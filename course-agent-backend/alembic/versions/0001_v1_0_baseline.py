"""Represent the stable 1.0 schema baseline without dropping existing data."""

from alembic import op
from app.database import Base
import app.models  # noqa: F401

revision = "0001_v1_0_baseline"
down_revision = None
branch_labels = None
depends_on = None

V1_TABLES = (
    "users", "courses", "materials", "material_chunks", "chat_sessions",
    "chat_messages", "tasks", "study_plans", "study_plan_tasks", "notes",
    "note_sync_records", "learning_records", "course_progresses",
    "integration_configs", "llm_configs", "agent_memories", "audit_logs",
)


def upgrade() -> None:
    tables = [Base.metadata.tables[name] for name in V1_TABLES]
    Base.metadata.create_all(bind=op.get_bind(), tables=tables, checkfirst=True)


def downgrade() -> None:
    # Never remove the stable 1.0 business schema or user data.
    pass
