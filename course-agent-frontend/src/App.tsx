import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type FormEvent,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { SiNotion, SiObsidian } from "react-icons/si";
import {
  BookOpen,
  CalendarRange,
  Check,
  ChevronRight,
  CircleHelp,
  Clock3,
  Database,
  Download,
  Eye,
  FileText,
  FolderOpen,
  LayoutDashboard,
  Library,
  LockKeyhole,
  LogOut,
  Menu,
  MessageSquareText,
  NotebookPen,
  Plus,
  Pencil,
  RefreshCw,
  Search,
  Settings2,
  Sparkles,
  Target,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import {
  api,
  streamAgent,
  type Entity,
  type SemanticSearchItem,
  type SemanticSearchResponse,
} from "./api";

type Page =
  | "dashboard"
  | "courses"
  | "materials"
  | "search"
  | "tasks"
  | "plans"
  | "notes"
  | "records"
  | "chat"
  | "audit";
const AuditPage = lazy(() => import("./features/audit/AuditPage"));
const DashboardPage = lazy(() => import("./features/dashboard/DashboardPage"));
const MarkdownContent = lazy(() => import("./components/MarkdownContent"));
const ChatPage = lazy(() => import("./features/chat/ChatPage"));
const CoursesPage = lazy(() => import("./features/courses/CoursesPage"));
const MaterialsPage = lazy(() => import("./features/materials/MaterialsPage"));
const PlansPage = lazy(() => import("./features/plans/PlansPage"));
const NotesPage = lazy(() => import("./features/notes/NotesPage"));
const nav: { id: Page; label: string; icon: any; group?: string }[] = [
  {
    id: "dashboard",
    label: "今日总览",
    icon: LayoutDashboard,
    group: "学习台",
  },
  { id: "courses", label: "课程", icon: BookOpen },
  { id: "materials", label: "资料库", icon: FolderOpen },
  { id: "search", label: "知识检索", icon: Search },
  { id: "tasks", label: "任务", icon: Check, group: "规划" },
  { id: "plans", label: "学习计划", icon: CalendarRange },
  { id: "records", label: "学习记录", icon: Clock3 },
  { id: "notes", label: "笔记", icon: NotebookPen, group: "沉淀" },
  { id: "chat", label: "课程问答", icon: MessageSquareText },
  { id: "audit", label: "运行审核", icon: Database, group: "管理" },
];
const pageMeta: Record<Page, [string, string]> = {
  dashboard: ["今日总览", "把注意力留给下一件要完成的事"],
  courses: ["课程", "管理学期课程与整体进度"],
  materials: ["资料库", "上传、解析并建立课程知识索引"],
  search: ["知识检索", "从已解析资料中定位原文依据"],
  tasks: ["任务", "安排明确、可完成的学习动作"],
  plans: ["学习计划", "把长期目标拆解到每一天"],
  notes: ["笔记", "记录理解，并同步到你的知识库"],
  records: ["学习记录", "用真实投入校准学习节奏"],
  chat: ["课程问答", "基于课程资料继续追问与理解"],
  audit: ["运行审核", "查看 Agent、接口性能与异常轨迹"],
};

function unwrap(data: any): Entity[] {
  return Array.isArray(data) ? data : data?.items || [];
}
function dateText(v?: string) {
  if (!v) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(v));
}
function dayText(v?: string) {
  return v
    ? new Intl.DateTimeFormat("zh-CN", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
      }).format(new Date(v))
    : "—";
}
function errorText(e: unknown) {
  return e instanceof Error ? e.message : "操作失败";
}
const labels: Record<string, string> = {
  pending: "待开始",
  in_progress: "进行中",
  completed: "已完成",
  cancelled: "已取消",
  draft: "草稿",
  active: "进行中",
  paused: "已暂停",
  urgent: "紧急",
  high: "高",
  medium: "中",
  low: "低",
  manual: "手动记录",
  material: "资料学习",
  task: "任务",
  study_plan: "学习计划",
  summary: "摘要",
  knowledge_point: "知识点",
  review: "复盘",
};

