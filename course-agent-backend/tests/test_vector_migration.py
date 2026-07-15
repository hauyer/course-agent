from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.course import Course
from app.models.material import Material
from app.models.material_chunk import MaterialChunk
from app.models.user import User
from scripts import rebuild_cosine_vectors as rebuild_script
from scripts import validate_cosine_collection as validate_script


class UpsertCollection:
    name = "course_material_chunks_v1_1_cosine"
    configuration = {"hnsw": {"space": "cosine"}}
    metadata = None

    def __init__(self, *, fail_on_call=None):
        self.calls = []
        self.records = {}
        self.fail_on_call = fail_on_call

    def upsert(self, **kwargs):
        call_number = len(self.calls) + 1
        self.calls.append(kwargs)
        if call_number == self.fail_on_call:
            raise RuntimeError("fake batch failure")
        for index, vector_id in enumerate(kwargs["ids"]):
            self.records[vector_id] = {
                "metadata": kwargs["metadatas"][index],
                "document": kwargs["documents"][index],
                "embedding": kwargs["embeddings"][index],
            }

    def count(self):
        return len(self.records)

    def get(self, *, limit, include):
        items = list(self.records.items())[:limit]
        return {
            "ids": [key for key, _value in items],
            "metadatas": [value["metadata"] for _key, value in items],
        }

    def query(self, *, where, **_kwargs):
        user_filter, course_filter = where["$and"]
        user_id = user_filter["user_id"]
        course_id = course_filter["course_id"]
        matches = [
            value
            for value in self.records.values()
            if value["metadata"]["user_id"] == user_id
            and value["metadata"]["course_id"] == course_id
        ]
        return {
            "metadatas": [[item["metadata"] for item in matches[:3]]],
            "distances": [[0.0 for _item in matches[:3]]],
        }


@pytest.fixture
def migration_db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[User.__table__, Course.__table__, Material.__table__, MaterialChunk.__table__],
    )
    db = sessionmaker(bind=engine)()
    user = User(username="migration", email="migration@example.com", password_hash="x")
    db.add(user)
    db.flush()
    course = Course(user_id=user.id, name="操作系统")
    db.add(course)
    db.flush()
    material = Material(
        user_id=user.id,
        course_id=course.id,
        title="进程管理",
        original_filename="process.pdf",
        stored_filename="migration-process.pdf",
        file_path="safe/process.pdf",
        file_type="pdf",
        file_size=100,
        parse_status="success",
    )
    failed_material = Material(
        user_id=user.id,
        course_id=course.id,
        title="解析失败",
        original_filename="failed.pdf",
        stored_filename="migration-failed.pdf",
        file_path="safe/failed.pdf",
        file_type="pdf",
        file_size=100,
        parse_status="failed",
    )
    db.add_all([material, failed_material])
    db.flush()
    chunks = []
    for index in range(3):
        chunk = MaterialChunk(
            user_id=user.id,
            course_id=course.id,
            material_id=material.id,
            chunk_index=index,
            page_no=index + 1,
            content=f"有效片段 {index}",
            char_count=6,
            vector_status="pending",
        )
        chunks.append(chunk)
    invalid = MaterialChunk(
        user_id=user.id,
        course_id=course.id,
        material_id=failed_material.id,
        chunk_index=0,
        page_no=1,
        content="不应迁移",
        char_count=4,
        vector_status="success",
    )
    db.add_all([*chunks, invalid])
    db.commit()
    yield db, user, course, material, chunks
    db.close()


def fake_encode(texts):
    return [[1.0, 0.0] for _text in texts]


def test_rebuild_defaults_to_dry_run_without_writes(migration_db):
    db, *_ = migration_db
    stats = rebuild_script.rebuild_cosine_vectors(
        db,
        collection=None,
        dry_run=True,
        batch_size=2,
        encode_fn=lambda _texts: pytest.fail("dry-run must not encode"),
    )
    assert stats.eligible == 3
    assert stats.skipped == 3
    assert stats.succeeded == 0


def test_batch_rebuild_upserts_stable_ids_and_is_idempotent(migration_db):
    db, _user, _course, _material, chunks = migration_db
    collection = UpsertCollection()
    first = rebuild_script.rebuild_cosine_vectors(
        db,
        collection=collection,
        dry_run=False,
        batch_size=2,
        encode_fn=fake_encode,
        version="test_normalized_v1",
    )
    second = rebuild_script.rebuild_cosine_vectors(
        db,
        collection=collection,
        dry_run=False,
        batch_size=2,
        encode_fn=fake_encode,
        version="test_normalized_v1",
    )
    expected_ids = {f"chunk_{chunk.id}" for chunk in chunks}
    assert first.succeeded == second.succeeded == 3
    assert set(collection.records) == expected_ids
    assert collection.count() == 3
    assert all("embedding_version" in value["metadata"] for value in collection.records.values())
    assert not hasattr(collection, "delete")


def test_failed_batch_keeps_previous_success_and_continues(migration_db):
    db, *_ = migration_db
    collection = UpsertCollection(fail_on_call=2)
    stats = rebuild_script.rebuild_cosine_vectors(
        db,
        collection=collection,
        dry_run=False,
        batch_size=1,
        encode_fn=fake_encode,
        version="test_normalized_v1",
    )
    assert stats.succeeded == 2
    assert stats.failed == 1
    assert len(stats.failed_chunk_ids) == 1
    assert collection.count() == 2


def test_validation_checks_counts_metadata_query_and_scope(monkeypatch, migration_db):
    db, *_ = migration_db
    collection = UpsertCollection()
    rebuild_script.rebuild_cosine_vectors(
        db,
        collection=collection,
        dry_run=False,
        batch_size=3,
        encode_fn=fake_encode,
        version="test_normalized_v1",
    )
    monkeypatch.setattr(validate_script, "encode_texts", fake_encode)
    report = validate_script.validate_cosine_collection(
        db,
        collection=collection,
        sample_size=20,
        run_query=True,
    )
    assert report.ok
    assert report.sql_eligible_count == report.collection_count == 3
    assert report.sampled_count == 3
    assert report.query_checked is True


def test_validation_rejects_count_mismatch(migration_db):
    db, *_ = migration_db
    collection = UpsertCollection()
    report = validate_script.validate_cosine_collection(
        db,
        collection=collection,
        sample_size=20,
        run_query=False,
    )
    assert not report.ok
    assert "记录数不一致" in report.issues[0]

