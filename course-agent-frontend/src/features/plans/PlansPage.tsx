import { useState, type FormEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { AlertTriangle, Check, Library, Plus, RefreshCw, RotateCcw, Settings2, Sparkles, Trash2, X } from "lucide-react";
import { api, type Entity, type MultiCoursePlanPreview } from "../../api";
import MultiCoursePlanner from "./MultiCoursePlanner";
import { useAsyncData as useData } from "../../shared/useAsyncData";

const labels:Record<string,string>={draft:"草稿",active:"进行中",paused:"已暂停",completed:"已完成",pending:"待开始",in_progress:"进行中",cancelled:"已取消"};
function unwrap(data:any):Entity[]{return Array.isArray(data)?data:data?.items||[]}
function errorText(error:unknown){return error instanceof Error?error.message:"操作失败"}
function dayText(value?:string){return value?new Intl.DateTimeFormat("zh-CN",{year:"numeric",month:"2-digit",day:"2-digit"}).format(new Date(value)):"—"}
function Empty({title,text}:{title:string;text:string}){return <div className="empty"><Library size={24}/><b>{title}</b><span>{text}</span></div>}
function Modal({title,children,onClose,wide=false}:{title:string;children:ReactNode;onClose:()=>void;wide?:boolean}){return createPortal(<div className="modal-backdrop" onMouseDown={onClose}><div className={`modal ${wide?"wide":""}`} onMouseDown={event=>event.stopPropagation()}><div className="modal-head"><h2>{title}</h2><button className="icon-btn" onClick={onClose}><X size={18}/></button></div>{children}</div></div>,document.body)}
function CourseSelect({courses,value,onChange,optional=false}:{courses:Entity[];value?:any;onChange:(value:string)=>void;optional?:boolean}){return <select name="course_id" defaultValue={value||""} onChange={event=>onChange(event.target.value)} required={!optional}><option value="">{optional?"不关联课程":"选择课程"}</option>{courses.map(course=><option key={course.id} value={course.id}>{course.name}</option>)}</select>}
function FormActions({onCancel,submit,disabled=false}:{onCancel:()=>void;submit:string;disabled?:boolean}){return <div className="form-actions"><button type="button" className="btn subtle" onClick={onCancel}>取消</button><button className="btn primary" disabled={disabled}>{submit}</button></div>}
function Toolbar({count,label,children}:{count:number;label:string;children:ReactNode}){return <div className="toolbar"><p><b>{count}</b> {label}</p>{children}</div>}
function Status({value}:{value:string}){return <span className={`status ${value}`}>{labels[value]||value}</span>}


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


export default function PlansPage({ notify }: { notify: (s: string) => void }) {
  const courses = useData(() => api.courses(), []),
    plans = useData(() => api.plans(), []),
    [edit, setEdit] = useState<Entity | null | undefined>(),
    [aiOpen, setAiOpen] = useState(false),
    [detail, setDetail] = useState<Entity | null>(null),
    [view, setView] = useState<"single" | "multi">("single");
  const items = unwrap(plans.data);
  const save = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const body: any = Object.fromEntries(new FormData(e.currentTarget));
    body.course_id = body.course_id ? Number(body.course_id) : null;
    body.daily_minutes = Number(body.daily_minutes);
    try {
      edit?.id
        ? await api.updatePlan(edit.id, body)
        : await api.createPlan(body);
      setEdit(undefined);
      plans.reload();
      notify("计划已保存");
    } catch (x) {
      notify(errorText(x));
    }
  };
  const open = async (p: Entity) => {
    const [tasks, progress] = await Promise.all([
      api.planTasks(p.id),
      api.planProgress(p.id),
    ]);
    setDetail({ ...p, tasks: unwrap(tasks), progress });
  };
  return (
    <>
      <div className="plan-view-tabs" role="tablist" aria-label="学习计划类型">
        <button
          type="button"
          role="tab"
          aria-selected={view === "single"}
          className={view === "single" ? "active" : ""}
          onClick={() => setView("single")}
        >
          单课程计划
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={view === "multi"}
          className={view === "multi" ? "active" : ""}
          onClick={() => setView("multi")}
        >
          综合规划
        </button>
      </div>
      {view === "single" ? (
        <>
      <Toolbar count={items.length} label="份计划">
        <div className="toolbar-actions">
          <button className="btn ai-action" onClick={() => setAiOpen(true)}>
            <Sparkles size={15} />
            AI 生成计划
          </button>
          <button className="btn primary" onClick={() => setEdit(null)}>
            <Plus size={16} />
            新建计划
          </button>
        </div>
      </Toolbar>
      {items.length ? (
        <div className="plan-grid">
          {items.map((p) => (
            <article key={p.id} onClick={() => open(p)}>
              <div className="plan-top">
                <div className="plan-card-labels">
                  <Status value={p.status} />
                  {p.plan_type === "multi" && <span className="plan-type">综合</span>}
                </div>
                <button
                  className="icon-btn"
                  disabled={p.plan_type === "multi"}
                  title={p.plan_type === "multi" ? "综合规划请在详情中重新生成" : "编辑计划"}
                  onClick={(e) => {
                    e.stopPropagation();
                    if (p.plan_type !== "multi") setEdit(p);
                  }}
                >
                  <Settings2 size={15} />
                </button>
              </div>
              <h3>{p.title}</h3>
              <p>{p.goal || "尚未填写计划目标"}</p>
              <div className="date-range">
                <span>{dayText(p.start_date)}</span>
                <i />
                <span>{dayText(p.end_date)}</span>
              </div>
              <small>每天 {p.daily_minutes} 分钟</small>
            </article>
          ))}
        </div>
      ) : (
        <Empty
          title="还没有学习计划"
          text="从目标和截止日期开始，系统会帮你保持节奏"
        />
      )}
        </>
      ) : (
        <MultiCoursePlanner
          courses={courses.data || []}
          notify={notify}
          onCreated={(plan) => {
            setView("single");
            plans.reload();
            open(plan).catch((error) => notify(errorText(error)));
          }}
        />
      )}
      {edit !== undefined && (
        <Modal
          title={edit?.id ? "编辑学习计划" : "新建学习计划"}
          onClose={() => setEdit(undefined)}
        >
          <form className="form" onSubmit={save}>
            <label>
              计划名称
              <input name="title" required defaultValue={edit?.title} />
            </label>
            <label>
              学习目标
              <textarea name="goal" defaultValue={edit?.goal} />
            </label>
            <label>
              关联课程
              <CourseSelect
                courses={courses.data || []}
                value={edit?.course_id}
                onChange={() => {}}
                optional
              />
            </label>
            <div className="form-row">
              <label>
                开始日期
                <input
                  name="start_date"
                  type="date"
                  required
                  defaultValue={edit?.start_date}
                />
              </label>
              <label>
                结束日期
                <input
                  name="end_date"
                  type="date"
                  required
                  defaultValue={edit?.end_date}
                />
              </label>
            </div>
            <div className="form-row">
              <label>
                每日分钟
                <input
                  name="daily_minutes"
                  type="number"
                  min="1"
                  defaultValue={edit?.daily_minutes || 60}
                />
              </label>
              <label>
                状态
                <select name="status" defaultValue={edit?.status || "draft"}>
                  <option value="draft">草稿</option>
                  <option value="active">进行中</option>
                  <option value="completed">已完成</option>
                  <option value="cancelled">已取消</option>
                </select>
              </label>
            </div>
            <FormActions
              onCancel={() => setEdit(undefined)}
              submit="保存计划"
            />
          </form>
        </Modal>
      )}
      {aiOpen && (
        <AiCreator
          kind="plan"
          courses={courses.data || []}
          onClose={() => setAiOpen(false)}
          onDone={() => {
            setAiOpen(false);
            plans.reload();
          }}
          notify={notify}
        />
      )}
      {detail && (
        <PlanDetail
          plan={detail}
          onClose={() => setDetail(null)}
          onChange={() => {
            setDetail(null);
            plans.reload();
          }}
          notify={notify}
        />
      )}
    </>
  );
}
function PlanDetail({
  plan,
  onClose,
  onChange,
  notify,
}: {
  plan: Entity;
  onClose: () => void;
  onChange: () => void;
  notify: (s: string) => void;
}) {
  const [add, setAdd] = useState(false);
  const [aiOpen, setAiOpen] = useState(false);
  const [regenerationPreview, setRegenerationPreview] = useState<MultiCoursePlanPreview | null>(null);
  const [regenerating, setRegenerating] = useState(false);
  const courses = useData(() => api.courses(), []);
  const p = plan.progress || {};
  return (
    <Modal title={plan.title} onClose={onClose} wide>
      <div className="plan-detail">
        <div className="progress-summary">
          <div>
            <strong>{p.progress_percent || 0}%</strong>
            <span>计划进度</span>
          </div>
          <div>
            <b>
              {p.completed_tasks || 0}/{p.total_tasks || 0}
            </b>
            <span>已完成任务</span>
          </div>
          <div>
            <b>{p.estimated_total_minutes || 0}</b>
            <span>预计分钟</span>
          </div>
          <div className="toolbar-actions">
            {plan.plan_type === "multi" ? (
              <button
                className="btn ai-action"
                disabled={regenerating}
                onClick={async () => {
                  setRegenerating(true);
                  try {
                    setRegenerationPreview(await api.previewMultiPlanRegeneration(plan.id));
                  } catch (error) {
                    notify(errorText(error));
                  } finally {
                    setRegenerating(false);
                  }
                }}
              >
                <RotateCcw className={regenerating ? "spin" : ""} size={14} />
                {regenerating ? "计算中…" : "重新生成预览"}
              </button>
            ) : (
              <button
                className="btn ai-action"
                disabled={!plan.course_id}
                title={!plan.course_id ? "请先为计划关联课程" : undefined}
                onClick={() => setAiOpen(true)}
              >
                <Sparkles size={14} />
                AI 拆解任务
              </button>
            )}
            <button className="btn primary" onClick={() => setAdd(true)}>
              <Plus size={15} />
              添加日程任务
            </button>
          </div>
        </div>
        <div className="progress">
          <i style={{ width: `${p.progress_percent || 0}%` }} />
        </div>
        <div className="task-board slim">
          {plan.tasks.map((x: Entity) => (
            <article key={x.id}>
              <div className="task-check">
                {x.task.status === "completed" && <Check size={14} />}
              </div>
              <div className="task-body">
                <h3>{x.task.title}</h3>
                <small>
                  {dayText(x.planned_date)} · 第 {x.sequence_no} 项
                </small>
              </div>
              <Status value={x.task.status} />
              <button
                className="icon-btn danger"
                onClick={async () => {
                  await api.deletePlanTask(plan.id, x.task_id);
                  notify("计划任务已删除");
                  onChange();
                }}
              >
                <Trash2 size={15} />
              </button>
            </article>
          ))}
        </div>
        <button
          className="btn danger-text"
          onClick={async () => {
            if (confirm("删除整份计划及其任务？")) {
              await api.deletePlan(plan.id);
              onChange();
            }
          }}
        >
          删除这份计划
        </button>
        {add && (
          <Modal title="添加计划任务" onClose={() => setAdd(false)}>
            <form
              className="form"
              onSubmit={async (e) => {
                e.preventDefault();
                const b: any = Object.fromEntries(
                  new FormData(e.currentTarget),
                );
                b.sequence_no = Number(b.sequence_no);
                b.estimated_minutes = b.estimated_minutes
                  ? Number(b.estimated_minutes)
                  : null;
                await api.createPlanTask(plan.id, b);
                notify("日程任务已添加");
                onChange();
              }}
            >
              <label>
                任务标题
                <input name="title" required />
              </label>
              <label>
                说明
                <textarea name="description" />
              </label>
              <div className="form-row">
                <label>
                  计划日期
                  <input name="planned_date" type="date" required />
                </label>
                <label>
                  顺序
                  <input
                    name="sequence_no"
                    type="number"
                    min="1"
                    defaultValue="1"
                  />
                </label>
              </div>
              <div className="form-row">
                <label>
                  优先级
                  <select name="priority">
                    <option value="medium">中</option>
                    <option value="high">高</option>
                    <option value="low">低</option>
                  </select>
                </label>
                <label>
                  预计分钟
                  <input name="estimated_minutes" type="number" min="1" />
                </label>
              </div>
              <FormActions onCancel={() => setAdd(false)} submit="添加任务" />
            </form>
          </Modal>
        )}
        {aiOpen && (
          <AiCreator
            kind="plan_tasks"
            courses={courses.data || []}
            fixedCourseId={plan.course_id}
            planId={plan.id}
            onClose={() => setAiOpen(false)}
            onDone={() => {
              setAiOpen(false);
              onChange();
            }}
            notify={notify}
          />
        )}
        {regenerationPreview && (
          <Modal title="重新生成综合规划" onClose={() => setRegenerationPreview(null)} wide>
            <div className="regeneration-preview">
              <p className="regeneration-note">
                <RotateCcw size={17} />
                只替换这份计划中尚未完成的自动任务；已完成任务和手工任务会原样保留。
              </p>
              <div className="capacity-grid">
                <div><span>可用容量</span><b>{regenerationPreview.capacity_minutes}</b><small>分钟</small></div>
                <div><span>实际需求</span><b>{regenerationPreview.required_minutes}</b><small>分钟</small></div>
                <div><span>已安排</span><b>{regenerationPreview.scheduled_minutes}</b><small>分钟</small></div>
                <div className={regenerationPreview.unscheduled_minutes ? "overload" : ""}>
                  <span>未安排</span><b>{regenerationPreview.unscheduled_minutes}</b><small>分钟</small>
                </div>
              </div>
              {regenerationPreview.warnings.length > 0 && (
                <div className="multi-warnings">
                  <AlertTriangle size={17} />
                  <div>{regenerationPreview.warnings.map((warning) => <p key={warning}>{warning}</p>)}</div>
                </div>
              )}
              <div className="regeneration-days">
                {regenerationPreview.daily_schedule.map((day) => (
                  <article key={day.date}>
                    <header><b>{dayText(day.date)}</b><span>{day.total_minutes} 分钟</span></header>
                    {day.tasks.map((task) => (
                      <p key={`${day.date}-${task.course_id}`}>
                        <span>{task.course_name}</span><b>{task.estimated_minutes} 分钟</b>
                      </p>
                    ))}
                  </article>
                ))}
              </div>
              <div className="form-actions">
                <button type="button" className="btn subtle" onClick={() => setRegenerationPreview(null)}>取消</button>
                <button
                  type="button"
                  className="btn primary"
                  disabled={regenerating || !regenerationPreview.version}
                  onClick={async () => {
                    if (!regenerationPreview.version) return;
                    setRegenerating(true);
                    try {
                      await api.regenerateMultiPlan(plan.id, regenerationPreview.version);
                      notify("综合规划已重新生成");
                      setRegenerationPreview(null);
                      onChange();
                    } catch (error) {
                      notify(errorText(error));
                    } finally {
                      setRegenerating(false);
                    }
                  }}
                >
                  {regenerating ? "正在替换…" : "确认重新生成"}
                </button>
              </div>
            </div>
          </Modal>
        )}
      </div>
    </Modal>
  );
}
