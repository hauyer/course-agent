import json
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.course import Course
from app.models.knowledge_graph import (
    KnowledgeEdge,
    KnowledgeEdgeSource,
    KnowledgeGraphJob,
    KnowledgeNode,
    KnowledgeNodeSource,
)
from app.models.llm_config import LlmConfig
from app.models.material import Material
from app.models.material_chunk import MaterialChunk
from app.models.user import User
from app.schemas.knowledge_graph import KnowledgeExtractionBatch
from app.services import knowledge_graph_service
from app.services.knowledge_graph_service import (
    KnowledgeGraphConflictError,
    create_knowledge_graph_job,
    extract_knowledge_batch,
    get_active_knowledge_graph,
    process_knowledge_graph_job,
    cancel_or_delete_graph_job,
)


@pytest.fixture
def graph_db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(
        engine,
        tables=[
            User.__table__,
            Course.__table__,
            Material.__table__,
            MaterialChunk.__table__,
            LlmConfig.__table__,
            KnowledgeGraphJob.__table__,
            KnowledgeNode.__table__,
            KnowledgeEdge.__table__,
            KnowledgeNodeSource.__table__,
            KnowledgeEdgeSource.__table__,
        ],
    )
    factory = sessionmaker(bind=engine)
    db = factory()
    alice = User(username="alice-graph", email="alice-graph@example.com", password_hash="x")
    bob = User(username="bob-graph", email="bob-graph@example.com", password_hash="x")
    db.add_all([alice, bob])
    db.flush()
    course = Course(user_id=alice.id, name="操作系统")
    foreign_course = Course(user_id=bob.id, name="他人的数据库")
    db.add_all([course, foreign_course])
    db.flush()
    material = Material(
        user_id=alice.id,
        course_id=course.id,
        title="进程管理",
        original_filename="process.pdf",
        stored_filename="process-owned.pdf",
        file_path="uploads/alice/process.pdf",
        file_type="pdf",
        file_size=100,
        parse_status="success",
    )
    foreign_material = Material(
        user_id=bob.id,
        course_id=foreign_course.id,
        title="外部资料",
        original_filename="foreign.pdf",
        stored_filename="process-foreign.pdf",
        file_path="uploads/bob/foreign.pdf",
        file_type="pdf",
        file_size=100,
        parse_status="success",
    )
    db.add_all([material, foreign_material])
    db.flush()
    chunks = [
        MaterialChunk(
            user_id=alice.id,
            course_id=course.id,
            material_id=material.id,
            chunk_index=index,
            page_no=index + 1,
            content=content,
            char_count=len(content),
            vector_status="success",
        )
        for index, content in enumerate(
            ["进程拥有独立地址空间。", "线程共享进程资源，线程由进程包含。"]
        )
    ]
    db.add_all(chunks)
    db.add(
        MaterialChunk(
            user_id=bob.id,
            course_id=foreign_course.id,
            material_id=foreign_material.id,
            chunk_index=0,
            page_no=1,
            content="不得泄露的其他用户资料",
            char_count=12,
            vector_status="success",
        )
    )
    db.commit()
    try:
        yield db, factory, alice, bob, course, foreign_course, material, chunks
    finally:
        db.close()
        engine.dispose()


def add_llm_config(db, user_id: int):
    db.add(
        LlmConfig(
            user_id=user_id,
            provider="openai",
            model_name="fake-model",
            api_key_encrypted="encrypted-placeholder",
            enabled=True,
        )
    )
    db.commit()


def valid_extractor(_runtime, rows):
    ids = [chunk.id for chunk, _material in rows]
    return KnowledgeExtractionBatch.model_validate(
        {
            "nodes": [
                {
                    "name": "进程",
                    "node_type": "concept",
                    "description": "资源分配的基本单位",
                    "importance": 0.9,
                    "confidence": 0.95,
                    "chunk_ids": [ids[0]],
                },
                {
                    "name": " 进程 ",
                    "node_type": "concept",
                    "description": "重复名称应合并",
                    "importance": 0.7,
                    "confidence": 0.8,
                    "chunk_ids": [ids[0]],
                },
                {
                    "name": "线程",
                    "node_type": "concept",
                    "description": "调度执行单位",
                    "importance": 0.8,
                    "confidence": 0.9,
                    "chunk_ids": [ids[-1]],
                },
                {
                    "name": "伪造节点",
                    "node_type": "concept",
                    "chunk_ids": [999999],
                },
            ],
            "edges": [
                {
                    "source": "进程",
                    "target": "线程",
                    "relation_type": "contains",
                    "weight": 0.8,
                    "confidence": 0.9,
                    "chunk_ids": [ids[-1]],
                },
                {
                    "source": "线程",
                    "target": "进程",
                    "relation_type": "invented_relation",
                    "chunk_ids": [ids[-1]],
                },
            ],
        }
    )


