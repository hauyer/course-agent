import { useState, type FormEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Eye, Library, Pencil, Plus, RefreshCw, Settings2, Trash2, X } from "lucide-react";
import { SiNotion, SiObsidian } from "react-icons/si";
import { api, type Entity } from "../../api";
import MarkdownContent from "../../components/MarkdownContent";
import { useAsyncData as useData } from "../../shared/useAsyncData";

const labels:Record<string,string>={summary:"摘要",knowledge_point:"知识点",review:"复盘"};
function unwrap(data:any):Entity[]{return Array.isArray(data)?data:data?.items||[]}
function errorText(error:unknown){return error instanceof Error?error.message:"操作失败"}
function dayText(value?:string){return value?new Intl.DateTimeFormat("zh-CN",{year:"numeric",month:"2-digit",day:"2-digit"}).format(new Date(value)):"—"}
function Loading({error}:{error?:string}){return <div className="empty"><RefreshCw className="spin" size={20}/><b>{error||"正在整理数据"}</b><span>{error?"检查后端服务后刷新页面":"请稍候"}</span></div>}
function Empty({title,text}:{title:string;text:string}){return <div className="empty"><Library size={24}/><b>{title}</b><span>{text}</span></div>}
function Modal({title,children,onClose,wide=false}:{title:string;children:ReactNode;onClose:()=>void;wide?:boolean}){return createPortal(<div className="modal-backdrop" onMouseDown={onClose}><div className={`modal ${wide?"wide":""}`} onMouseDown={event=>event.stopPropagation()}><div className="modal-head"><h2>{title}</h2><button className="icon-btn" onClick={onClose}><X size={18}/></button></div>{children}</div></div>,document.body)}
function CourseSelect({courses,value,onChange}:{courses:Entity[];value?:any;onChange:(value:string)=>void}){return <select name="course_id" defaultValue={value||""} onChange={event=>onChange(event.target.value)} required><option value="">选择课程</option>{courses.map(course=><option key={course.id} value={course.id}>{course.name}</option>)}</select>}
function FormActions({onCancel,submit}:{onCancel:()=>void;submit:string}){return <div className="form-actions"><button type="button" className="btn subtle" onClick={onCancel}>取消</button><button className="btn primary">{submit}</button></div>}
function Status({value}:{value:string}){return <span className={`status ${value}`}>{labels[value]||value}</span>}


