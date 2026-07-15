import asyncio
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agent.citations import (
    CitationCollector,
    activate_citation_collector,
    get_citation_collector,
    reset_citation_collector,
)
from app.database import Base
from app.models.course import Course
from app.models.material import Material
from app.models.material_chunk import MaterialChunk
from app.models.user import User
from app.services import citation_service
from app.services.course_retrieval_service import CourseChunkSearchResult
from app.schemas.agent import AgentChatRequest
from app.routers import agent as agent_router


def citation_item(chunk_id: int) -> dict:
    return {
        "course_id": 1,
        "course_name": "操作系统",
        "material_id": 10,
        "material_title": "进程管理",
        "chunk_id": chunk_id,
        "chunk_index": chunk_id,
        "page_no": 12,
        "content": f"片段 {chunk_id}",
        "similarity_score": 0.9,
    }


def test_collector_assigns_stable_ids_and_deduplicates_chunks():
    collector = CitationCollector()
    first = collector.register(citation_item(7))
    duplicate = collector.register({**citation_item(7), "content": "不得覆盖"})
    second = collector.register(citation_item(8))

    assert first["citation_id"] == "C1"
    assert duplicate == first
    assert second["citation_id"] == "C2"
    assert [item["chunk_id"] for item in collector.snapshot()] == [7, 8]


@pytest.mark.asyncio
async def test_collectors_are_isolated_across_concurrent_requests():
    async def run(chunk_id: int):
        collector = CitationCollector()
        token = activate_citation_collector(collector)
        try:
            await asyncio.sleep(0)
            assert get_citation_collector() is collector
            collector.register(citation_item(chunk_id))
            await asyncio.sleep(0)
            return collector.snapshot()
        finally:
            reset_citation_collector(token)

    left, right = await asyncio.gather(run(101), run(202))
    assert [item["chunk_id"] for item in left] == [101]
    assert [item["chunk_id"] for item in right] == [202]
    assert get_citation_collector() is None


def test_collector_is_reset_after_tool_failure():
    collector = CitationCollector()
    token = activate_citation_collector(collector)
    try:
        collector.register(citation_item(1))
        with pytest.raises(RuntimeError):
            raise RuntimeError("tool failed")
    finally:
        reset_citation_collector(token)

    next_collector = CitationCollector()
    next_token = activate_citation_collector(next_collector)
    try:
        assert next_collector.snapshot() == []
    finally:
        reset_citation_collector(next_token)


def test_unknown_markers_are_removed_without_adding_sources():
    citations = [
        {**citation_item(1), "citation_id": "C1", "index": 1},
    ]
    answer = citation_service.sanitize_answer_citation_markers(
        "进程有地址空间 [C1]，伪造内容 [C9]。",
        citations,
    )
    assert "[C1]" in answer
    assert "[C9]" not in answer


@pytest.fixture
def citation_db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            User.__table__,
            Course.__table__,
            Material.__table__,
            MaterialChunk.__table__,
        ],
    )
    session = sessionmaker(bind=engine)()
    user_a = User(username="alice", email="alice@example.com", password_hash="x")
    user_b = User(username="bob", email="bob@example.com", password_hash="x")
    session.add_all([user_a, user_b])
    session.flush()
    course_a = Course(user_id=user_a.id, name="操作系统")
    other_course = Course(user_id=user_a.id, name="数据库")
    foreign_course = Course(user_id=user_b.id, name="他人课程")
    session.add_all([course_a, other_course, foreign_course])
    session.flush()

    def add_chunk(user_id: int, course_id: int, title: str, content: str):
        material = Material(
            user_id=user_id,
            course_id=course_id,
            title=title,
            original_filename=f"{title}.txt",
            stored_filename=f"{user_id}-{course_id}-{title}.txt",
            file_path=f"safe/{user_id}/{course_id}/{title}.txt",
            file_type="txt",
            file_size=len(content),
            parse_status="success",
        )
        session.add(material)
        session.flush()
        chunk = MaterialChunk(
            user_id=user_id,
            course_id=course_id,
            material_id=material.id,
            chunk_index=0,
            page_no=1,
            content=content,
            char_count=len(content),
            vector_status="success",
        )
        session.add(chunk)
        session.flush()
        return material, chunk

    owned = add_chunk(user_a.id, course_a.id, "进程", "进程拥有独立地址空间。")
    cross_course = add_chunk(user_a.id, other_course.id, "事务", "事务具有原子性。")
    foreign = add_chunk(user_b.id, foreign_course.id, "秘密", "其他用户资料。")
    session.commit()
    yield session, user_a, course_a, owned, cross_course, foreign
    session.close()


