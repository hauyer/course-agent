from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.chat_message import ChatMessage
from app.models.chat_session import ChatSession


def generate_session_title(message: str) -> str:
    """
    根据第一次提问生成简短会话标题。
    """
    normalized = " ".join(message.strip().split())

    if not normalized:
        return "新对话"

    if len(normalized) <= 30:
        return normalized

    return normalized[:30] + "..."


def create_chat_session(
    db: Session,
    *,
    user_id: int,
    course_id: int,
    first_message: str,
) -> ChatSession:
    session = ChatSession(
        user_id=user_id,
        course_id=course_id,
        title=generate_session_title(first_message),
        status="active",
    )

    db.add(session)
    db.commit()
    db.refresh(session)

    return session


def get_chat_session(
    db: Session,
    *,
    user_id: int,
    session_id: int,
) -> ChatSession | None:
    return (
        db.query(ChatSession)
        .filter(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id,
        )
        .first()
    )


def list_chat_sessions(
    db: Session,
    *,
    user_id: int,
    course_id: int | None = None,
) -> list[ChatSession]:
    query = db.query(ChatSession).filter(
        ChatSession.user_id == user_id
    )

    if course_id is not None:
        query = query.filter(
            ChatSession.course_id == course_id
        )

    return (
        query.order_by(ChatSession.updated_at.desc())
        .all()
    )


def get_recent_messages(
    db: Session,
    *,
    session_id: int,
    limit: int = 10,
) -> list[ChatMessage]:
    """
    获取最近若干条消息，并恢复为正序。
    """
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.id.desc())
        .limit(limit)
        .all()
    )

    messages.reverse()
    return messages


def list_chat_messages(
    db: Session,
    *,
    session_id: int,
) -> list[ChatMessage]:
    return (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.id.asc())
        .all()
    )


def save_chat_exchange(
    db: Session,
    *,
    session: ChatSession,
    user_content: str,
    assistant_content: str,
    citations: list[dict[str, Any]],
) -> tuple[ChatMessage, ChatMessage]:
    """
    一次性保存用户问题和 Agent 回答。
    """
    user_message = ChatMessage(
        session_id=session.id,
        role="user",
        content=user_content,
        citations=None,
    )

    assistant_message = ChatMessage(
        session_id=session.id,
        role="assistant",
        content=assistant_content,
        citations=citations,
    )

    session.updated_at = datetime.now(timezone.utc)

    db.add(user_message)
    db.add(assistant_message)
    db.add(session)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(user_message)
    db.refresh(assistant_message)
    db.refresh(session)

    return user_message, assistant_message


def delete_chat_session(
    db: Session,
    *,
    session: ChatSession,
) -> None:
    """
    删除会话及其全部消息。
    """
    (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session.id)
        .delete(synchronize_session=False)
    )

    db.delete(session)
    db.commit()