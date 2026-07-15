from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from app.database import Base


class KnowledgeGraphJob(Base):
    __tablename__ = "knowledge_graph_jobs"
    __table_args__ = (
        Index("ix_knowledge_graph_jobs_user_course", "user_id", "course_id"),
        Index("ix_knowledge_graph_jobs_course_active", "course_id", "is_active"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    course_id = Column(
        Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status = Column(String(20), nullable=False, default="pending", index=True)
    progress = Column(Integer, nullable=False, default=0)
    stage = Column(String(100), nullable=False, default="等待开始")
    source_hash = Column(String(64), nullable=True, index=True)
    is_active = Column(Boolean, nullable=False, default=False, index=True)
    node_count = Column(Integer, nullable=False, default=0)
    edge_count = Column(Integer, nullable=False, default=0)
    error_message = Column(String(1000), nullable=True)
    # pending/running 时为 user_id:course_id，终态时清空。唯一索引阻止并发创建。
    running_guard = Column(String(100), nullable=True, unique=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)


class KnowledgeNode(Base):
    __tablename__ = "knowledge_nodes"
    __table_args__ = (
        UniqueConstraint("job_id", "normalized_name", name="uq_knowledge_nodes_job_name"),
        Index("ix_knowledge_nodes_user_course", "user_id", "course_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(
        Integer,
        ForeignKey("knowledge_graph_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    course_id = Column(
        Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name = Column(String(200), nullable=False)
    normalized_name = Column(String(200), nullable=False)
    node_type = Column(String(50), nullable=False, default="concept", index=True)
    description = Column(Text, nullable=True)
    importance = Column(Float, nullable=False, default=0.5)
    confidence = Column(Float, nullable=False, default=0.5)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class KnowledgeEdge(Base):
    __tablename__ = "knowledge_edges"
    __table_args__ = (
        UniqueConstraint(
            "job_id",
            "source_node_id",
            "target_node_id",
            "relation_type",
            name="uq_knowledge_edges_job_relation",
        ),
        Index("ix_knowledge_edges_user_course", "user_id", "course_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(
        Integer,
        ForeignKey("knowledge_graph_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    course_id = Column(
        Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_node_id = Column(
        Integer, ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_node_id = Column(
        Integer, ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    relation_type = Column(String(30), nullable=False, index=True)
    weight = Column(Float, nullable=False, default=0.5)
    confidence = Column(Float, nullable=False, default=0.5)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class KnowledgeNodeSource(Base):
    __tablename__ = "knowledge_node_sources"
    __table_args__ = (
        UniqueConstraint("node_id", "chunk_id", name="uq_knowledge_node_sources_chunk"),
        Index("ix_knowledge_node_sources_material", "material_id", "chunk_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    node_id = Column(
        Integer, ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    material_id = Column(
        Integer, ForeignKey("materials.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_id = Column(
        Integer, ForeignKey("material_chunks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_no = Column(Integer, nullable=True)
    evidence_text = Column(Text, nullable=False)


class KnowledgeEdgeSource(Base):
    __tablename__ = "knowledge_edge_sources"
    __table_args__ = (
        UniqueConstraint("edge_id", "chunk_id", name="uq_knowledge_edge_sources_chunk"),
        Index("ix_knowledge_edge_sources_material", "material_id", "chunk_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    edge_id = Column(
        Integer, ForeignKey("knowledge_edges.id", ondelete="CASCADE"), nullable=False, index=True
    )
    material_id = Column(
        Integer, ForeignKey("materials.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_id = Column(
        Integer, ForeignKey("material_chunks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_no = Column(Integer, nullable=True)
    evidence_text = Column(Text, nullable=False)