function App() {
  const [token, setToken] = useState(localStorage.getItem("access_token"));
  const [page, setPage] = useState<Page>(
    (sessionStorage.getItem("page") as Page) || "dashboard",
  );
  const [user, setUser] = useState<Entity | null>(() => {
    try {
      return JSON.parse(localStorage.getItem("current_user") || "null");
    } catch {
      return null;
    }
  });
  const [mobile, setMobile] = useState(false);
  const [toast, setToast] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [dataVersion, setDataVersion] = useState(0);
  const [fontSize, setFontSize] = useState(
    () => localStorage.getItem("font_size") || "standard",
  );
  const fontScale =
    fontSize === "compact" ? 0.92 : fontSize === "large" ? 1.1 : 1;
  const appScaleStyle = {
    zoom: fontScale,
    width: "100%",
    height: `calc(${100 / fontScale}vh - ${38 / fontScale}px)`,
  } as CSSProperties;
  const notify = useCallback((s: string) => {
    setToast(s);
    setTimeout(() => setToast(""), 2600);
  }, []);
  useEffect(() => {
    const expired = () => setToken(null);
    window.addEventListener("auth-expired", expired);
    return () => window.removeEventListener("auth-expired", expired);
  }, []);
  useEffect(() => {
    if (token && !user)
      api
        .me()
        .then((u) => {
          setUser(u);
          localStorage.setItem("current_user", JSON.stringify(u));
        })
        .catch(() => {});
  }, [token, user]);
  const go = (p: Page) => {
    setPage(p);
    sessionStorage.setItem("page", p);
    setMobile(false);
  };
  const logout = () => {
    localStorage.removeItem("access_token");
    localStorage.removeItem("current_user");
    setUser(null);
    setToken(null);
  };
  const updateFontSize = (value: string) => {
    localStorage.setItem("font_size", value);
    setFontSize(value);
  };
  if (!token)
    return (
      <Login
        onLogin={(t, u) => {
          localStorage.setItem("access_token", t);
          localStorage.setItem("current_user", JSON.stringify(u));
          setToken(t);
          setUser(u);
        }}
      />
    );
  return (
    <>
      <div className="window-dragbar">
        <span>课程学习助手</span>
      </div>
      <div className="app-shell" style={appScaleStyle}>
        <aside className={`rail ${mobile ? "open" : ""}`}>
          <div className="brand">
            <span className="brand-mark">课</span>
            <div>
              <strong>学习工作台</strong>
              <small>COURSE DESK</small>
            </div>
            <button
              className="icon-btn rail-close"
              onClick={() => setMobile(false)}
            >
              <X size={18} />
            </button>
          </div>
          <nav>
            {nav.map((item, i) => (
              <div key={item.id}>
                {item.group && <div className="nav-group">{item.group}</div>}
                <button
                  className={page === item.id ? "active" : ""}
                  onClick={() => go(item.id)}
                >
                  <span className="index">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <item.icon size={17} />
                  <span>{item.label}</span>
                </button>
              </div>
            ))}
          </nav>
          <div className="rail-user">
            <div className="avatar">
              {user?.username?.slice(0, 1)?.toUpperCase() || "学"}
            </div>
            <div>
              <b>{user?.username || "学习者"}</b>
              <small>{user?.email || "本地账户"}</small>
            </div>
            <button
              className="icon-btn"
              title="打开设置"
              aria-label="打开设置"
              onClick={() => setSettingsOpen(true)}
            >
              <Settings2 size={16} />
            </button>
          </div>
        </aside>
        {mobile && (
          <button
            className="scrim"
            onClick={() => setMobile(false)}
            aria-label="关闭导航"
          />
        )}
        <main className="workspace">
          <header className="topbar">
            <button className="icon-btn menu" onClick={() => setMobile(true)}>
              <Menu size={20} />
            </button>
            <div>
              <h1>{pageMeta[page][0]}</h1>
              <p>{pageMeta[page][1]}</p>
            </div>
          </header>
          <section className="page">
            <div className="page-transition" key={`${page}-${dataVersion}`}>
              <Suspense fallback={<Loading />}>
                <PageView page={page} notify={notify} go={go} />
              </Suspense>
            </div>
          </section>
        </main>
        {toast && (
          <div className="toast">
            <Check size={16} />
            {toast}
          </div>
        )}
        {settingsOpen && (
          <UserSettings
            fontSize={fontSize}
            onFontSize={updateFontSize}
            onClose={() => setSettingsOpen(false)}
            onLogout={logout}
            onMaterialsCleared={() => setDataVersion((value) => value + 1)}
            notify={notify}
          />
        )}
      </div>
    </>
  );
}

function Login({
  onLogin,
}: {
  onLogin: (token: string, user: Entity) => void;
}) {
  const [register, setRegister] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const submit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    const f = new FormData(e.currentTarget);
    const body = Object.fromEntries(f);
    try {
      if (register) {
        await api.register(body);
        setRegister(false);
        setError("账户已创建，现在可以登录");
      } else {
        const r: any = await api.login(body);
        onLogin(r.access_token, r.user);
      }
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="login-page">
      <div className="login-aside">
        <div className="brand light">
          <span className="brand-mark">课</span>
          <div>
            <strong>学习工作台</strong>
            <small>COURSE DESK</small>
          </div>
        </div>
        <div className="login-thesis">
          <span>
            把散落的学习，
            <br />
            整理成清晰的进展。
          </span>
          <p>课程、资料、计划、笔记与学习记录，在一处自然衔接。</p>
        </div>
        <div className="ruler">本学期 · 保持节奏 · 持续复盘</div>
      </div>
      <div className="login-panel">
        <form onSubmit={submit}>
          <div className="eyebrow">
            {register ? "创建学习档案" : "欢迎回来"}
          </div>
          <h1>{register ? "开始使用" : "继续今天的学习"}</h1>
          <p className="muted">登录后继续整理今天的学习进展</p>
          <label>
            用户名
            <input
              name="username"
              minLength={3}
              required
              autoFocus
              placeholder="输入用户名"
            />
          </label>
          {register && (
            <label>
              邮箱（选填）
              <input name="email" type="email" placeholder="name@example.com" />
            </label>
          )}
          <label>
            密码
            <input
              name="password"
              type="password"
              minLength={6}
              required
              placeholder="至少 6 位"
            />
          </label>
          {error && (
            <div
              className={
                error.includes("已创建") ? "form-success" : "form-error"
              }
            >
              {error}
            </div>
          )}
          <button className="btn primary wide" disabled={busy}>
            {busy ? "正在处理…" : register ? "创建账户" : "登录"}
          </button>
          <button
            type="button"
            className="text-btn"
            onClick={() => {
              setRegister(!register);
              setError("");
            }}
          >
            {register ? "已有账户？返回登录" : "没有账户？创建一个"}
          </button>
        </form>
      </div>
    </div>
  );
}

