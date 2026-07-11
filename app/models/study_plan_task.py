from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from app.database import Base


class StudyPlanTask(Base):
    """
    学习计划和待办任务之间的关联。

    具体任务内容保存在 tasks 表中，
    此表只保存任务属于哪个计划以及安排在哪一天。
    """

    __tablename__ = "study_plan_tasks"

    __table_args__ = (
        UniqueConstraint(
            "study_plan_id",
            "task_id",
            name="uq_study_plan_task",
        ),
        Index(
            "ix_study_plan_tasks_plan_date",
            "study_plan_id",
            "planned_date",
            "sequence_no",
        ),
    )

    id = Column(
        Integer,
        primary_key=True,
        index=True,
        autoincrement=True,
    )

    study_plan_id = Column(
        Integer,
        ForeignKey("study_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    task_id = Column(
        Integer,
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    planned_date = Column(
        Date,
        nullable=False,
        index=True,
    )

    # 同一天中任务的执行顺序
    sequence_no = Column(
        Integer,
        nullable=False,
        default=1,
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )