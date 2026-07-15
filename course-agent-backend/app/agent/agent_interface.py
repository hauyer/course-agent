from app.agent.agent_kernel.supervisor import build_supervisor
from langgraph.checkpoint.memory import InMemorySaver
from app.agent.agent_kernel.memory import store
from typing import AsyncIterator
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage


class AgentInterface:
    """后端调用 Agent 模块的唯一入口。"""

    # --- node → 前端展示映射说明 ---
    # 前端可根据 event["node"] 区分思考过程与最终输出。
    # 注意：astream_events 追踪子图内部节点名，不是 supervisor 包装名。
    #
    #   course_agent     → "🧠 课程助手思考中"    可折叠
    #   concept_agent    → "🧠 概念助手思考中"    可折叠
    #   material_agent   → "🧠 资料助手思考中"    可折叠
    #   plan_agent       → "🧠 规划师正在规划"    可折叠
    #   learning_agent   → "🧠 学习助手分析中"    可折叠
    #   note_agent       → "🧠 笔记助手操作中"    可折叠
    #   chat_agent       → 直接展示（非工具逻辑，无需折叠）
    #   tools            → 工具执行中（operation / tool_result）
    #   compress_node    → 系统消息（上下文已压缩） 静默或小字提示
    #
    # 规则：ReAct agent 的 token 流 = 思考过程，chat_agent 的 token 流 = 最终回答。

    def __init__(self):
        self.checkpointer = InMemorySaver()
        self.store = store
        self.graph = build_supervisor(checkpointer=self.checkpointer, store=self.store)

        # 内部节点：用户不需要看到它们产生的 token
        self._SKIP_NODES = {"supervisor_agent", "memory_node", "save_node"}

        # 工具名 → 用户可见的操作描述
        self._TOOL_LABELS = {
            "search_courses": "正在搜索课程",
            "list_all_courses": "正在列出全部课程",
            "create_course": "正在创建课程",
            "search_materials": "正在搜索学习资料",
            "add_material": "正在添加学习资料",
            "list_materials": "正在列出学习资料",
            "explain_concept": "正在查询知识库",
            "create_learning_record": "正在记录本次学习",
            "list_learning_records": "正在整理学习记录",
            "get_learning_summary": "正在汇总学习投入",
            "get_course_progress": "正在读取课程进度",
            "delete_learning_record": "正在删除学习记录",
            "create_note": "正在创建笔记",
            "search_notes": "正在搜索笔记",
            "get_note_detail": "正在读取笔记",
            "update_note": "正在更新笔记",
            "delete_note": "正在删除笔记",
            "sync_note_to_obsidian": "正在同步到 Obsidian",
            "sync_note_to_notion": "正在同步到 Notion",
            "list_note_sync_records": "正在读取同步记录",
            "create_study_plan": "正在创建学习计划",
            "list_study_plans": "正在整理学习计划",
            "get_study_plan_detail": "正在读取计划进度",
            "update_study_plan_status": "正在更新计划状态",
            "delete_study_plan": "正在删除学习计划",
            "create_task": "正在创建任务",
            "list_tasks": "正在整理任务",
            "update_task_status": "正在更新任务状态",
            "delete_task": "正在删除任务",
            "get_dashboard_overview": "正在汇总学习概览",
        }

    @staticmethod
    def _message_from_model_output(output):
        """兼容不同 LangChain 模型的 on_chat_model_end 输出结构。"""
        if output is None:
            return None
        if hasattr(output, "generations"):
            generations = output.generations or []
            if generations:
                first = generations[0]
                if isinstance(first, list):
                    first = first[0] if first else None
                return getattr(first, "message", first)
        return getattr(output, "message", output)

    @staticmethod
    def _content_text(content) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
            return "".join(parts)
        return str(content or "")

    @staticmethod
    def _history_messages(history: list[dict] | None):
        """从数据库恢复上下文，并在过长时压缩早期轮次。

        数据库是跨进程的会话记忆来源；早期消息被压缩为短摘要，最近消息
        保留原文，避免桌面后端重启后丢失上下文或无限增长提示词。
        """
        history = history or []
        recent = history[-10:]
        older = history[:-10]
        result = []
        if older:
            lines = []
            for item in older[-12:]:
                role = "用户" if item.get("role") == "user" else "助手"
                compact = " ".join(str(item.get("content", "")).split())[:220]
                if compact:
                    lines.append(f"{role}：{compact}")
            if lines:
                result.append(SystemMessage(content="[较早对话压缩记录]\n" + "\n".join(lines)))
        for item in recent:
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            result.append(
                HumanMessage(content=content)
                if item.get("role") == "user"
                else AIMessage(content=content)
            )
        return result

    async def _run_stream(
        self,
        message: str,
        user_id: str,
        thread_id: str,
        course_id: str = "",
        top_k: int = 5,
        history: list[dict] | None = None,
        citation_context: str = "",
    ) -> AsyncIterator[dict]:
        """
        流式对话接口，返回异步迭代器供后端通过 SSE 推送给前端。

        参数：
            message   (str)  用户输入的文本
            user_id   (str)  用户 ID
            thread_id (str)  会话 ID，用于隔离不同对话的短期记忆
            course_id (str)  课程 ID，用于限定工具操作的课程范围（可选）

        ── 事件协议（前端请按此解析）──

        所有事件均包含以下公共字段：
            type   (str)  事件类型：token / operation / tool_result
            node   (str)  来源节点，用于区分思考过程与最终回答

        1. token — LLM 逐字输出（打字机效果）
            {
                "type": "token",
                "node": "course_agent",          # 来源节点
                "content": "Python基础课程..."    # 增量文本
            }
            前端判断：node 是 ReAct agent（course_agent、concept_agent 等）
                     → 展示为"思考中"区域，建议可折叠
                     node 是 chat_agent
                     → 展示为最终回答区域

        2. operation — 工具开始执行
            {
                "type": "operation",
                "node": "tools",
                "name": "正在搜索课程",           # 中文操作名
                "detail": {"keyword": "python"}   # 工具入参
            }
            前端建议：展示为状态提示（如 loading 图标 + name）

        3. tool_result — 工具执行完毕
            {
                "type": "tool_result",
                "node": "tools",
                "content": "Python基础(20课时,李老师)..."  # 工具返回文本
            }
            前端建议：展示为可折叠引用块，标注"检索结果"

        4. 流结束 — 后端 SSE 在迭代器耗尽后自行追加
            {"type": "done"}
        """

        context_messages = []
        if citation_context:
            context_messages.append(
                SystemMessage(
                    content=(
                        "[当前课程的已验证资料上下文]\n"
                        "以下片段由系统实际检索并校验。只能使用其中存在的 "
                        "[C1]、[C2] 等编号；不得编造引用。涉及资料内容的关键结论"
                        "应附相应编号。资料不足时明确说明当前课程资料中未检索到足够依据。\n\n"
                        f"{citation_context}"
                    )
                )
            )

        input_data = {
            "messages": context_messages
            + self._history_messages(history)
            + [HumanMessage(content=message)],
            "user_id": user_id,
            "course_id": course_id,
            "top_k": top_k,
        }

        config = {
            "configurable": {
                "thread_id": thread_id,
                "user_id": user_id,
                "course_id": course_id,
                "top_k": top_k,
            }
        }

        async for event in self.graph.astream_events(input_data, config, version="v2"):
            kind = event["event"]

            # metadata.langgraph_node 才是真正的图节点名
            # event["name"] 在 LLM 事件中是模型类名（如 "ChatDeepSeek"），不能用于区分来源
            node = event["metadata"].get("langgraph_node", "")

            if node in self._SKIP_NODES:
                continue

            # LLM 每吐一个 token，触发一次 on_chat_model_stream
            if kind == "on_chat_model_start":
                yield {
                    "type": "model_start",
                    "node": node,
                    "run_id": str(event.get("run_id", "")),
                }

            elif kind == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                if chunk.content:
                    yield {
                        "type": "token",
                        "content": self._content_text(chunk.content),
                        "node": node,
                        "run_id": str(event.get("run_id", "")),
                    }

            elif kind == "on_chat_model_end":
                message_output = self._message_from_model_output(
                    event.get("data", {}).get("output")
                )
                content = self._content_text(getattr(message_output, "content", ""))
                tool_calls = getattr(message_output, "tool_calls", None) or []
                if not tool_calls:
                    additional = getattr(message_output, "additional_kwargs", {}) or {}
                    tool_calls = additional.get("tool_calls", []) or []
                usage = getattr(message_output, "usage_metadata", None) or {}
                yield {
                    "type": "model_end",
                    "node": node,
                    "run_id": str(event.get("run_id", "")),
                    "content": content,
                    "final": not bool(tool_calls),
                    "usage": {
                        "input_tokens": int(usage.get("input_tokens", 0) or 0),
                        "output_tokens": int(usage.get("output_tokens", 0) or 0),
                        "total_tokens": int(usage.get("total_tokens", 0) or 0),
                    },
                }

            # 工具开始执行
            elif kind == "on_tool_start":
                name = event["name"]
                yield {
                    "type": "operation",
                    "name": self._TOOL_LABELS.get(name, name),
                    "detail": event["data"].get("input", {}),
                    "node": node,
                }

            # 工具执行完毕，结果作为 agent 的"思考依据"
            elif kind == "on_tool_end":
                output = event["data"].get("output", "")
                if output:
                    content = output.content if hasattr(output, "content") else str(output)
                    yield {"type": "tool_result", "content": content, "node": node}
