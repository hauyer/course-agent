import { useEffect, useRef, useState, type FormEvent } from "react";
import { Check, MessageSquareText, Plus, RefreshCw, Sparkles, Trash2 } from "lucide-react";

import { api, streamAgent, type Entity } from "../../api";
import MarkdownContent from "../../components/MarkdownContent";
import "./chat.css";

function unwrap(data: any): Entity[] {
  return Array.isArray(data) ? data : data?.items || [];
}
function errorText(error: unknown) {
  return error instanceof Error ? error.message : "操作失败";
}
function dateText(value?: string) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}
function useData<T>(loader: () => Promise<T>, deps: any[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let live = true;
    loader().then((value) => live && setData(value)).catch(() => undefined);
    return () => { live = false; };
  }, [...deps, tick]);
  return { data, reload: () => setTick((value) => value + 1) };
}
function CourseSelect({ courses, value, onChange }: { courses: Entity[]; value?: any; onChange: (value: string) => void }) {
  return <select value={value || ""} onChange={(event) => onChange(event.target.value)} required>
    <option value="">选择课程</option>
    {courses.map((course) => <option key={course.id} value={course.id}>{course.name}</option>)}
  </select>;
}

function UserAvatar({ user }: { user: Entity | null }) {
  if (user?.avatar_data) {
    return <img src={String(user.avatar_data)} alt="用户头像" />;
  }
  return <span>{String(user?.username || "你").slice(0, 1).toUpperCase()}</span>;
}

function CitationReferences({ items }: { items: Entity[] }) {
  if (!items.length) return null;
  const groups = items.reduce<Record<string, Entity[]>>((result, item) => {
    const key = `${item.course_id || 0}:${item.material_id || 0}`;
    (result[key] ||= []).push(item);
    return result;
  }, {});
  return (
    <details className="citation-references">
      <summary>参考资料 · {items.length} 条真实检索片段</summary>
      <div className="citation-groups">
        {Object.entries(groups).map(([key, citations]) => (
          <section className="citation-group" key={key}>
            <header>
              <span>{citations[0].course_name}</span>
              <b>{citations[0].material_title}</b>
            </header>
            {citations.map((citation) => (
              <details className="citation" key={citation.chunk_id}>
                <summary>
                  <b>[{citation.citation_id || `C${citation.index}`}]</b>
                  <span>
                    {citation.page_no !== null && citation.page_no !== undefined
                      ? `第 ${citation.page_no} 页 · `
                      : ""}
                    片段 {citation.chunk_index} · 相关度 {Math.round(Number(citation.similarity_score || 0) * 100)}%
                  </span>
                </summary>
                <p>{String(citation.content || "")}</p>
              </details>
            ))}
          </section>
        ))}
      </div>
    </details>
  );
}