def test_job_creation_requires_user_llm_and_rejects_foreign_course(graph_db):
    db, _, alice, _, course, foreign_course, _, _ = graph_db
    with pytest.raises(ValueError, match="大模型"):
        create_knowledge_graph_job(db, user_id=alice.id, course_id=course.id)
    add_llm_config(db, alice.id)
    with pytest.raises(PermissionError):
        create_knowledge_graph_job(db, user_id=alice.id, course_id=foreign_course.id)


def test_successful_graph_has_verified_sources_and_filters_model_hallucinations(
    graph_db, monkeypatch
):
    db, factory, alice, _, course, _, material, chunks = graph_db
    add_llm_config(db, alice.id)
    job = create_knowledge_graph_job(db, user_id=alice.id, course_id=course.id)
    monkeypatch.setattr(
        knowledge_graph_service,
        "load_user_llm_runtime",
        lambda _user_id: {"provider": "fake", "model_name": "fake", "api_key": "hidden"},
    )

    process_knowledge_graph_job(
        job_id=job.id,
        user_id=alice.id,
        course_id=course.id,
        session_factory=factory,
        extractor=valid_extractor,
    )

    db.expire_all()
    finished = db.query(KnowledgeGraphJob).filter_by(id=job.id).one()
    assert finished.status == "succeeded"
    assert finished.is_active is True
    assert finished.node_count == 2
    assert finished.edge_count == 1
    graph = get_active_knowledge_graph(db, user_id=alice.id, course_id=course.id)
    assert graph is not None
    assert {item["name"] for item in graph["nodes"]} == {"进程", "线程"}
    assert graph["edges"][0]["relation_type"] == "contains"
    allowed_chunk_ids = {chunk.id for chunk in chunks}
    for item in [*graph["nodes"], *graph["edges"]]:
        assert item["sources"]
        assert {source["chunk_id"] for source in item["sources"]} <= allowed_chunk_ids
        assert all(source["material_id"] == material.id for source in item["sources"])
        assert all("其他用户" not in source["evidence_text"] for source in item["sources"])


def test_same_course_cannot_have_two_running_jobs(graph_db):
    db, _, alice, _, course, _, _, _ = graph_db
    add_llm_config(db, alice.id)
    create_knowledge_graph_job(db, user_id=alice.id, course_id=course.id)
    with pytest.raises(KnowledgeGraphConflictError):
        create_knowledge_graph_job(db, user_id=alice.id, course_id=course.id)


def test_failed_new_version_does_not_replace_old_active_graph(graph_db, monkeypatch):
    db, factory, alice, _, course, _, _, _ = graph_db
    add_llm_config(db, alice.id)
    monkeypatch.setattr(
        knowledge_graph_service,
        "load_user_llm_runtime",
        lambda _user_id: {"provider": "fake", "model_name": "fake", "api_key": "hidden"},
    )
    first = create_knowledge_graph_job(db, user_id=alice.id, course_id=course.id)
    process_knowledge_graph_job(
        job_id=first.id,
        user_id=alice.id,
        course_id=course.id,
        session_factory=factory,
        extractor=valid_extractor,
    )
    second = create_knowledge_graph_job(db, user_id=alice.id, course_id=course.id)

    def broken_extractor(_runtime, _rows):
        raise ValueError("invalid json")

    process_knowledge_graph_job(
        job_id=second.id,
        user_id=alice.id,
        course_id=course.id,
        session_factory=factory,
        extractor=broken_extractor,
    )
    db.expire_all()
    assert db.query(KnowledgeGraphJob).filter_by(id=second.id).one().status == "failed"
    assert db.query(KnowledgeGraphJob).filter_by(id=first.id).one().is_active is True
    assert get_active_knowledge_graph(db, user_id=alice.id, course_id=course.id)["job_id"] == first.id