export default function NotesPage({ notify }: { notify: (s: string) => void }) {
  const courses = useData(() => api.courses(), []),
    notes = useData(() => api.notes(), []),
    [edit, setEdit] = useState<Entity | null | undefined>(),
    [view, setView] = useState<Entity | null>(null),
    [settings, setSettings] = useState(false);
  const items = unwrap(notes.data);
  const save = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const b: any = Object.fromEntries(new FormData(e.currentTarget));
    b.course_id = Number(b.course_id);
    b.tags = String(b.tags || "")
      .split(/[,，]/)
      .map((x) => x.trim())
      .filter(Boolean);
    delete b.id;
    try {
      const saved: any = edit?.id
        ? await api.updateNote(edit.id, b)
        : await api.createNote(b);
      setEdit(undefined);
      setView(saved);
      notes.reload();
      notify("笔记已保存");
    } catch (x) {
      notify(errorText(x));
    }
  };
  return (
    <>
      <div className="split-toolbar">
        <div className="integration-actions">
          <button className="btn primary" onClick={() => setSettings(true)}>
            <Settings2 size={15} />
            集成配置
          </button>
          <button
            className="btn subtle"
            onClick={async () => {
              try {
                await api.testIntegration("notion");
                notify("Notion 连接正常");
              } catch (x) {
                notify(errorText(x));
              }
            }}
          >
            <SiNotion size={14} />
            测试 Notion
          </button>
          <button
            className="btn subtle"
            onClick={async () => {
              try {
                await api.testIntegration("obsidian");
                notify("Obsidian 连接正常");
              } catch (x) {
                notify(errorText(x));
              }
            }}
          >
            <SiObsidian size={14} />
            测试 Obsidian
          </button>
        </div>
        <button className="btn primary" onClick={() => setEdit(null)}>
          <Plus size={16} />
          新建笔记
        </button>
      </div>
      {items.length ? (
        <div className="notes-grid">
          {items.map((n) => (
            <article
              key={n.id}
              className="note-card-clickable"
              role="button"
              tabIndex={0}
              onClick={() => setView(n)}
              onKeyDown={(event) => {
                if (
                  event.target === event.currentTarget &&
                  event.key === "Enter"
                )
                  setView(n);
              }}
            >
              <div className="note-meta">
                <Status value={n.note_type} />
                <span>{dayText(n.updated_at)}</span>
              </div>
              <h3>{n.title}</h3>
              <div className="note-rendered-preview">
                <MarkdownContent
                  content={String(n.content_markdown || "空白笔记")}
                  compact
                />
              </div>
              <div className="tags">
                {n.tags?.map((t: string) => (
                  <span key={t}>#{t}</span>
                ))}
              </div>
              <div
                className="card-actions"
                onClick={(event) => event.stopPropagation()}
              >
                <button className="btn subtle" onClick={() => setView(n)}>
                  <Eye size={14} />
                  阅读
                </button>
                <button className="text-btn" onClick={() => setEdit(n)}>
                  <Pencil size={13} />
                  编辑
                </button>
                <button
                  className="text-btn"
                  onClick={async () => {
                    await api.syncNote(n.id, "notion");
                    notify("已同步到 Notion");
                  }}
                >
                  <SiNotion size={13} />
                  Notion
                </button>
                <button
                  className="text-btn"
                  onClick={async () => {
                    await api.syncNote(n.id, "obsidian");
                    notify("已同步到 Obsidian");
                  }}
                >
                  <SiObsidian size={13} />
                  Obsidian
                </button>
                <button
                  className="icon-btn danger"
                  onClick={async () => {
                    if (confirm("删除这篇笔记？")) {
                      await api.deleteNote(n.id);
                      notes.reload();
                    }
                  }}
                >
                  <Trash2 size={15} />
                </button>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <Empty title="还没有笔记" text="记录一次理解，或从课程问答中整理重点" />
      )}
      {view && (
        <Modal title={view.title} onClose={() => setView(null)} wide>
          <div className="note-reader">
            <div className="note-reader-meta">
              <div>
                <Status value={view.note_type} />
                <span>{dayText(view.updated_at)}</span>
              </div>
              <button
                className="btn subtle"
                onClick={() => {
                  setView(null);
                  setEdit(view);
                }}
              >
                <Pencil size={14} />
                编辑笔记
              </button>
            </div>
            <MarkdownContent content={String(view.content_markdown || "")} />
          </div>
        </Modal>
      )}
      {edit !== undefined && (
        <Modal
          title={edit?.id ? "编辑笔记" : "新建笔记"}
          onClose={() => setEdit(undefined)}
          wide
        >
          <form className="form note-form" onSubmit={save}>
            <div className="form-row">
              <label>
                标题
                <input name="title" required defaultValue={edit?.title} />
              </label>
              <label>
                课程
                <CourseSelect
                  courses={courses.data || []}
                  value={edit?.course_id}
                  onChange={() => {}}
                />
              </label>
            </div>
            <div className="form-row">
              <label>
                笔记类型
                <select
                  name="note_type"
                  defaultValue={edit?.note_type || "manual"}
                >
                  <option value="manual">手写笔记</option>
                  <option value="summary">课程摘要</option>
                  <option value="knowledge_point">知识点</option>
                  <option value="review">学习复盘</option>
                </select>
              </label>
              <label>
                标签
                <input
                  name="tags"
                  defaultValue={edit?.tags?.join(", ")}
                  placeholder="用逗号分隔"
                />
              </label>
            </div>
            <label>
              笔记内容
              <textarea
                className="editor"
                name="content_markdown"
                defaultValue={edit?.content_markdown}
                placeholder="# 写下标题&#10;&#10;从这里开始整理…"
              />
              <small>支持 Markdown，保存后会自动排版为阅读视图。</small>
            </label>
            <input
              type="hidden"
              name="source"
              value={edit?.source || "manual"}
            />
            <FormActions
              onCancel={() => setEdit(undefined)}
              submit="保存笔记"
            />
          </form>
        </Modal>
      )}
      {settings && (
        <IntegrationSettings
          onClose={() => setSettings(false)}
          notify={notify}
        />
      )}
    </>
  );
}

function IntegrationSettings({
  onClose,
  notify,
}: {
  onClose: () => void;
  notify: (s: string) => void;
}) {
  const config = useData<Entity>(() => api.integrationConfig(), []);
  const save = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const body: any = Object.fromEntries(new FormData(e.currentTarget));
    body.notion_timeout_seconds = Number(body.notion_timeout_seconds);
    try {
      await api.saveIntegrationConfig(body);
      notify("个人集成配置已保存");
      onClose();
    } catch (error) {
      notify(errorText(error));
    }
  };

  return (
    <Modal title="个人集成配置" onClose={onClose} wide>
      {config.loading || !config.data ? (
        <Loading error={config.error} />
      ) : (
        <form className="form" onSubmit={save}>
          <div className="integration-section">
            <div>
              <h3>
                <SiNotion size={17} /> Notion
              </h3>
              <Status
                value={config.data.notion_configured ? "completed" : "pending"}
              />
            </div>
            <p>Token 仅加密保存到当前账户，不会与其他系统用户共享。</p>
            {config.data.notion_invalid && (
              <div className="integration-warning" role="alert">
                {config.data.notion_error_message || "原 Notion Token 已失效，请重新输入后保存。"}
              </div>
            )}
            <label>
              Integration Token
              <input
                name="notion_api_key"
                type="password"
                placeholder={
                  config.data.notion_invalid
                    ? "请重新输入 Notion Token"
                    : config.data.notion_api_key_hint || "secret_..."
                }
              />
            </label>
            <div className="form-row">
              <label>
                父页面 ID 或 URL
                <input
                  name="notion_parent_page_id"
                  defaultValue={config.data.notion_parent_page_id || ""}
                />
              </label>
              <label>
                超时秒数
                <input
                  name="notion_timeout_seconds"
                  type="number"
                  min="1"
                  max="120"
                  defaultValue={config.data.notion_timeout_seconds || 30}
                />
              </label>
            </div>
            <input
              type="hidden"
              name="notion_api_version"
              value={config.data.notion_api_version || "2026-03-11"}
            />
          </div>
          <div className="integration-section">
            <div>
              <h3>
                <SiObsidian size={17} /> Obsidian
              </h3>
              <Status
                value={
                  config.data.obsidian_configured ? "completed" : "pending"
                }
              />
            </div>
            <p>桌面版后端必须能访问所填写的本地 Vault 路径。</p>
            <div className="form-row">
              <label>
                Vault 绝对路径
                <input
                  name="obsidian_vault_path"
                  defaultValue={config.data.obsidian_vault_path || ""}
                  placeholder="D:/Documents/MyVault"
                />
              </label>
              <label>
                Vault 内基础目录
                <input
                  name="obsidian_base_folder"
                  defaultValue={
                    config.data.obsidian_base_folder || "课程学习助手"
                  }
                />
              </label>
            </div>
          </div>
          <FormActions onCancel={onClose} submit="保存个人配置" />
        </form>
      )}
    </Modal>
  );
}
