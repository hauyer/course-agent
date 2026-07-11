from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.sql import func

from app.database import Base


class ChatSession(Base):
    """用户与课程 Agent 的一次对话会话。"""

    __tablename__ = "chat_sessions"

    __table_args__ = (
        Index(
            "ix_chat_sessions_user_course_updated",
            "user_id",
            "course_id",
            "updated_at",
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

    course_id = Column(
        Integer,
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    title = Column(
        String(120),
        nullable=False,
        default="新对话",
    )

    # active、archived
    status = Column(
        String(20),
        nullable=False,
        default="active",
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