def test_new_success_atomically_switches_active_version(graph_db, monkeypatch):
    db, factory, alice, _, course, _, _, _ = graph_db
    add_llm_config(db, alice.id)
    monkeypatch.setattr(
        knowledge_graph_service,
        "load_user_llm_runtime",
        lambda _user_id: {"provider": "fake", "model_name": "fake", "api_key": "hidden"},
    )
    first = create_knowledge_graph_job(db, user_id=alice.id, course_id=course.id)
    process_knowledge_graph_job(
        job_id=first.id, user_id=alice.id, course_id=course.id,
        session_factory=factory, extractor=valid_extractor,
    )
    second = create_knowledge_graph_job(db, user_id=alice.id, course_id=course.id)
    process_knowledge_graph_job(
        job_id=second.id, user_id=alice.id, course_id=course.id,
        session_factory=factory, extractor=valid_extractor,
    )
    db.expire_all()
    assert db.query(KnowledgeGraphJob).filter_by(id=first.id).one().is_active is False
    assert db.query(KnowledgeGraphJob).filter_by(id=second.id).one().is_active is True


def test_background_processor_uses_factory_owned_session(graph_db, monkeypatch):
    request_db, factory, alice, _, course, _, _, _ = graph_db
    add_llm_config(request_db, alice.id)
    job = create_knowledge_graph_job(request_db, user_id=alice.id, course_id=course.id)
    created_sessions = []

    def tracked_factory():
        session = factory()
        created_sessions.append(session)
        return session

    monkeypatch.setattr(
        knowledge_graph_service,
        "load_user_llm_runtime",
        lambda _user_id: {"provider": "fake", "model_name": "fake", "api_key": "hidden"},
    )
    process_knowledge_graph_job(
        job_id=job.id, user_id=alice.id, course_id=course.id,
        session_factory=tracked_factory, extractor=valid_extractor,
    )
    assert len(created_sessions) == 1
    assert created_sessions[0] is not request_db


def test_structured_llm_output_retries_once(monkeypatch, graph_db):
    _, _, _, _, _, _, material, chunks = graph_db
    calls = []

    class FakeModel:
        def invoke(self, _messages):
            calls.append(1)
            if len(calls) == 1:
                return SimpleNamespace(content="not json")
            return SimpleNamespace(
                content=json.dumps(
                    {
                        "nodes": [
                            {
                                "name": "进程",
                                "node_type": "concept",
                                "chunk_ids": [chunks[0].id],
                            }
                        ],
                        "edges": [],
                    },
                    ensure_ascii=False,
                )
            )

    monkeypatch.setattr(knowledge_graph_service, "init_model", lambda: FakeModel())
    result = extract_knowledge_batch(
        {"provider": "fake", "model_name": "fake", "api_key": "hidden"},
        [(chunks[0], material)],
    )
    assert len(calls) == 2
    assert result.nodes[0].name == "进程"


def test_structured_scores_accept_common_model_labels_and_percentages():
    result = KnowledgeExtractionBatch.model_validate(
        {
            "nodes": [
                {
                    "name": "生成函数",
                    "importance": "high",
                    "confidence": "80%",
                    "chunk_ids": [1],
                },
                {
                    "name": "递推关系",
                    "importance": "medium",
                    "confidence": 75,
                    "chunk_ids": [2],
                },
            ],
            "edges": [
                {
                    "source": "递推关系",
                    "target": "生成函数",
                    "relation_type": "applies_to",
                    "weight": "low",
                    "confidence": "0.9",
                    "chunk_ids": [2],
                }
            ],
        }
    )

    assert result.nodes[0].importance == pytest.approx(0.85)
    assert result.nodes[0].confidence == pytest.approx(0.8)
    assert result.nodes[1].importance == pytest.approx(0.6)
    assert result.nodes[1].confidence == pytest.approx(0.75)
    assert result.edges[0].weight == pytest.approx(0.35)
    assert result.edges[0].confidence == pytest.approx(0.9)


