from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.sql import func

from app.database import Base


class Task(Base):
    """课程学习助手中的待办任务。"""

    __tablename__ = "tasks"

    __table_args__ = (
        Index(
            "ix_tasks_user_status_due",
            "user_id",
            "status",
            "due_at",
        ),
        Index(
            "ix_tasks_user_course",
            "user_id",
            "course_id",
        ),
    )

    id = Column(
        Integer,
        primary_key=True,
        index=True,
        autoincrement=True,
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # 通用任务可以不绑定课程
    course_id = Column(
        Integer,
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # 为后续任务拆解预留父子任务关系
    parent_task_id = Column(
        Integer,
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    title = Column(
        String(200),
        nullable=False,
    )

    description = Column(
        Text,
        nullable=True,
    )

    # pending、in_progress、completed、cancelled
    status = Column(
        String(20),
        nullable=False,
        default="pending",
        index=True,
    )

    # low、medium、high、urgent
    priority = Column(
        String(20),
        nullable=False,
        default="medium",
        index=True,
    )

    due_at = Column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    estimated_minutes = Column(
        Integer,
        nullable=True,
    )

    # manual、study_plan、agent
    source = Column(
        String(20),
        nullable=False,
        default="manual",
    )

    completed_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )