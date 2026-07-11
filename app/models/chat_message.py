from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.sql import func

from app.database import Base


class ChatMessage(Base):
    """对话中的单条用户消息或 Agent 消息。"""

    __tablename__ = "chat_messages"

    __table_args__ = (
        Index(
            "ix_chat_messages_session_created",
            "session_id",
            "created_at",
        ),
    )

    id = Column(
        Integer,
        primary_key=True,
        index=True,
        autoincrement=True,
    )

    session_id = Column(
        Integer,
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # user、assistant、system
    role = Column(
        String(20),
        nullable=False,
        index=True,
    )

    content = Column(
        LONGTEXT,
        nullable=False,
    )

    # Agent 回答引用的资料片段列表
    citations = Column(
        JSON,
        nullable=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )