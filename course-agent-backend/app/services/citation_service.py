from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.agent.citations import CitationCollector, get_citation_collector
from app.models.course import Course
from app.models.material import Material
from app.models.material_chunk import MaterialChunk
from app.services.vector_service import semantic_search


MAX_CITATION_CONTENT_LENGTH = 1000
_CITATION_MARKER = re.compile(r"\[C(\d+)\]")


def _safe_excerpt(content: str, limit: int = MAX_CITATION_CONTENT_LENGTH) -> str:
    normalized = " ".join((content or "").split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def retrieve_course_chunks(
    db: Session,
    *,
    user_id: int,
    course_id: int,
    query: str,
    top_k: int,
    collector: CitationCollector | None = None,
) -> list[dict[str, Any]]:
    """Retrieve from Chroma, then verify every result against owned SQL rows."""

    if user_id < 1 or course_id < 1:
        raise ValueError("无法确定当前用户或课程")
    if not query.strip():
        raise ValueError("检索问题不能为空")
    top_k = max(1, min(int(top_k), 10))

    course = (
        db.query(Course)
        .filter(Course.id == course_id, Course.user_id == user_id)
        .first()
    )
    if course is None:
        raise PermissionError("课程不存在或无权限访问")

    raw_results = semantic_search(
        db=db,
        user_id=user_id,
        course_id=course_id,
        query=query,
        top_k=top_k,
    )
    ordered_chunk_ids: list[int] = []
    by_chunk_result: dict[int, dict[str, Any]] = {}
    for item in raw_results:
        try:
            chunk_id = int(item["chunk_id"])
        except (KeyError, TypeError, ValueError):
            continue
        if chunk_id in by_chunk_result:
            continue
        ordered_chunk_ids.append(chunk_id)
        by_chunk_result[chunk_id] = item

    if not ordered_chunk_ids:
        return []

    verified_rows = (
        db.query(MaterialChunk, Material)
        .join(Material, Material.id == MaterialChunk.material_id)
        .filter(
            MaterialChunk.id.in_(ordered_chunk_ids),
            MaterialChunk.user_id == user_id,
            MaterialChunk.course_id == course_id,
            Material.user_id == user_id,
            Material.course_id == course_id,
        )
        .all()
    )
    verified = {chunk.id: (chunk, material) for chunk, material in verified_rows}
    active_collector = collector or get_citation_collector()
    output: list[dict[str, Any]] = []

    for chunk_id in ordered_chunk_ids:
        pair = verified.get(chunk_id)
        if pair is None:
            continue
        chunk, material = pair
        raw = by_chunk_result[chunk_id]
        citation = {
            "course_id": course.id,
            "course_name": course.name,
            "material_id": material.id,
            "material_title": material.title,
            "chunk_id": chunk.id,
            "chunk_index": chunk.chunk_index,
            "page_no": chunk.page_no,
            "content": _safe_excerpt(chunk.content),
            "similarity_score": round(float(raw.get("similarity_score", 0.0)), 4),
        }
        if active_collector is not None:
            citation = active_collector.register(citation)
        else:
            index = len(output) + 1
            citation = {**citation, "citation_id": f"C{index}", "index": index}
        output.append(citation)

    return output


def build_agent_citation_context(citations: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    for item in citations:
        page = f"第 {item['page_no']} 页" if item.get("page_no") is not None else "页码未知"
        blocks.append(
            "\n".join(
                [
                    f"[{item['citation_id']}]",
                    f"课程：{item['course_name']}",
                    f"资料：{item['material_title']}",
                    f"位置：{page}，片段 {item['chunk_index']}",
                    f"片段：{item['content']}",
                ]
            )
        )
    return "\n\n".join(blocks)


def sanitize_answer_citation_markers(
    answer: str,
    citations: list[dict[str, Any]],
) -> str:
    valid_ids = {str(item["citation_id"]) for item in citations}

    def replace(match: re.Match[str]) -> str:
        marker = f"C{match.group(1)}"
        return match.group(0) if marker in valid_ids else ""

    return _CITATION_MARKER.sub(replace, answer).strip()
