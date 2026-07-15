import os
from typing import Any


from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
)
from sqlalchemy.orm import Session

from app.agent.agent_kernel.config import init_model as get_chat_model
from app.services.citation_service import (
    build_agent_citation_context,
    retrieve_course_chunks,
)


SYSTEM_PROMPT = """
你是课程学习助手。

你必须严格根据系统提供的课程资料片段回答问题。

回答规则：
1. 不得编造课程资料中没有出现的事实。
2. 优先直接回答用户问题，再进行必要解释。
3. 引用资料时使用 [C1]、[C2] 这样的编号。
4. 引用编号必须与提供的资料片段编号一致。
5. 如果资料不足以回答，应明确说明“当前课程资料不足以回答该问题”。
6. 使用清晰、准确、适合大学生学习的中文。
7. 不要声称自己查阅了未提供的教材、网页或其他外部资料。
""".strip()


def _build_context(search_results: list[dict[str, Any]]) -> str:
    """
    将语义检索结果转换成提供给大模型的课程资料上下文。
    """
    return build_agent_citation_context(search_results)


def _build_citations(
    search_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    把检索结果转换成接口返回的引用列表。
    """
    return list(search_results)

def _convert_history_to_messages(
    history: list[dict[str, str]],
):
    messages = []

    for item in history:
        role = item.get("role")
        content = item.get("content", "").strip()

        if not content:
            continue

        if role == "user":
            messages.append(
                HumanMessage(content=content)
            )

        elif role == "assistant":
            messages.append(
                AIMessage(content=content)
            )

    return messages

def answer_course_question(
    db: Session,
    *,
    user_id: int,
    course_id: int,
    message: str,
    top_k: int | None = None,
    history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """
    完成一次基于课程资料的 RAG 问答。
    """
    message = message.strip()

    if not message:
        raise ValueError("问题不能为空")

    if top_k is None:
        top_k = int(os.getenv("RAG_TOP_K", "5"))

    search_results = retrieve_course_chunks(
        db,
        user_id=user_id,
        course_id=course_id,
        query=message,
        top_k=top_k,
    )

    if not search_results:
        return {
            "course_id": course_id,
            "answer": "当前课程还没有可用于回答该问题的资料。",
            "citations": [],
        }

    context = _build_context(search_results)

    user_prompt = f"""
以下是从当前课程资料中检索出的内容：

{context}

用户问题：
{message}

请严格基于以上课程资料回答问题，并在对应内容后标注引用编号。
""".strip()

    llm = get_chat_model()

    llm_messages = [
        SystemMessage(content=SYSTEM_PROMPT)
    ]

    if history:
        llm_messages.extend(
            _convert_history_to_messages(history)
        )

    llm_messages.append(
        HumanMessage(content=user_prompt)
    )

    response = llm.invoke(llm_messages)

    if isinstance(response.content, str):
        answer = response.content.strip()
    else:
        answer = str(response.content).strip()

    if not answer:
        raise RuntimeError("大模型返回了空内容")

    return {
        "course_id": course_id,
        "answer": answer,
        "citations": _build_citations(search_results),
    }
