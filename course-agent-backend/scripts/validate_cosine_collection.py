from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy.orm import Session  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models.material import Material  # noqa: E402
from app.models.material_chunk import MaterialChunk  # noqa: E402
from app.services.course_retrieval_service import distance_to_cosine_similarity  # noqa: E402
from app.services.vector_service import (  # noqa: E402
    DEFAULT_COSINE_COLLECTION,
    LEGACY_COLLECTION_NAME,
    encode_texts,
    get_chroma_collection,
    validate_collection_metric,
)
from scripts.rebuild_cosine_vectors import eligible_chunk_query  # noqa: E402


@dataclass
class ValidationReport:
    collection_name: str
    metric: str = "cosine"
    sql_eligible_count: int = 0
    collection_count: int = 0
    sampled_count: int = 0
    query_checked: bool = False
    issues: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "ok": self.ok}


def validate_cosine_collection(
    db: Session,
    *,
    collection: Any,
    sample_size: int = 20,
    run_query: bool = True,
) -> ValidationReport:
    validate_collection_metric(collection)
    report = ValidationReport(collection_name=getattr(collection, "name", "<unknown>"))
    report.sql_eligible_count = eligible_chunk_query(db).count()
    report.collection_count = int(collection.count())
    if report.collection_count != report.sql_eligible_count:
        report.issues.append(
            f"记录数不一致：SQL={report.sql_eligible_count}, Chroma={report.collection_count}"
        )

    sample = collection.get(limit=max(1, min(sample_size, 100)), include=["metadatas"])
    ids = sample.get("ids") or []
    metadatas = sample.get("metadatas") or []
    required = {
        "user_id",
        "course_id",
        "material_id",
        "chunk_id",
        "chunk_index",
        "page_no",
        "file_type",
        "embedding_version",
    }
    for vector_id, metadata in zip(ids, metadatas):
        metadata = metadata or {}
        if not required.issubset(metadata):
            report.issues.append(f"{vector_id} metadata 字段不完整")
            continue
        row = (
            db.query(MaterialChunk, Material)
            .join(Material, Material.id == MaterialChunk.material_id)
            .filter(
                MaterialChunk.id == int(metadata["chunk_id"]),
                MaterialChunk.user_id == int(metadata["user_id"]),
                MaterialChunk.course_id == int(metadata["course_id"]),
                MaterialChunk.material_id == int(metadata["material_id"]),
                Material.user_id == int(metadata["user_id"]),
                Material.course_id == int(metadata["course_id"]),
            )
            .first()
        )
        if row is None:
            report.issues.append(f"{vector_id} 无匹配的用户/课程/资料 SQL 片段")
    report.sampled_count = len(ids)

    if run_query and report.sql_eligible_count:
        row = eligible_chunk_query(db).order_by(MaterialChunk.id.asc()).first()
        if row is not None:
            chunk, _material = row
            embedding = encode_texts([chunk.content])[0]
            query_result = collection.query(
                query_embeddings=[embedding],
                n_results=min(3, max(1, report.collection_count)),
                where={
                    "$and": [
                        {"user_id": int(chunk.user_id)},
                        {"course_id": int(chunk.course_id)},
                    ]
                },
                include=["metadatas", "distances"],
            )
            result_metadatas = (query_result.get("metadatas") or [[]])[0]
            distances = (query_result.get("distances") or [[]])[0]
            for metadata, distance in zip(result_metadatas, distances):
                if (
                    int(metadata.get("user_id", -1)) != chunk.user_id
                    or int(metadata.get("course_id", -1)) != chunk.course_id
                ):
                    report.issues.append("随机查询返回了作用域外 metadata")
                similarity = distance_to_cosine_similarity(float(distance))
                if not -1.0 <= similarity <= 1.0:
                    report.issues.append("distance 与 cosine similarity 关系异常")
            report.query_checked = True
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the separate 1.1 cosine collection.")
    parser.add_argument("--collection", default=DEFAULT_COSINE_COLLECTION)
    parser.add_argument("--legacy-collection", default=LEGACY_COLLECTION_NAME)
    parser.add_argument("--sample-size", type=int, default=20)
    parser.add_argument("--skip-query", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.collection == args.legacy_collection:
        print("拒绝把旧 1.0 collection 当作 1.1 cosine collection 校验。", file=sys.stderr)
        return 2
    db = SessionLocal()
    try:
        collection = get_chroma_collection(collection_name=args.collection)
        report = validate_cosine_collection(
            db,
            collection=collection,
            sample_size=args.sample_size,
            run_query=not args.skip_query,
        )
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        return 0 if report.ok else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

