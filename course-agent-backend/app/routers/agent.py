import asyncio
import json
import logging
import time
from uuid import uuid4
from functools import lru_cache
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
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
    save_assistant_message,
    save_user_message,
)
from app.services.audit_service import write_audit_log
from app.services.course_service import get_course_by_id
from app.services.llm_config_service import (
    load_user_llm_runtime,
    reset_active_llm_runtime,
    set_active_llm_runtime,
)
from app.agent.citations import (
    CitationCollector,
    activate_citation_collector,
    reset_citation_collector,
)
from app.services.citation_service import (
    build_agent_citation_context,
    retrieve_course_chunks,
    sanitize_answer_citation_markers,
)


logger = logging.getLogger(__name__)

router = APIRouter()
_session_locks: dict[int, asyncio.Lock] = {}


def _session_lock(session_id: int) -> asyncio.Lock:
    lock = _session_locks.get(session_id)
    if lock is None:
        lock = asyncio.Lock()
        _session_locks[session_id] = lock
    return lock


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
    course_id: int,
    top_k: int,
    history: list[dict],
    citation_context: str,
) -> AsyncIterator[dict]:
    interface = get_agent_interface()
    runtime_token = set_active_llm_runtime(load_user_llm_runtime(user_id))
    try:
        async for event in interface._run_stream(
            message=message,
            user_id=str(user_id),
            # 每轮使用独立图线程，数据库消息作为权威上下文来源。这样既不会
            # 重复叠加检查点，也能在桌面后端重启后继续同一场对话。
            thread_id=f"{session_id}:{uuid4().hex}",
            course_id=str(course_id),
            top_k=top_k,
            history=history,
            citation_context=citation_context,
        ):
            yield event
    finally:
        reset_active_llm_runtime(runtime_token)


_NODE_LABELS = {
    "course_agent": "课程助手",
    "course_agent_node": "课程助手",
    "concept_agent": "知识助手",
    "concept_agent_node": "知识助手",
    "material_agent": "资料助手",
    "material_agent_node": "资料助手",
    "plan_agent": "规划助手",
    "plan_agent_node": "规划助手",
    "learning_agent": "学习记录助手",
    "learning_agent_node": "学习记录助手",
    "note_agent": "笔记助手",
    "note_agent_node": "笔记助手",
    "chat_agent": "对话助手",
    "chat_agent_node": "对话助手",
}


def _history_payload(messages) -> list[dict]:
    return [{"role": item.role, "content": item.content} for item in messages]


def _request_citation_context(
    db: Session,
    *,
    user_id: int,
    course_id: int,
    message: str,
    top_k: int,
) -> str:
    try:
        citations = retrieve_course_chunks(
            db,
            user_id=user_id,
            course_id=course_id,
            query=message,
            top_k=top_k,
        )
    except Exception as exc:
        logger.warning("课程引用检索不可用: %s", type(exc).__name__)
        return ""
    return build_agent_citation_context(citations)


def _record_trace(trace: list[dict], event: dict) -> None:
    kind = event.get("type")
    run_id = str(event.get("run_id", ""))
    node = str(event.get("node", ""))
    if kind == "model_start":
        trace.append({
            "kind": "agent_trace",
            "type": "agent",
            "run_id": run_id,
            "node": node,
            "name": _NODE_LABELS.get(node, "课程 Agent"),
            "detail": "正在分析请求并确定下一步",
            "status": "running",
        })
    elif kind == "model_end":
        for item in reversed(trace):
            if item.get("run_id") == run_id and item.get("type") == "agent":
                item["status"] = "done"
                item["detail"] = "已组织最终回答" if event.get("final") else "已确定工具调用"
                break
    elif kind == "operation":
        trace.append({
            "kind": "agent_trace",
            "type": "tool",
            "node": node,
            "name": str(event.get("name") or "正在调用工具"),
            "detail": event.get("detail") or {},
            "status": "running",
        })
    elif kind == "tool_result":
        result = str(event.get("content") or "")
        for item in reversed(trace):
            if item.get("type") == "tool" and item.get("status") == "running":
                item["status"] = "done"
                item["result"] = result[:800]
                break


def _finish_trace(trace: list[dict]) -> None:
    for item in trace:
        if item.get("status") == "running":
            item["status"] = "done"


