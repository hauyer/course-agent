from langgraph.graph import StateGraph, START, END
from app.agent.agent_kernel.state import AgentState
from app.agent.agent_kernel.config import init_model
from app.agent.tools.concept import explain_concept
from langgraph.prebuilt import ToolNode
from langchain_core.messages import SystemMessage

# tools of concept agent
CONCEPT_AGENT_TOOLS = [explain_concept]

tool_node = ToolNode(CONCEPT_AGENT_TOOLS)

CONCEPT_PROMPT = SystemMessage(
    content=(
        "你是课程知识助手。解释课程概念前必须调用 explain_concept 检索当前课程资料。"
        "只能根据工具返回的已验证 [C1]、[C2] 片段回答，并在关键结论后保留对应引用编号。"
        "不得编造引用编号或资料内容；没有结果时明确说明当前课程资料中未检索到足够依据。"
    )
)


def concept_agent_node(state: AgentState):
    # init model
    llm = init_model()
    llm = llm.bind_tools(CONCEPT_AGENT_TOOLS)

    # get resp and return
    resp = llm.invoke([CONCEPT_PROMPT] + state["messages"])
    return {"messages": [resp]}


def should_continue(state: AgentState):
    last_msg = state["messages"][-1]
    if last_msg.tool_calls:
        return "tools"
    return END


# bulid graph
def build_concept_agent():
    builder = StateGraph(AgentState)

    builder.add_node("concept_agent", concept_agent_node)
    builder.add_node("tools", tool_node)

    builder.add_edge(START, "concept_agent")
    builder.add_conditional_edges("concept_agent", should_continue, {"tools": "tools", END: END})
    builder.add_edge("tools", "concept_agent")

    return builder.compile()