function AgentActivity({
  items,
  compact = false,
}: {
  items: Entity[];
  compact?: boolean;
}) {
  if (!items.length) {
    return (
      <div className="agent-activity is-waiting">
        <div>
          <RefreshCw className="spin" size={13} />
          <span>理解需求并选择助手</span>
        </div>
      </div>
    );
  }
  return (
    <div className={`agent-activity ${compact ? "compact" : ""}`}>
      {items.map((item, index) => (
        <div
          key={item.id || item.run_id || `${item.type || "step"}-${index}`}
          className={item.status === "done" ? "done" : "running"}
        >
          <span className="activity-mark">
            {item.status === "done" ? (
              <Check size={12} />
            ) : (
              <RefreshCw className="spin" size={12} />
            )}
          </span>
          <div>
            <b>{item.name}</b>
            {item.detail &&
              (typeof item.detail !== "object" ||
                Object.keys(item.detail).length > 0) && (
              <small>
                {typeof item.detail === "object"
                  ? Object.values(item.detail).slice(0, 2).join(" · ")
                  : String(item.detail)}
              </small>
            )}
            {item.result && compact && (
              <p>{String(item.result).slice(0, 180)}</p>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

export default function ChatPage({ notify }: { notify: (s: string) => void }) {
  const currentUser = (() => {
    try {
      return JSON.parse(localStorage.getItem("current_user") || "null");
    } catch {
      return null;
    }
  })();
  const courses = useData(() => api.courses(), []),
    [cid, setCid] = useState<number>(0),
    sessions = useData(
      () => (cid ? api.sessions(cid) : Promise.resolve([])),
      [cid],
    ),
    [sid, setSid] = useState<number | undefined>(),
    [messages, setMessages] = useState<Entity[]>([]),
    [input, setInput] = useState(""),
    [busy, setBusy] = useState(false),
    [activities, setActivities] = useState<Entity[]>([]),
    [streamText, setStreamText] = useState("");
  const keepImmediateResultForSession = useRef<number | undefined>(undefined);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const agentNames: Record<string, string> = {
    course_agent: "课程助手",
    course_agent_node: "课程助手",
    concept_agent: "知识助手",
    concept_agent_node: "知识助手",
    material_agent: "资料助手",
    material_agent_node: "资料助手",
    plan_agent: "规划助手",
    plan_agent_node: "规划助手",
    learning_agent: "学习记录助手",
    learning_agent_node: "学习记录助手",
    note_agent: "笔记助手",
    note_agent_node: "笔记助手",
    chat_agent: "对话助手",
    chat_agent_node: "对话助手",
  };
  const hydrateMessages = (rows: Entity[]) =>
    rows.map((message) => {
      const stored = Array.isArray(message.citations) ? message.citations : [];
      const legacyTrace = stored.filter((item: Entity) => item.kind === "agent_trace");
      return {
        ...message,
        citations: stored.filter((item: Entity) => item.kind !== "agent_trace"),
        activities: Array.isArray(message.agent_trace)
          ? message.agent_trace
          : legacyTrace,
      };
    });
  useEffect(() => {
    if (!cid && courses.data?.[0]) setCid(courses.data[0].id);
  }, [courses.data, cid]);
  useEffect(() => {
    if (!sid) {
      setMessages([]);
      return;
    }
    // A newly-created session already has the richer local result, including
    // the live tool trace. Do not immediately replace it with the persisted
    // message shape, which intentionally stores only the conversation body.
    if (keepImmediateResultForSession.current === sid) {
      keepImmediateResultForSession.current = undefined;
      return;
    }
    api.messages(sid).then((x: any) => setMessages(hydrateMessages(unwrap(x))));
  }, [sid]);
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: busy ? "auto" : "smooth" });
  }, [messages, busy, activities, streamText]);
  const send = async (e: FormEvent) => {
    e.preventDefault();
    if (!input.trim() || !cid) return;
    const text = input;
    setInput("");
    setMessages((m) => [
      ...m,
      { id: `u${Date.now()}`, role: "user", content: text },
    ]);
    setBusy(true);
    setActivities([]);
    setStreamText("");
    let runActivities: Entity[] = [];
    let streamed = "";
    try {
      const r: any = await streamAgent(
        {
          course_id: cid,
          session_id: sid || null,
          message: text,
          top_k: 5,
        },
        (event) => {
          if (event.type === "model_start") {
            runActivities = [
              ...runActivities,
              {
                id: event.run_id || `${Date.now()}-${runActivities.length}`,
                run_id: event.run_id,
                type: "agent",
                name: agentNames[event.node] || "课程 Agent",
                detail: "正在分析请求并确定下一步",
                status: "running",
              },
            ];
            setActivities([...runActivities]);
          } else if (event.type === "model_end") {
            runActivities = runActivities.map((item) =>
              item.run_id === event.run_id
                ? {
                    ...item,
                    status: "done",
                    detail: event.final ? "已组织最终回答" : "已确定工具调用",
                  }
                : item,
            );
            if (event.final && event.content) {
              streamed = String(event.content);
              setStreamText(streamed);
            }
            setActivities([...runActivities]);
          } else if (event.type === "operation") {
            runActivities = [
              ...runActivities,
              {
                id: `${Date.now()}-${runActivities.length}`,
                type: "tool",
                name: event.name,
                detail: event.detail,
                status: "running",
              },
            ];
            setActivities([...runActivities]);
          } else if (event.type === "tool_result") {
            const pendingIndex = [...runActivities]
              .map((item, index) => ({ item, index }))
              .reverse()
              .find(({ item }) => item.status === "running")?.index;
            if (pendingIndex !== undefined) {
              runActivities = runActivities.map((item, index) =>
                index === pendingIndex
                  ? { ...item, status: "done", result: event.content }
                  : item,
              );
            } else {
              runActivities = [
                ...runActivities,
                {
                  id: `${Date.now()}-result`,
                  name: "已完成操作",
                  status: "done",
                  result: event.content,
                },
              ];
            }
            setActivities([...runActivities]);
          } else if (
            event.type === "token" &&
            (event.node === "chat_agent" || event.node === "chat_agent_node")
          ) {
            streamed += String(event.content || "");
            setStreamText(streamed);
          }
        },
      );
      if (r.session_id !== sid) {
        keepImmediateResultForSession.current = r.session_id;
      }
      setSid(r.session_id);
      setMessages((m) => [
        ...m,
        {
          id: r.assistant_message_id,
          role: "assistant",
          content: r.answer || streamed || "操作已完成",
          citations: r.citations,
          activities: r.agent_trace?.length ? r.agent_trace : runActivities,
        },
      ]);
      sessions.reload();
    } catch (x) {
      notify(errorText(x));
    } finally {
      setBusy(false);
      setActivities([]);
      setStreamText("");
    }
  };
  return (
    <div className="chat-layout">
      <aside className="sessions">
        <div>
          <CourseSelect
            courses={courses.data || []}
            value={cid}
            onChange={(v) => {
              if (busy) return;
              setCid(Number(v));
              setSid(undefined);
            }}
          />
          <button
            className="btn primary wide"
            disabled={busy}
            onClick={() => {
              setSid(undefined);
              setMessages([]);
              setInput("");
            }}
          >
            <Plus size={15} />
            新对话
          </button>
        </div>
        <div>
          {unwrap(sessions.data).map((s) => (
            <button
              key={s.id}
              className={sid === s.id ? "active" : ""}
              disabled={busy}
              onClick={() => {
                if (!busy) setSid(s.id);
              }}
            >
              <MessageSquareText size={15} />
              <span>
                <b>{s.title}</b>
                <small>{dateText(s.updated_at)}</small>
              </span>
              <Trash2
                size={13}
                onClick={async (e) => {
                  e.stopPropagation();
                  if (busy) return;
                  await api.deleteSession(s.id);
                  if (sid === s.id) setSid(undefined);
                  sessions.reload();
                }}
              />
            </button>
          ))}
        </div>
      </aside>
      <section className="conversation">
        <div className="messages">
          {messages.length ? (
            messages.map((m, i) => (
              <div className={`message ${m.role}`} key={m.id || i}>
                <div className="message-role">
                  {m.role === "user" ? <UserAvatar user={currentUser} /> : <Sparkles size={15} />}
                </div>
                <div>
                  {m.activities?.length > 0 && (
                    <details className="agent-run-summary">
                      <summary>
                        查看 Agent 工作过程 · {m.activities.length} 个步骤
                      </summary>
                      <AgentActivity items={m.activities} compact />
                    </details>
                  )}
                  {m.role === "assistant" ? (
                    <MarkdownContent content={String(m.content || "")} />
                  ) : (
                    <p>{m.content}</p>
                  )}
                  <CitationReferences items={m.citations || []} />
                </div>
              </div>
            ))
          ) : (
            <div className="chat-empty">
              <div className="chat-seal">
                <Sparkles size={25} />
              </div>
              <h2>从课程资料开始提问</h2>
              <p>回答会标注引用的资料片段，方便回到原文核对。</p>
              <div>
                <button
                  onClick={() => setInput("总结这门课程资料的核心知识框架")}
                >
                  梳理知识框架
                </button>
                <button
                  onClick={() => setInput("列出目前资料中最容易混淆的概念")}
                >
                  辨析易混概念
                </button>
                <button
                  onClick={() =>
                    setInput("把这门课程接下来要做的事情整理成任务")
                  }
                >
                  安排任务
                </button>
                <button
                  onClick={() => setInput("为这门课程创建一篇本周学习复盘笔记")}
                >
                  创建复盘笔记
                </button>
              </div>
            </div>
          )}
          {busy && (
            <div className="message assistant agent-running">
              <div className="message-role">
                <Sparkles size={15} />
              </div>
              <div>
                <details className="agent-thinking-live" open>
                  <summary>
                    <span className="live-dot" />
                    Agent 正在工作 · 点击收起
                  </summary>
                  <AgentActivity items={activities} />
                </details>
                {streamText && <MarkdownContent content={streamText} compact />}
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>
        <form className="composer" onSubmit={send}>
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                e.currentTarget.form?.requestSubmit();
              }
            }}
            placeholder="输入问题，Enter 发送，Shift + Enter 换行"
          />
          <button className="btn primary" disabled={busy || !cid}>
            发送
          </button>
        </form>
      </section>
    </div>
  );
}