function PageView({
  page,
  notify,
  go,
}: {
  page: Page;
  notify: (s: string) => void;
  go: (p: Page) => void;
}) {
  if (page === "dashboard") return <DashboardPage go={go} />;
  if (page === "courses") return <CoursesPage notify={notify} />;
  if (page === "materials") return <MaterialsPage notify={notify} />;
  if (page === "search") return <KnowledgeSearch />;
  if (page === "tasks") return <Tasks notify={notify} />;
  if (page === "plans") return <PlansPage notify={notify} />;
  if (page === "notes") return <NotesPage notify={notify} />;
  if (page === "records") return <Records notify={notify} />;
  if (page === "chat") return <ChatPage notify={notify} />;
  return (
    <Suspense fallback={<Loading />}>
      <AuditPage />
    </Suspense>
  );
}

function useData<T>(loader: () => Promise<T>, deps: any[] = []) {
  const [data, setData] = useState<T | null>(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true),
    [tick, setTick] = useState(0);
  useEffect(() => {
    let live = true;
    setLoading(true);
    loader()
      .then((x) => live && setData(x))
      .catch((e) => live && setError(errorText(e)))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
  }, [...deps, tick]);
  return { data, error, loading, reload: () => setTick((x) => x + 1), setData };
}
function Loading({ error }: { error?: string }) {
  return (
    <div className="empty">
      <RefreshCw className="spin" size={20} />
      <b>{error || "正在整理数据"}</b>
      <span>{error ? "检查后端服务后刷新页面" : "请稍候"}</span>
    </div>
  );
}
function Empty({ title, text }: { title: string; text: string }) {
  return (
    <div className="empty">
      <Library size={24} />
      <b>{title}</b>
      <span>{text}</span>
    </div>
  );
}
function Modal({
  title,
  children,
  onClose,
  wide,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  return createPortal(
    <div className="modal-backdrop" onMouseDown={onClose}>
      <div
        className={`modal ${wide ? "wide" : ""}`}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="modal-head">
          <h2>{title}</h2>
          <button className="icon-btn" onClick={onClose}>
            <X size={18} />
          </button>
        </div>
        {children}
      </div>
    </div>,
    document.body,
  );
}

function UserSettings({
  fontSize,
  onFontSize,
  onClose,
  onLogout,
  onMaterialsCleared,
  notify,
}: {
  fontSize: string;
  onFontSize: (value: string) => void;
  onClose: () => void;
  onLogout: () => void;
  onMaterialsCleared: () => void;
  notify: (message: string) => void;
}) {
  const [passwordBusy, setPasswordBusy] = useState(false);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [identityBusy, setIdentityBusy] = useState(false);
  const [modelBusy, setModelBusy] = useState(false);
  const [backupBusy, setBackupBusy] = useState<"export" | "import" | "">("");
  const [backupProgress, setBackupProgress] = useState(0);
  const [verifiedPassword, setVerifiedPassword] = useState("");
  const [provider, setProvider] = useState("openai");
  const llmConfig = useData<Entity>(() => api.llmConfig(), []);

  useEffect(() => {
    if (llmConfig.data?.provider) setProvider(llmConfig.data.provider);
  }, [llmConfig.data?.provider]);

  const changePassword = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    const values: any = Object.fromEntries(new FormData(form));
    if (values.new_password !== values.confirm_password) {
      notify("两次输入的新密码不一致");
      return;
    }
    setPasswordBusy(true);
    try {
      await api.changePassword({
        current_password: values.current_password,
        new_password: values.new_password,
      });
      form.reset();
      notify("密码已修改");
    } catch (error) {
      notify(errorText(error));
    } finally {
      setPasswordBusy(false);
    }
  };

  const clearMaterials = async () => {
    if (
      !confirm(
        "确定删除当前账户上传的全部课程资料？原文件、文本分块和向量索引都会永久删除，课程与笔记会保留。",
      )
    )
      return;
    setDeleteBusy(true);
    try {
      const result: any = await api.deleteAllMaterials();
      onMaterialsCleared();
      notify(result.message || "全部课程资料已删除");
    } catch (error) {
      notify(errorText(error));
    } finally {
      setDeleteBusy(false);
    }
  };

  const verifyModelIdentity = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const currentPassword = String(
      new FormData(event.currentTarget).get("current_password") || "",
    );
    setIdentityBusy(true);
    try {
      await api.verifyPassword(currentPassword);
      setVerifiedPassword(currentPassword);
      notify("身份验证通过，请填写模型连接信息");
    } catch (error) {
      notify(errorText(error));
    } finally {
      setIdentityBusy(false);
    }
  };

  const saveModelConnection = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const body: any = Object.fromEntries(new FormData(event.currentTarget));
    body.current_password = verifiedPassword;
    setModelBusy(true);
    try {
      await api.saveLlmConfig(body);
      setVerifiedPassword("");
      llmConfig.reload();
      notify("外部模型已接入，后续 Agent 操作将使用此模型");
    } catch (error) {
      notify(errorText(error));
    } finally {
      setModelBusy(false);
    }
  };

  const useSystemModel = async () => {
    if (!verifiedPassword) return;
    setModelBusy(true);
    try {
      await api.disableLlmConfig(verifiedPassword);
      setVerifiedPassword("");
      llmConfig.reload();
      notify("已恢复使用系统默认模型");
    } catch (error) {
      notify(errorText(error));
    } finally {
      setModelBusy(false);
    }
  };

  const exportBackup = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    const password = String(new FormData(form).get("current_password") || "");
    setBackupBusy("export");
    try {
      const blob = await api.exportBackup(password);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `course-study-backup-${new Date().toISOString().slice(0, 10)}.zip`;
      link.click();
      URL.revokeObjectURL(url);
      form.reset();
      notify("数据备份已导出，请妥善保管");
    } catch (error) {
      notify(errorText(error));
    } finally {
      setBackupBusy("");
    }
  };

  const importBackup = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    const file = values.get("file");
    if (!(file instanceof File) || !file.size) return;
    if (!confirm("导入会把备份内容合并到当前账户，并在后台重建资料向量。确认继续吗？")) return;
    setBackupBusy("import");
    setBackupProgress(0);
    try {
      const result: any = await api.importBackup(
        String(values.get("current_password") || ""),
        file,
        (percent) => setBackupProgress(percent),
      );
      form.reset();
      notify(`${result.message || "数据导入完成"}，正在刷新工作台`);
      window.setTimeout(() => window.location.reload(), 700);
    } catch (error) {
      notify(errorText(error));
    } finally {
      setBackupBusy("");
      setBackupProgress(0);
    }
  };

  return (
    <Modal title="账户与界面设置" onClose={onClose} wide>
      <div className="user-settings">
        <section className="setting-section">
          <div className="setting-heading">
            <Settings2 size={18} />
            <div>
              <h3>界面字号</h3>
              <p>调整整个工作台的内容密度，设置会保存在本机。</p>
            </div>
          </div>
          <div className="font-size-options" role="group" aria-label="界面字号">
            {[
              ["compact", "紧凑", "90%"],
              ["standard", "标准", "100%"],
              ["large", "较大", "110%"],
            ].map(([value, label, size]) => (
              <button
                type="button"
                key={value}
                className={fontSize === value ? "active" : ""}
                onClick={() => onFontSize(value)}
              >
                <b>{label}</b>
                <span>{size}</span>
              </button>
            ))}
          </div>
        </section>

        <section className="setting-section model-setting">
          <div className="setting-heading">
            <Sparkles size={18} />
            <div>
              <h3>外部大模型 API</h3>
              <p>
                密钥按账户加密保存，只用于你的 Agent 请求。请先验证登录密码。
              </p>
            </div>
            <span
              className={`connection-state ${llmConfig.data?.enabled ? "online" : ""}`}
            >
              {llmConfig.data?.enabled
                ? `${llmConfig.data.model_name} · ${llmConfig.data.api_key_hint}`
                : "使用系统模型"}
            </span>
          </div>
          <div className="model-steps">
            <form className="model-step" onSubmit={verifyModelIdentity}>
              <span className="step-number">01</span>
              <label>
                验证当前密码
                <input
                  name="current_password"
                  type="password"
                  minLength={6}
                  required
                  autoComplete="current-password"
                  placeholder="输入登录密码后继续"
                />
              </label>
              <button className="btn subtle" disabled={identityBusy}>
                {identityBusy ? "正在验证…" : "验证身份"}
              </button>
            </form>
            <form
              className={`model-step ${verifiedPassword ? "is-ready" : "is-locked"}`}
              onSubmit={saveModelConnection}
            >
              <span className="step-number">02</span>
              <label>
                接口类型
                <select
                  name="provider"
                  value={provider}
                  disabled={!verifiedPassword}
                  onChange={(event) => setProvider(event.target.value)}
                >
                  <option value="openai">OpenAI 兼容接口</option>
                  <option value="deepseek">DeepSeek</option>
                </select>
              </label>
              <label>
                模型名称
                <input
                  key={`model-${provider}`}
                  name="model_name"
                  required
                  disabled={!verifiedPassword}
                  defaultValue={
                    llmConfig.data?.provider === provider
                      ? llmConfig.data?.model_name
                      : provider === "deepseek"
                        ? "deepseek-chat"
                        : "gpt-4o-mini"
                  }
                />
              </label>
              <label>
                API 地址
                <input
                  key={`url-${provider}`}
                  name="base_url"
                  type="url"
                  disabled={!verifiedPassword}
                  defaultValue={
                    llmConfig.data?.provider === provider
                      ? llmConfig.data?.base_url
                      : provider === "deepseek"
                        ? "https://api.deepseek.com"
                        : "https://api.openai.com/v1"
                  }
                />
              </label>
              <label>
                API 密钥
                <input
                  name="api_key"
                  type="password"
                  minLength={8}
                  required
                  disabled={!verifiedPassword}
                  autoComplete="off"
                  placeholder="仅显示一次输入内容"
                />
              </label>
              <div className="model-actions">
                <button
                  className="btn primary"
                  disabled={!verifiedPassword || modelBusy}
                >
                  {modelBusy ? "正在接入…" : "保存并接入"}
                </button>
                {llmConfig.data?.enabled && (
                  <button
                    type="button"
                    className="text-btn"
                    disabled={!verifiedPassword || modelBusy}
                    onClick={useSystemModel}
                  >
                    改用系统模型
                  </button>
                )}
              </div>
            </form>
          </div>
        </section>

        <section className="setting-section">
          <div className="setting-heading">
            <LockKeyhole size={18} />
            <div>
              <h3>修改密码</h3>
              <p>修改后当前设备保持登录，下次请使用新密码。</p>
            </div>
          </div>
          <form className="password-form" onSubmit={changePassword}>
            <label>
              当前密码
              <input
                name="current_password"
                type="password"
                minLength={6}
                required
                autoComplete="current-password"
              />
            </label>
            <label>
              新密码
              <input
                name="new_password"
                type="password"
                minLength={6}
                required
                autoComplete="new-password"
              />
            </label>
            <label>
              确认新密码
              <input
                name="confirm_password"
                type="password"
                minLength={6}
                required
                autoComplete="new-password"
              />
            </label>
            <button className="btn primary" disabled={passwordBusy}>
              {passwordBusy ? "正在修改…" : "保存新密码"}
            </button>
          </form>
        </section>

        <section className="setting-section backup-setting">
          <div className="setting-heading">
            <Database size={18} />
            <div>
              <h3>数据备份与迁移</h3>
              <p>导出当前账户的课程、资料、任务、计划、笔记、学习记录和对话。备份不包含登录密码、模型 API Key 或第三方集成密钥。</p>
            </div>
          </div>
          <div className="backup-actions">
            <form onSubmit={exportBackup}>
              <label>登录密码<input name="current_password" type="password" minLength={6} required autoComplete="current-password" /></label>
              <button className="btn subtle" disabled={Boolean(backupBusy)}><Download size={15} />{backupBusy === "export" ? "正在打包…" : "导出备份"}</button>
            </form>
            <form onSubmit={importBackup}>
              <label>登录密码<input name="current_password" type="password" minLength={6} required autoComplete="current-password" /></label>
              <label className="backup-file">备份文件<input name="file" type="file" accept=".zip,application/zip" required /></label>
              <button className="btn subtle" disabled={Boolean(backupBusy)}><Upload size={15} />{backupBusy === "import" ? `正在导入 ${backupProgress}%` : "导入备份"}</button>
            </form>
          </div>
        </section>

        <section className="setting-section danger-zone">
          <div className="setting-heading">
            <Database size={18} />
            <div>
              <h3>数据与账户</h3>
              <p>清空资料不会删除课程、笔记、任务和学习计划。</p>
            </div>
          </div>
          <div className="setting-actions">
            <button
              type="button"
              className="btn danger-outline"
              disabled={deleteBusy}
              onClick={clearMaterials}
            >
              <Trash2 size={15} />
              {deleteBusy ? "正在删除…" : "删除所有资料"}
            </button>
            <button type="button" className="btn subtle" onClick={onLogout}>
              <LogOut size={15} />
              退出登录
            </button>
          </div>
        </section>
      </div>
    </Modal>
  );
}
function CourseSelect({
  courses,
  value,
  onChange,
  optional,
}: {
  courses: Entity[];
  value?: any;
  onChange: (v: string) => void;
  optional?: boolean;
}) {
  return (
    <select
      key={value || "empty"}
      name="course_id"
      defaultValue={value || ""}
      onChange={(e) => onChange(e.target.value)}
      required={!optional}
    >
      <option value="">{optional ? "不关联课程" : "选择课程"}</option>
      {courses.map((c) => (
        <option key={c.id} value={c.id}>
          {c.name}
        </option>
      ))}
    </select>
  );
}

