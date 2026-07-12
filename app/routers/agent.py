import json
import logging
from functools import lru_cache
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.agent import (
    AgentChatRequest,
    AgentChatResponse,
    ChatMessageResponse,
    ChatSessionResponse,
)
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


@lru_cache(maxsize=1)
def get_agent_interface():
    """延迟创建组员提供的 AgentInterface，避免导入 API 时初始化 Agent。"""
    from app.agent.agent_interface import AgentInterface

    return AgentInterface()


def _prepare_session(
    chat_in: AgentChatRequest,
    db: Session,
    current_user: User,
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

    if chat_in.session_id is None:
        return (
            create_chat_session(
                db=db,
                user_id=current_user.id,
                course_id=chat_in.course_id,
                first_message=chat_in.message,
            ),
            True,
        )

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

    return session, False


async def _agent_events(
    *,
    message: str,
    user_id: int,
    session_id: int,
) -> AsyncIterator[dict]:
    interface = get_agent_interface()
    async for event in interface._run_stream(
        message=message,
        user_id=str(user_id),
        thread_id=str(session_id),
    ):
        yield event


@router.post(
    "/agent/chat",
    response_model=AgentChatResponse,
    summary="基于课程资料进行多轮 Agent 问答",
)
async def agent_chat(
    chat_in: AgentChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session, created_new_session = _prepare_session(chat_in, db, current_user)

    try:
        answer_parts: list[str] = []
        async for event in _agent_events(
            message=chat_in.message,
            user_id=current_user.id,
            session_id=session.id,
        ):
            if event.get("type") == "token":
                answer_parts.append(str(event.get("content", "")))

        answer = "".join(answer_parts).strip()
        if not answer:
            raise RuntimeError("AgentInterface 没有返回回答内容")

        user_message, assistant_message = save_chat_exchange(
            db=db,
            session=session,
            user_content=chat_in.message,
            assistant_content=answer,
            citations=[],
        )

        return {
            "session_id": session.id,
            "course_id": chat_in.course_id,
            "user_message_id": user_message.id,
            "assistant_message_id": assistant_message.id,
            "answer": answer,
            "citations": [],
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


@router.post(
    "/agent/chat/stream",
    summary="通过 AgentInterface 流式返回 Agent 事件",
)
async def agent_chat_stream(
    chat_in: AgentChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session, created_new_session = _prepare_session(chat_in, db, current_user)

    async def event_generator():
        answer_parts: list[str] = []
        try:
            async for event in _agent_events(
                message=chat_in.message,
                user_id=current_user.id,
                session_id=session.id,
            ):
                if event.get("type") == "token":
                    answer_parts.append(str(event.get("content", "")))
                yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"

            answer = "".join(answer_parts).strip()
            if not answer:
                raise RuntimeError("AgentInterface 没有返回回答内容")

            user_message, assistant_message = save_chat_exchange(
                db=db,
                session=session,
                user_content=chat_in.message,
                assistant_content=answer,
                citations=[],
            )
            yield "data: " + json.dumps(
                {
                    "type": "result",
                    "session_id": session.id,
                    "course_id": chat_in.course_id,
                    "user_message_id": user_message.id,
                    "assistant_message_id": assistant_message.id,
                    "answer": answer,
                    "citations": [],
                },
                ensure_ascii=False,
            ) + "\n\n"
            yield "data: [DONE]\n\n"
        except Exception:
            if created_new_session:
                delete_chat_session(db=db, session=session)
            logger.exception("AgentInterface 流式问答执行失败")
            yield "data: " + json.dumps(
                {"type": "error", "message": "Agent 问答执行失败，请查看后端日志"},
                ensure_ascii=False,
            ) + "\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

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