def _new_metrics() -> dict[str, int]:
    return {
        "model_calls": 0,
        "tool_calls": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "tool_errors": 0,
    }


def _record_metrics(metrics: dict[str, int], event: dict) -> None:
    if event.get("type") == "model_start":
        metrics["model_calls"] += 1
    elif event.get("type") == "operation":
        metrics["tool_calls"] += 1
    elif event.get("type") == "tool_result":
        content = str(event.get("content") or "").lower()
        if event.get("error") or any(
            marker in content
            for marker in ("tool error", "exception", "traceback", "调用失败", "工具失败")
        ):
            metrics["tool_errors"] += 1
    elif event.get("type") == "model_end":
        usage = event.get("usage") or {}
        metrics["prompt_tokens"] += int(usage.get("input_tokens", 0) or 0)
        metrics["completion_tokens"] += int(usage.get("output_tokens", 0) or 0)


def _write_agent_audit(
    *,
    trace_id: str,
    user_id: int,
    session_id: int,
    course_id: int,
    started: float,
    metrics: dict[str, int],
    status_code: int,
    error: Exception | None = None,
) -> None:
    write_audit_log(
        trace_id=trace_id,
        user_id=user_id,
        category="agent",
        method="POST",
        path="/api/agent/chat",
        status_code=status_code,
        duration_ms=(time.perf_counter() - started) * 1000,
        model_calls=metrics["model_calls"],
        tool_calls=metrics["tool_calls"],
        prompt_tokens=metrics["prompt_tokens"],
        completion_tokens=metrics["completion_tokens"],
        error_count=metrics["tool_errors"] + (1 if error else 0),
        summary=f"课程 {course_id} · 会话 {session_id}",
        error_detail=(f"{type(error).__name__}: {str(error)[:1800]}" if error else None),
    )


