"""Add 1.1 citations trace, multi-plan, knowledge graph and user avatar structures."""

import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects.mysql import LONGTEXT

from app.database import Base
import app.models  # noqa: F401

revision = "0002_v1_1_features"
down_revision = "0001_v1_0_baseline"
branch_labels = None
depends_on = None

NEW_TABLES = (
    "study_plan_courses", "knowledge_graph_jobs", "knowledge_nodes",
    "knowledge_edges", "knowledge_node_sources", "knowledge_edge_sources",
)


def _columns(table: str) -> set[str]:
    return {column["name"] for column in inspect(op.get_bind()).get_columns(table)}


def _indexes(table: str) -> set[str]:
    inspector = inspect(op.get_bind())
    names = {item["name"] for item in inspector.get_indexes(table) if item.get("name")}
    names.update(item["name"] for item in inspector.get_unique_constraints(table) if item.get("name"))
    return names


def upgrade() -> None:
    if "avatar_data" not in _columns("users"):
        op.add_column("users", sa.Column("avatar_data", sa.Text().with_variant(LONGTEXT(), "mysql"), nullable=True))
    if "agent_trace" not in _columns("chat_messages"):
        op.add_column("chat_messages", sa.Column("agent_trace", sa.JSON(), nullable=True))

    plan_columns = _columns("study_plans")
    for name, column in (
        ("plan_type", sa.Column("plan_type", sa.String(20), nullable=True)),
        ("version", sa.Column("version", sa.Integer(), nullable=True)),
        ("client_request_id", sa.Column("client_request_id", sa.String(64), nullable=True)),
        ("available_weekdays", sa.Column("available_weekdays", sa.JSON(), nullable=True)),
    ):
        if name not in plan_columns:
            op.add_column("study_plans", column)
    op.execute(sa.text("UPDATE study_plans SET plan_type='single' WHERE plan_type IS NULL"))
    op.execute(sa.text("UPDATE study_plans SET version=1 WHERE version IS NULL"))
    dialect = op.get_bind().dialect.name
    if dialect == "mysql":
        op.execute(sa.text("UPDATE study_plans SET available_weekdays=JSON_ARRAY(1,2,3,4,5,6,7) WHERE available_weekdays IS NULL"))
    else:
        weekdays = json.dumps([1, 2, 3, 4, 5, 6, 7])
        op.execute(sa.text("UPDATE study_plans SET available_weekdays=:days WHERE available_weekdays IS NULL").bindparams(days=weekdays))
    if dialect == "mysql":
        op.alter_column("study_plans", "plan_type", existing_type=sa.String(20), nullable=False, server_default="single")
        op.alter_column("study_plans", "version", existing_type=sa.Integer(), nullable=False, server_default="1")
        op.alter_column("study_plans", "available_weekdays", existing_type=sa.JSON(), nullable=False)

    names = _indexes("study_plans")
    if "ix_study_plans_plan_type" not in names:
        op.create_index("ix_study_plans_plan_type", "study_plans", ["plan_type"])
    if "uq_study_plans_user_request" not in names:
        if op.get_bind().dialect.name == "sqlite":
            op.create_index("uq_study_plans_user_request", "study_plans", ["user_id", "client_request_id"], unique=True)
        else:
            op.create_unique_constraint("uq_study_plans_user_request", "study_plans", ["user_id", "client_request_id"])

    Base.metadata.create_all(bind=op.get_bind(), tables=[Base.metadata.tables[name] for name in NEW_TABLES], checkfirst=True)


def downgrade() -> None:
    # Only 1.1 additions are removed. Baseline tables and existing business rows remain.
    existing = set(inspect(op.get_bind()).get_table_names())
    for table in reversed(NEW_TABLES):
        if table in existing:
            op.drop_table(table)
    names = _indexes("study_plans")
    if "uq_study_plans_user_request" in names:
        if op.get_bind().dialect.name == "sqlite":
            op.drop_index("uq_study_plans_user_request", table_name="study_plans")
        else:
            op.drop_constraint("uq_study_plans_user_request", "study_plans", type_="unique")
    if "ix_study_plans_plan_type" in names:
        op.drop_index("ix_study_plans_plan_type", table_name="study_plans")
    for table, column in (
        ("study_plans", "available_weekdays"), ("study_plans", "client_request_id"),
        ("study_plans", "version"), ("study_plans", "plan_type"),
        ("chat_messages", "agent_trace"), ("users", "avatar_data"),
    ):
        if column in _columns(table):
            op.drop_column(table, column)