async function runAgentAction(courseId: number, message: string) {
  let sessionId: number | undefined;
  try {
    const result: any = await api.chat({
      course_id: courseId,
      message,
      top_k: 5,
    });
    sessionId = result.session_id;
    return result.answer || "Agent 已完成创建";
  } finally {
    if (sessionId) api.deleteSession(sessionId).catch(() => undefined);
  }
}

function AiCreator({
  kind,
  courses,
  fixedCourseId,
  planId,
  onClose,
  onDone,
  notify,
}: {
  kind: "plan" | "tasks" | "plan_tasks";
  courses: Entity[];
  fixedCourseId?: number;
  planId?: number;
  onClose: () => void;
  onDone: () => void;
  notify: (message: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const title =
    kind === "plan"
      ? "AI 生成学习计划"
      : kind === "plan_tasks"
        ? "AI 拆解计划任务"
        : "AI 创建课程任务";

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const values: any = Object.fromEntries(new FormData(event.currentTarget));
    const courseId = fixedCourseId || Number(values.course_id);
    const taskCount = Number(values.task_count || 4);
    const goal = String(values.goal || "").trim();
    const dueDate = String(values.due_date || "");
    let command = "";

    if (kind === "plan") {
      const days = Number(values.days || 14);
      const dailyMinutes = Number(values.daily_minutes || 60);
      command = `这是从学习计划界面发起的执行请求。请务必调用工具实际写入数据，不能只给建议。围绕课程 ID ${courseId} 和目标“${goal}”，从今天起创建一份持续 ${days} 天、每天约 ${dailyMinutes} 分钟的学习计划，状态设为 active。创建计划后，继续调用 create_task，把新计划 ID 作为 plan_id，生成 ${taskCount} 个循序渐进的日程任务，任务日期均匀分布在计划周期内。完成全部工具调用后简要汇报创建结果。`;
    } else if (kind === "plan_tasks") {
      command = `这是从计划详情界面发起的执行请求。请务必调用 create_task 工具实际写入数据，不能只列清单。围绕课程 ID ${courseId} 和目标“${goal}”，向学习计划 ID ${planId} 中创建 ${taskCount} 个可以直接执行的日程任务${dueDate ? `，从 ${dueDate} 开始安排` : ""}。每个任务需有清晰标题、说明、合理优先级和日期。完成全部工具调用后简要汇报。`;
    } else {
      command = `这是从任务界面发起的执行请求。请务必调用 create_task 工具实际写入数据，不能只给建议。围绕课程 ID ${courseId} 和目标“${goal}”，创建 ${taskCount} 个具体、可完成、彼此不重复的学习任务${dueDate ? `，截止日期从 ${dueDate} 起合理安排` : ""}。每个任务要包含说明和合理优先级。完成全部工具调用后简要汇报。`;
    }

    setBusy(true);
    try {
      await runAgentAction(courseId, command);
      notify(kind === "plan" ? "AI 已生成计划与日程任务" : "AI 已创建课程任务");
      onDone();
    } catch (error) {
      notify(errorText(error));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal title={title} onClose={busy ? () => undefined : onClose}>
      <form className="form ai-create-form" onSubmit={submit}>
        <div className="ai-create-intro">
          <Sparkles size={18} />
          <div>
            <b>让 Agent 直接执行</b>
            <span>会调用后端工具并写入当前账户，不只是生成一段文字。</span>
          </div>
        </div>
        {!fixedCourseId && (
          <label>
            依据课程
            <CourseSelect courses={courses} onChange={() => undefined} />
          </label>
        )}
        {fixedCourseId && (
          <div className="selected-course">
            <span>依据课程</span>
            <b>{courses.find((course) => course.id === fixedCourseId)?.name}</b>
          </div>
        )}
        <label>
          {kind === "plan" ? "计划目标" : "希望完成什么"}
          <textarea
            name="goal"
            required
            placeholder={
              kind === "plan"
                ? "例如：两周内完成期末复习并掌握薄弱章节"
                : "例如：完成第三章复习、练习与错题整理"
            }
          />
        </label>
        <div className="form-row">
          {kind === "plan" ? (
            <>
              <label>
                计划天数
                <input
                  name="days"
                  type="number"
                  min="2"
                  max="180"
                  defaultValue="14"
                />
              </label>
              <label>
                每日分钟
                <input
                  name="daily_minutes"
                  type="number"
                  min="10"
                  max="600"
                  defaultValue="60"
                />
              </label>
            </>
          ) : (
            <label>
              开始日期
              <input name="due_date" type="date" />
            </label>
          )}
          <label>
            生成任务数
            <input
              name="task_count"
              type="number"
              min="1"
              max="10"
              defaultValue={kind === "plan" ? "5" : "4"}
            />
          </label>
        </div>
        {busy && (
          <div className="ai-progress">
            <RefreshCw className="spin" size={15} />
            Agent 正在调用计划工具，请保持窗口开启…
          </div>
        )}
        <FormActions
          onCancel={onClose}
          submit={busy ? "正在创建…" : "交给 Agent 创建"}
          disabled={busy}
        />
      </form>
    </Modal>
  );
}
function Status({ value }: { value: string }) {
  return <span className={`status ${value}`}>{labels[value] || value}</span>;
}

function Toolbar({
  children,
  count,
  label,
}: {
  children: ReactNode;
  count: number;
  label: string;
}) {
  return (
    <div className="toolbar">
      <p>
        <b>{count}</b> {label}
      </p>
      <div>{children}</div>
    </div>
  );
}
function FormActions({
  onCancel,
  submit,
  disabled = false,
}: {
  onCancel: () => void;
  submit: string;
  disabled?: boolean;
}) {
  return (
    <div className="form-actions">
      <button
        type="button"
        className="btn subtle"
        disabled={disabled}
        onClick={onCancel}
      >
        取消
      </button>
      <button className="btn primary" disabled={disabled}>
        {submit}
      </button>
    </div>
  );
}

function KnowledgeSearch() {
  const courses = useData(() => api.courses(), []),
    [cid, setCid] = useState(""),
    [q, setQ] = useState(""),
    [response, setResponse] = useState<SemanticSearchResponse | null>(null),
    [busy, setBusy] = useState(false),
    [err, setErr] = useState("");
  const results: SemanticSearchItem[] = response?.results || [];
  const run = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      const r = await api.search({
        course_id: Number(cid),
        query: q,
        top_k: 10,
      });
      setResponse(r);
    } catch (x) {
      setErr(errorText(x));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="search-layout">
      <form className="search-box" onSubmit={run}>
        <div className="search-mark">
          <Search size={26} />
        </div>
        <div>
          <label>
            在哪门课程中查找？
            <CourseSelect
              courses={courses.data || []}
              value={cid}
              onChange={setCid}
            />
          </label>
          <label>
            输入概念、问题或关键句
            <textarea
              value={q}
              onChange={(e) => setQ(e.target.value)}
              required
              placeholder="例如：观察者模式如何降低对象之间的耦合？"
            />
          </label>
          <button className="btn primary" disabled={busy}>
            {busy ? "正在检索…" : "检索课程资料"}
          </button>
          {err && <div className="form-error">{err}</div>}
        </div>
      </form>
      <div className="results">
        <div className="results-head">
          <h2>检索结果</h2>
          <span>
            {results.length
              ? `${results.length} 条依据 · 余弦相似度越高越相关`
              : response
                ? `阈值 ${Math.round(response.min_similarity * 100)}%`
                : "等待检索"}
          </span>
        </div>
        <div className="results-list">
          {results.length ? (
            results.map((r, i) => (
              <article key={r.vector_id || i}>
                <div className="result-rank">
                  {String(i + 1).padStart(2, "0")}
                </div>
                <div>
                  <div className="result-meta">
                    <b>{r.material_title}</b>
                    <span>
                      {r.page_no ? `第 ${r.page_no} 页 · ` : ""}余弦相似度{" "}
                      {Number(r.similarity_percent).toFixed(2)}%
                    </span>
                  </div>
                  <p>{r.content}</p>
                  <small className="retrieval-metric">
                    片段 {r.chunk_index} · 余弦距离 {r.distance.toFixed(4)}
                  </small>
                </div>
              </article>
            ))
          ) : (
            <Empty
              title={
                response
                  ? "当前课程资料中未找到相似度足够高的内容"
                  : "从资料中寻找依据"
              }
              text={
                response
                  ? "可以换一种问法，或检查资料是否已完成向量索引。"
                  : "先为资料建立检索索引，再输入自然语言问题"
              }
            />
          )}
        </div>
      </div>
    </div>
  );
}

function Tasks({ notify }: { notify: (s: string) => void }) {
  const courses = useData(() => api.courses(), []),
    [filter, setFilter] = useState(""),
    tasks = useData(
      () => api.tasks(filter ? `status=${filter}` : ""),
      [filter],
    ),
    [edit, setEdit] = useState<Entity | null | undefined>(),
    [aiOpen, setAiOpen] = useState(false),
    [recentlyCompleted, setRecentlyCompleted] = useState<number | null>(null);
  const items = unwrap(tasks.data);
  const save = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = new FormData(e.currentTarget),
      body: any = Object.fromEntries(f);
    body.course_id = body.course_id ? Number(body.course_id) : null;
    body.estimated_minutes = body.estimated_minutes
      ? Number(body.estimated_minutes)
      : null;
    body.due_at = body.due_at
      ? new Date(String(body.due_at)).toISOString()
      : null;
    try {
      edit?.id
        ? await api.updateTask(edit.id, body)
        : await api.createTask(body);
      setEdit(undefined);
      tasks.reload();
      notify("任务已保存");
    } catch (x) {
      notify(errorText(x));
    }
  };
  const setTaskStatus = async (task: Entity, nextStatus: string) => {
    const previousStatus = task.status;
    const updateItems = (value: any) => {
      if (Array.isArray(value)) {
        return value.map((item) =>
          item.id === task.id ? { ...item, status: nextStatus } : item,
        );
      }
      return {
        ...value,
        items: unwrap(value).map((item) =>
          item.id === task.id ? { ...item, status: nextStatus } : item,
        ),
      };
    };
    tasks.setData((current: any) => updateItems(current));
    if (nextStatus === "completed") {
      setRecentlyCompleted(task.id);
      window.setTimeout(() => setRecentlyCompleted(null), 900);
    }
    try {
      await api.taskStatus(task.id, nextStatus);
      notify(
        nextStatus === "completed"
          ? task.course_id
            ? `任务完成，已计入 ${task.estimated_minutes || 30} 分钟学习时间`
            : "任务完成；通用任务不计入课程学习时间"
          : "任务状态已更新",
      );
      if (filter && filter !== nextStatus) {
        window.setTimeout(tasks.reload, 950);
      }
    } catch (error) {
      tasks.setData((current: any) => {
        const restore = (item: Entity) =>
          item.id === task.id ? { ...item, status: previousStatus } : item;
        return Array.isArray(current)
          ? current.map(restore)
          : { ...current, items: unwrap(current).map(restore) };
      });
      notify(errorText(error));
    }
  };
  return (
    <>
      <div className="split-toolbar">
        <div className="segmented">
          {[
            ["", "全部"],
            ["pending", "待开始"],
            ["in_progress", "进行中"],
            ["completed", "已完成"],
          ].map(([v, l]) => (
            <button
              className={filter === v ? "active" : ""}
              onClick={() => setFilter(v)}
              key={v}
            >
              {l}
            </button>
          ))}
        </div>
        <div className="toolbar-actions">
          <button className="btn ai-action" onClick={() => setAiOpen(true)}>
            <Sparkles size={15} />
            AI 创建任务
          </button>
          <button className="btn primary" onClick={() => setEdit(null)}>
            <Plus size={16} />
            添加任务
          </button>
        </div>
      </div>
      {tasks.loading ? (
        <Loading error={tasks.error} />
      ) : items.length ? (
        <div className="task-board task-timeline">
          {items.map((t, index) => (
            <article
              key={t.id}
              className={`${t.status === "completed" ? "done" : ""} ${recentlyCompleted === t.id ? "just-completed" : ""}`}
            >
              <span className="task-sequence">
                {String(index + 1).padStart(2, "0")}
              </span>
              <button
                className="task-check"
                aria-label={
                  t.status === "completed" ? "标记为未完成" : "标记为已完成"
                }
                onClick={async () => {
                  await setTaskStatus(
                    t,
                    t.status === "completed" ? "pending" : "completed",
                  );
                }}
              >
                {t.status === "completed" && <Check size={14} />}
              </button>
              <div className="task-body" onClick={() => setEdit(t)}>
                <div>
                  <Status value={t.priority} />
                  <h3>{t.title}</h3>
                </div>
                <p>{t.description || "没有补充说明"}</p>
                <small>
                  {courses.data?.find((c) => c.id === t.course_id)?.name ||
                    "通用任务"}{" "}
                  ·{" "}
                  {t.estimated_minutes ? `${t.estimated_minutes} 分钟 · ` : ""}
                  {t.due_at ? `截止 ${dateText(t.due_at)}` : "未设截止时间"}
                </small>
              </div>
              <select
                value={t.status}
                onChange={async (e) => {
                  await setTaskStatus(t, e.target.value);
                }}
              >
                <option value="pending">待开始</option>
                <option value="in_progress">进行中</option>
                <option value="completed">已完成</option>
                <option value="cancelled">已取消</option>
              </select>
              <button
                className="icon-btn danger"
                onClick={async () => {
                  if (confirm("删除此任务？")) {
                    await api.deleteTask(t.id);
                    tasks.reload();
                  }
                }}
              >
                <Trash2 size={15} />
              </button>
            </article>
          ))}
        </div>
      ) : (
        <Empty title="没有符合条件的任务" text="添加一个清晰、可执行的下一步" />
      )}
      {edit !== undefined && (
        <Modal
          title={edit?.id ? "编辑任务" : "添加任务"}
          onClose={() => setEdit(undefined)}
        >
          <form className="form" onSubmit={save}>
            <label>
              任务标题
              <input name="title" required defaultValue={edit?.title} />
            </label>
            <label>
              说明
              <textarea name="description" defaultValue={edit?.description} />
            </label>
            <div className="form-row">
              <label>
                所属课程
                <CourseSelect
                  courses={courses.data || []}
                  value={edit?.course_id}
                  onChange={() => {}}
                  optional
                />
              </label>
              <label>
                优先级
                <select
                  name="priority"
                  defaultValue={edit?.priority || "medium"}
                >
                  <option value="low">低</option>
                  <option value="medium">中</option>
                  <option value="high">高</option>
                  <option value="urgent">紧急</option>
                </select>
              </label>
            </div>
            <div className="form-row">
              <label>
                截止时间
                <input
                  name="due_at"
                  type="datetime-local"
                  defaultValue={edit?.due_at?.slice(0, 16)}
                />
              </label>
              <label>
                预计分钟
                <input
                  name="estimated_minutes"
                  type="number"
                  min="1"
                  defaultValue={edit?.estimated_minutes}
                />
              </label>
            </div>
            <FormActions
              onCancel={() => setEdit(undefined)}
              submit="保存任务"
            />
          </form>
        </Modal>
      )}
      {aiOpen && (
        <AiCreator
          kind="tasks"
          courses={courses.data || []}
          onClose={() => setAiOpen(false)}
          onDone={() => {
            setAiOpen(false);
            tasks.reload();
          }}
          notify={notify}
        />
      )}
    </>
  );
}