@router.post(
    "/agent/chat",
    response_model=AgentChatResponse,
    summary="基于课程资料进行多轮 Agent 问答",
)
async def agent_chat(
    chat_in: AgentChatRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session, created_new_session = _prepare_session(chat_in, db, current_user)
    trace_id = getattr(request.state, "trace_id", uuid4().hex)
    started = time.perf_counter()
    metrics = _new_metrics()

    try:
        collector = CitationCollector()
        collector_token = activate_citation_collector(collector)
        try:
            async with _session_lock(session.id):
                history = _history_payload(
                    get_recent_messages(db, session_id=session.id, limit=24)
                )
                citation_context = _request_citation_context(
                    db,
                    user_id=current_user.id,
                    course_id=chat_in.course_id,
                    message=chat_in.message,
                    top_k=chat_in.top_k,
                )
                user_message = save_user_message(
                    db=db, session=session, content=chat_in.message
                )
                answer = ""
                fallback_by_run: dict[str, str] = {}
                trace: list[dict] = []
                async for event in _agent_events(
                    message=chat_in.message,
                    user_id=current_user.id,
                    session_id=session.id,
                    course_id=chat_in.course_id,
                    top_k=chat_in.top_k,
                    history=history,
                    citation_context=citation_context,
                ):
                    _record_trace(trace, event)
                    _record_metrics(metrics, event)
                    if event.get("type") == "token":
                        run_id = str(event.get("run_id", ""))
                        fallback_by_run[run_id] = fallback_by_run.get(run_id, "") + str(event.get("content", ""))
                    elif event.get("type") == "model_end" and event.get("final"):
                        candidate = str(event.get("content", "")).strip()
                        if candidate:
                            answer = candidate

                if not answer and fallback_by_run:
                    answer = next((v.strip() for v in reversed(fallback_by_run.values()) if v.strip()), "")
                if not answer:
                    raise RuntimeError("AgentInterface 没有返回回答内容")

                citations = collector.snapshot()
                answer = sanitize_answer_citation_markers(answer, citations)
                _finish_trace(trace)
                assistant_message = save_assistant_message(
                    db=db,
                    session=session,
                    content=answer,
                    citations=citations,
                    agent_trace=trace,
                )
        finally:
            reset_citation_collector(collector_token)

        _write_agent_audit(
            trace_id=trace_id,
            user_id=current_user.id,
            session_id=session.id,
            course_id=chat_in.course_id,
            started=started,
            metrics=metrics,
            status_code=200,
        )

        return {
            "session_id": session.id,
            "course_id": chat_in.course_id,
            "user_message_id": user_message.id,
            "assistant_message_id": assistant_message.id,
            "answer": answer,
            "citations": citations,
            "agent_trace": trace,
        }

    except ValueError as exc:
        _write_agent_audit(trace_id=trace_id, user_id=current_user.id, session_id=session.id, course_id=chat_in.course_id, started=started, metrics=metrics, status_code=400, error=exc)

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    except RuntimeError as exc:
        _write_agent_audit(trace_id=trace_id, user_id=current_user.id, session_id=session.id, course_id=chat_in.course_id, started=started, metrics=metrics, status_code=503, error=exc)

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        _write_agent_audit(trace_id=trace_id, user_id=current_user.id, session_id=session.id, course_id=chat_in.course_id, started=started, metrics=metrics, status_code=500, error=exc)

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
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session, created_new_session = _prepare_session(chat_in, db, current_user)
    trace_id = getattr(request.state, "trace_id", uuid4().hex)

    async def event_generator():
        started = time.perf_counter()
        metrics = _new_metrics()
        answer = ""
        fallback_by_run: dict[str, str] = {}
        trace: list[dict] = []
        collector = CitationCollector()
        collector_token = activate_citation_collector(collector)
        try:
            async with _session_lock(session.id):
                history = _history_payload(
                    get_recent_messages(db, session_id=session.id, limit=24)
                )
                citation_context = _request_citation_context(
                    db,
                    user_id=current_user.id,
                    course_id=chat_in.course_id,
                    message=chat_in.message,
                    top_k=chat_in.top_k,
                )
                user_message = save_user_message(
                    db=db, session=session, content=chat_in.message
                )
                yield "data: " + json.dumps(
                    {
                        "type": "persisted",
                        "session_id": session.id,
                        "course_id": chat_in.course_id,
                        "user_message_id": user_message.id,
                    },
                    ensure_ascii=False,
                ) + "\n\n"
                async for event in _agent_events(
                    message=chat_in.message,
                    user_id=current_user.id,
                    session_id=session.id,
                    course_id=chat_in.course_id,
                    top_k=chat_in.top_k,
                    history=history,
                    citation_context=citation_context,
                ):
                    _record_trace(trace, event)
                    _record_metrics(metrics, event)
                    if event.get("type") == "token":
                        run_id = str(event.get("run_id", ""))
                        fallback_by_run[run_id] = fallback_by_run.get(run_id, "") + str(event.get("content", ""))
                    elif event.get("type") == "model_end" and event.get("final"):
                        candidate = str(event.get("content", "")).strip()
                        if candidate:
                            answer = candidate
                    yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"

                if not answer and fallback_by_run:
                    answer = next((v.strip() for v in reversed(fallback_by_run.values()) if v.strip()), "")
                if not answer:
                    raise RuntimeError("AgentInterface 没有返回回答内容")

                citations = collector.snapshot()
                answer = sanitize_answer_citation_markers(answer, citations)
                _finish_trace(trace)

                assistant_message = save_assistant_message(
                    db=db,
                    session=session,
                    content=answer,
                    citations=citations,
                    agent_trace=trace,
                )
            _write_agent_audit(trace_id=trace_id, user_id=current_user.id, session_id=session.id, course_id=chat_in.course_id, started=started, metrics=metrics, status_code=200)
            yield "data: " + json.dumps(
                {
                    "type": "result",
                    "session_id": session.id,
                    "course_id": chat_in.course_id,
                    "user_message_id": user_message.id,
                    "assistant_message_id": assistant_message.id,
                    "answer": answer,
                    "citations": citations,
                    "agent_trace": trace,
                },
                ensure_ascii=False,
            ) + "\n\n"
            yield "data: [DONE]\n\n"
        except Exception as exc:
            _write_agent_audit(trace_id=trace_id, user_id=current_user.id, session_id=session.id, course_id=chat_in.course_id, started=started, metrics=metrics, status_code=500, error=exc)
            logger.exception("AgentInterface 流式问答执行失败")
            yield "data: " + json.dumps(
                {
                    "type": "error",
                    "message": f"Agent 问答执行失败（追踪号 {trace_id[:12]}）",
                    "trace_id": trace_id,
                    "session_id": session.id,
                    "course_id": chat_in.course_id,
                },
                ensure_ascii=False,
            ) + "\n\n"
        finally:
            reset_citation_collector(collector_token)

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
