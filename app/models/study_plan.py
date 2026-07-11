from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.sql import func

from app.database import Base


class StudyPlan(Base):
    """用户制定的一份学习计划。"""

    __tablename__ = "study_plans"

    __table_args__ = (
        Index(
            "ix_study_plans_user_status",
            "user_id",
            "status",
        ),
        Index(
            "ix_study_plans_user_course",
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

    # 可以是单课程计划，也可以是不绑定课程的综合计划
    course_id = Column(
        Integer,
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    title = Column(
        String(200),
        nullable=False,
    )

    goal = Column(
        Text,
        nullable=True,
    )

    start_date = Column(
        Date,
        nullable=False,
    )

    end_date = Column(
        Date,
        nullable=False,
    )

    # 用户每天计划投入多少分钟
    daily_minutes = Column(
        Integer,
        nullable=False,
        default=60,
    )

    # draft、active、completed、cancelled
    status = Column(
        String(20),
        nullable=False,
        default="draft",
        index=True,
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