function Records({ notify }: { notify: (s: string) => void }) {
  const courses = useData(() => api.courses(), []),
    records = useData(() => api.records(), []),
    summary = useData(() => api.summary(), []),
    [edit, setEdit] = useState<Entity | null | undefined>();
  const items = unwrap(records.data);
  const s: any = summary.data || {};
  const save = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const b: any = Object.fromEntries(new FormData(e.currentTarget));
    b.course_id = Number(b.course_id);
    b.duration_minutes = Number(b.duration_minutes);
    b.studied_at = new Date(String(b.studied_at)).toISOString();
    try {
      edit?.id ? await api.updateRecord(edit.id, b) : await api.createRecord(b);
      setEdit(undefined);
      records.reload();
      summary.reload();
      notify("学习记录已保存");
    } catch (x) {
      notify(errorText(x));
    }
  };
  return (
    <>
      <div className="record-summary">
        <div>
          <span>累计投入</span>
          <strong>{s.total_study_minutes || 0}</strong>
          <small>分钟</small>
        </div>
        <div>
          <span>近 7 天</span>
          <strong>{s.recent_7_days_minutes || 0}</strong>
          <small>分钟</small>
        </div>
        <div>
          <span>学习次数</span>
          <strong>{s.learning_record_count || 0}</strong>
          <small>次</small>
        </div>
        <button className="btn primary" onClick={() => setEdit(null)}>
          <Plus size={16} />
          记录学习
        </button>
      </div>
      {items.length ? (
        <div className="timeline">
          {items.map((r) => (
            <article key={r.id}>
              <div className="timeline-date">
                <b>{new Date(r.studied_at).getDate()}</b>
                <span>
                  {new Date(r.studied_at).toLocaleDateString("zh-CN", {
                    month: "short",
                  })}
                </span>
              </div>
              <div className="timeline-line">
                <i />
              </div>
              <div className="timeline-card" onClick={() => setEdit(r)}>
                <div>
                  <Status value={r.source} />
                  <strong>{r.duration_minutes} 分钟</strong>
                  <span>
                    {courses.data?.find((c) => c.id === r.course_id)?.name}
                  </span>
                </div>
                <h3>{r.content_summary || "一次学习记录"}</h3>
                <p>{r.reflection || "没有填写复盘"}</p>
              </div>
              <button
                className="icon-btn danger"
                onClick={async () => {
                  if (confirm("删除这条记录？")) {
                    await api.deleteRecord(r.id);
                    records.reload();
                    summary.reload();
                  }
                }}
              >
                <Trash2 size={15} />
              </button>
            </article>
          ))}
        </div>
      ) : (
        <Empty
          title="暂无学习记录"
          text="完成一次学习后，记录时间、内容与复盘"
        />
      )}
      {edit !== undefined && (
        <Modal
          title={edit?.id ? "编辑学习记录" : "记录本次学习"}
          onClose={() => setEdit(undefined)}
        >
          <form className="form" onSubmit={save}>
            <div className="form-row">
              <label>
                课程
                <CourseSelect
                  courses={courses.data || []}
                  value={edit?.course_id}
                  onChange={() => {}}
                />
              </label>
              <label>
                学习分钟
                <input
                  name="duration_minutes"
                  type="number"
                  min="1"
                  max="1440"
                  required
                  defaultValue={edit?.duration_minutes || 30}
                />
              </label>
            </div>
            <div className="form-row">
              <label>
                学习时间
                <input
                  name="studied_at"
                  type="datetime-local"
                  required
                  defaultValue={
                    edit?.studied_at?.slice(0, 16) ||
                    new Date(
                      Date.now() - new Date().getTimezoneOffset() * 60000,
                    )
                      .toISOString()
                      .slice(0, 16)
                  }
                />
              </label>
              <label>
                来源
                <select name="source" defaultValue={edit?.source || "manual"}>
                  <option value="manual">手动记录</option>
                  <option value="material">资料学习</option>
                  <option value="task">任务</option>
                  <option value="study_plan">学习计划</option>
                </select>
              </label>
            </div>
            <label>
              学了什么
              <textarea
                name="content_summary"
                defaultValue={edit?.content_summary}
              />
            </label>
            <label>
              复盘与想法
              <textarea name="reflection" defaultValue={edit?.reflection} />
            </label>
            <FormActions
              onCancel={() => setEdit(undefined)}
              submit="保存记录"
            />
          </form>
        </Modal>
      )}
    </>
  );
}

export default App;