def test_retrieval_rechecks_user_course_material_and_chunk(monkeypatch, citation_db):
    db, user, course, owned, cross_course, foreign = citation_db
    owned_material, owned_chunk = owned
    monkeypatch.setattr(
        citation_service,
        "retrieve_structured_course_chunks",
        lambda *_args, **_kwargs: [
            CourseChunkSearchResult(
                vector_id=f"chunk_{owned_chunk.id}",
                chunk_id=owned_chunk.id,
                chunk_index=owned_chunk.chunk_index,
                course_id=course.id,
                course_name=course.name,
                material_id=owned_material.id,
                material_title=owned_material.title,
                file_type=owned_material.file_type,
                page_no=owned_chunk.page_no,
                content=owned_chunk.content,
                distance=0.05,
                similarity_score=0.95,
                similarity_percent=95.0,
            )
        ],
    )
    collector = CitationCollector()
    results = citation_service.retrieve_course_chunks(
        db,
        user_id=user.id,
        course_id=course.id,
        query="什么是进程",
        top_k=5,
        collector=collector,
    )

    assert len(results) == 1
    assert results[0]["course_name"] == "操作系统"
    assert results[0]["material_title"] == owned_material.title
    assert results[0]["chunk_id"] == owned_chunk.id
    assert results[0]["citation_id"] == "C1"
    assert collector.snapshot() == results


def test_no_semantic_results_returns_empty_citations(monkeypatch, citation_db):
    db, user, course, *_ = citation_db
    monkeypatch.setattr(
        citation_service,
        "retrieve_structured_course_chunks",
        lambda *_args, **_kwargs: [],
    )
    assert citation_service.retrieve_course_chunks(
        db,
        user_id=user.id,
        course_id=course.id,
        query="不存在的内容",
        top_k=5,
    ) == []


def _install_agent_route_fakes(monkeypatch, saved_messages: list[dict]):
    session = SimpleNamespace(id=88, course_id=3)
    monkeypatch.setattr(agent_router, "_prepare_session", lambda *_args, **_kwargs: (session, False))
    monkeypatch.setattr(agent_router, "get_recent_messages", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(agent_router, "save_user_message", lambda **_kwargs: SimpleNamespace(id=901))

    def save_assistant(**kwargs):
        saved_messages.append(kwargs)
        return SimpleNamespace(id=902)

    monkeypatch.setattr(agent_router, "save_assistant_message", save_assistant)
    monkeypatch.setattr(agent_router, "_write_agent_audit", lambda **_kwargs: None)

    def citation_context(*_args, **_kwargs):
        collector = get_citation_collector()
        assert collector is not None
        collector.register(citation_item(77))
        return "[C1] 已验证片段"

    monkeypatch.setattr(agent_router, "_request_citation_context", citation_context)

    async def events(**_kwargs):
        yield {
            "type": "model_start",
            "node": "concept_agent",
            "run_id": "run-1",
        }
        yield {
            "type": "model_end",
            "node": "concept_agent",
            "run_id": "run-1",
            "final": True,
            "content": "真实结论 [C1]，伪造结论 [C99]。",
            "usage": {},
        }

    monkeypatch.setattr(agent_router, "_agent_events", events)


@pytest.mark.asyncio
async def test_stream_and_non_stream_return_and_persist_identical_citations(monkeypatch):
    saved_messages: list[dict] = []
    _install_agent_route_fakes(monkeypatch, saved_messages)
    payload = AgentChatRequest(course_id=3, session_id=88, message="解释进程", top_k=5)
    request = SimpleNamespace(state=SimpleNamespace(trace_id="test-trace"))
    user = SimpleNamespace(id=5)

    direct = await agent_router.agent_chat(payload, request, db=object(), current_user=user)
    stream_response = await agent_router.agent_chat_stream(payload, request, db=object(), current_user=user)
    raw = ""
    async for part in stream_response.body_iterator:
        raw += part.decode() if isinstance(part, bytes) else part
    result = None
    persisted = None
    for frame in raw.split("\n\n"):
        if not frame.startswith("data: "):
            continue
        body = frame[6:]
        if body == "[DONE]":
            continue
        event = json.loads(body)
        if event.get("type") == "persisted":
            persisted = event
        if event.get("type") == "result":
            result = event

    assert result is not None
    assert persisted["session_id"] == 88
    assert persisted["course_id"] == 3
    assert direct["citations"] == result["citations"]
    assert direct["citations"][0]["citation_id"] == "C1"
    assert "[C99]" not in direct["answer"]
    assert saved_messages[0]["citations"] == saved_messages[1]["citations"]
    assert saved_messages[0]["agent_trace"]
    assert get_citation_collector() is None
