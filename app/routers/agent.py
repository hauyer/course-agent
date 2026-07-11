import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.agent import (
    AgentChatRequest,
    AgentChatResponse,
    ChatMessageResponse,
    ChatSessionResponse,
)
from app.services.agent_service import answer_course_question
from app.services.auth_service import get_current_user
from app.services.chat_service import (
    create_chat_session,
    delete_chat_session,
    get_chat_session,
    get_recent_messages,
    list_chat_messages,
    list_chat_sessions,
    save_chat_exchange,
)
from app.services.course_service import get_course_by_id


logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/agent/chat",
    response_model=AgentChatResponse,
    summary="基于课程资料进行多轮 Agent 问答",
)
def agent_chat(
    chat_in: AgentChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    course = get_course_by_id(
        db=db,
        user_id=current_user.id,
        course_id=chat_in.course_id,
    )

    if course is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="课程不存在或无权限访问",
        )

    created_new_session = False

    if chat_in.session_id is None:
        session = create_chat_session(
            db=db,
            user_id=current_user.id,
            course_id=chat_in.course_id,
            first_message=chat_in.message,
        )
        created_new_session = True

    else:
        session = get_chat_session(
            db=db,
            user_id=current_user.id,
            session_id=chat_in.session_id,
        )

        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="对话会话不存在或无权限访问",
            )

        if session.course_id != chat_in.course_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="当前会话不属于指定课程",
            )

    history_rows = get_recent_messages(
        db=db,
        session_id=session.id,
        limit=10,
    )

    history = [
        {
            "role": item.role,
            "content": item.content,
        }
        for item in history_rows
    ]

    try:
        result = answer_course_question(
            db=db,
            user_id=current_user.id,
            course_id=chat_in.course_id,
            message=chat_in.message,
            top_k=chat_in.top_k,
            history=history,
        )

        user_message, assistant_message = save_chat_exchange(
            db=db,
            session=session,
            user_content=chat_in.message,
            assistant_content=result["answer"],
            citations=result["citations"],
        )

        return {
            "session_id": session.id,
            "course_id": chat_in.course_id,
            "user_message_id": user_message.id,
            "assistant_message_id": assistant_message.id,
            "answer": result["answer"],
            "citations": result["citations"],
        }

    except ValueError as exc:
        if created_new_session:
            delete_chat_session(db=db, session=session)

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    except RuntimeError as exc:
        if created_new_session:
            delete_chat_session(db=db, session=session)

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        if created_new_session:
            delete_chat_session(db=db, session=session)

        logger.exception("Agent 问答执行失败")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Agent 问答执行失败，请查看后端日志",
        ) from exc


@router.get(
    "/agent/sessions",
    response_model=list[ChatSessionResponse],
    summary="查看当前用户的对话列表",
)
def get_agent_sessions(
    course_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return list_chat_sessions(
        db=db,
        user_id=current_user.id,
        course_id=course_id,
    )


@router.get(
    "/agent/sessions/{session_id}/messages",
    response_model=list[ChatMessageResponse],
    summary="查看指定对话的全部消息",
)
def get_agent_session_messages(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = get_chat_session(
        db=db,
        user_id=current_user.id,
        session_id=session_id,
    )

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="对话会话不存在或无权限访问",
        )

    return list_chat_messages(
        db=db,
        session_id=session.id,
    )


@router.delete(
    "/agent/sessions/{session_id}",
    summary="删除指定对话",
)
def delete_agent_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = get_chat_session(
        db=db,
        user_id=current_user.id,
        session_id=session_id,
    )

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="对话会话不存在或无权限访问",
        )

    delete_chat_session(
        db=db,
        session=session,
    )

    return {
        "message": "对话删除成功"
    }