def test_first_partial_graph_keeps_verified_batches_viewable(graph_db, monkeypatch):
    db, factory, alice, _, course, _, _, _ = graph_db
    add_llm_config(db, alice.id)
    job = create_knowledge_graph_job(db, user_id=alice.id, course_id=course.id)
    monkeypatch.setattr(
        knowledge_graph_service,
        "load_user_llm_runtime",
        lambda _user_id: {"provider": "fake", "model_name": "fake", "api_key": "hidden"},
    )
    monkeypatch.setattr(
        knowledge_graph_service,
        "_batch_rows",
        lambda rows: ([row] for row in rows),
    )
    calls = 0

    def partly_broken_extractor(_runtime, rows):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise ValueError("invalid json")
        chunk_id = rows[0][0].id
        return KnowledgeExtractionBatch.model_validate(
            {"nodes": [{"name": "进程", "chunk_ids": [chunk_id]}], "edges": []}
        )

    process_knowledge_graph_job(
        job_id=job.id,
        user_id=alice.id,
        course_id=course.id,
        session_factory=factory,
        extractor=partly_broken_extractor,
    )

    db.expire_all()
    finished = db.query(KnowledgeGraphJob).filter_by(id=job.id).one()
    assert finished.status == "partial"
    assert finished.is_active is True
    graph = get_active_knowledge_graph(db, user_id=alice.id, course_id=course.id)
    assert graph is not None
    assert graph["job_id"] == job.id
    assert [node["name"] for node in graph["nodes"]] == ["进程"]


def test_inactive_legacy_partial_graph_with_nodes_is_still_viewable(graph_db, monkeypatch):
    db, factory, alice, _, course, _, _, _ = graph_db
    add_llm_config(db, alice.id)
    job = create_knowledge_graph_job(db, user_id=alice.id, course_id=course.id)
    monkeypatch.setattr(
        knowledge_graph_service,
        "load_user_llm_runtime",
        lambda _user_id: {"provider": "fake", "model_name": "fake", "api_key": "hidden"},
    )
    process_knowledge_graph_job(
        job_id=job.id,
        user_id=alice.id,
        course_id=course.id,
        session_factory=factory,
        extractor=valid_extractor,
    )
    finished = db.query(KnowledgeGraphJob).filter_by(id=job.id).one()
    finished.status = "partial"
    finished.is_active = False
    db.commit()

    graph = get_active_knowledge_graph(db, user_id=alice.id, course_id=course.id)

    assert graph is not None
    assert graph["job_id"] == job.id
    assert graph["nodes"]


def test_large_course_is_processed_in_bounded_batches(graph_db, monkeypatch):
    db, factory, alice, _, course, _, material, _ = graph_db
    for index in range(2, 22):
        text = f"第 {index} 个受控知识片段 " + "内容" * 300
        db.add(
            MaterialChunk(
                user_id=alice.id,
                course_id=course.id,
                material_id=material.id,
                chunk_index=index,
                page_no=index + 1,
                content=text,
                char_count=len(text),
                vector_status="success",
            )
        )
    db.commit()
    add_llm_config(db, alice.id)
    job = create_knowledge_graph_job(db, user_id=alice.id, course_id=course.id)
    batch_sizes = []

    def bounded_extractor(_runtime, rows):
        batch_sizes.append(len(rows))
        chunk_id = rows[0][0].id
        return KnowledgeExtractionBatch.model_validate(
            {
                "nodes": [
                    {
                        "name": f"知识点 {chunk_id}",
                        "node_type": "concept",
                        "chunk_ids": [chunk_id],
                    }
                ],
                "edges": [],
            }
        )

    monkeypatch.setattr(
        knowledge_graph_service,
        "load_user_llm_runtime",
        lambda _user_id: {"provider": "fake", "model_name": "fake", "api_key": "hidden"},
    )
    process_knowledge_graph_job(
        job_id=job.id,
        user_id=alice.id,
        course_id=course.id,
        session_factory=factory,
        extractor=bounded_extractor,
    )
    assert len(batch_sizes) >= 3
    assert max(batch_sizes) <= 8


def test_cancelled_job_does_not_start_or_replace_graph(graph_db):
    db, factory, alice, _, course, _, _, _ = graph_db
    add_llm_config(db, alice.id)
    job = create_knowledge_graph_job(db, user_id=alice.id, course_id=course.id)
    result = cancel_or_delete_graph_job(
        db, user_id=alice.id, course_id=course.id, job_id=job.id
    )
    assert result == "cancelled"
    process_knowledge_graph_job(
        job_id=job.id,
        user_id=alice.id,
        course_id=course.id,
        session_factory=factory,
        extractor=valid_extractor,
    )
    db.expire_all()
    assert db.query(KnowledgeGraphJob).filter_by(id=job.id).one().status == "cancelled"
    assert get_active_knowledge_graph(db, user_id=alice.id, course_id=course.id) is None
