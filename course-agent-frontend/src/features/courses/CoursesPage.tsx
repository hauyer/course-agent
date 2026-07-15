import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { BookOpen, Library, Network, Plus, RefreshCw, Search, Trash2, X } from "lucide-react";
import { api, type Entity } from "../../api";
import KnowledgeGraphPanel from "./KnowledgeGraphPanel";

function unwrap(data: any): Entity[] { return Array.isArray(data) ? data : data?.items || []; }
function errorText(error: unknown) { return error instanceof Error ? error.message : "操作失败"; }
function useData<T>(loader: () => Promise<T>, deps: any[] = []) { const [data,setData]=useState<T|null>(null),[error,setError]=useState(""),[loading,setLoading]=useState(true),[tick,setTick]=useState(0); useEffect(()=>{let live=true;setLoading(true);loader().then(value=>live&&setData(value)).catch(reason=>live&&setError(errorText(reason))).finally(()=>live&&setLoading(false));return()=>{live=false};},[...deps,tick]);return{data,error,loading,reload:()=>setTick(value=>value+1)}; }
function Loading({error}:{error?:string}){return <div className="empty"><RefreshCw className="spin" size={20}/><b>{error||"正在整理数据"}</b><span>{error?"检查后端服务后刷新页面":"请稍候"}</span></div>}
function Empty({title,text}:{title:string;text:string}){return <div className="empty"><Library size={24}/><b>{title}</b><span>{text}</span></div>}
function Modal({title,children,onClose}:{title:string;children:ReactNode;onClose:()=>void}){return createPortal(<div className="modal-backdrop" onMouseDown={onClose}><div className="modal" onMouseDown={event=>event.stopPropagation()}><div className="modal-head"><h2>{title}</h2><button className="icon-btn" onClick={onClose}><X size={18}/></button></div>{children}</div></div>,document.body)}
function FormActions({onCancel,submit}:{onCancel:()=>void;submit:string}){return <div className="form-actions"><button type="button" className="btn subtle" onClick={onCancel}>取消</button><button className="btn primary">{submit}</button></div>}


export default function CoursesPage({ notify }: { notify: (s: string) => void }) {
  const { data, loading, error, reload } = useData(() => api.courses(), []),
    [edit, setEdit] = useState<Entity | null | undefined>(),
    [keyword, setKeyword] = useState(""),
    [teacher, setTeacher] = useState(""),
    [semester, setSemester] = useState(""),
    [graphCourse, setGraphCourse] = useState<Entity | null>(null);
  const allCourses = unwrap(data);
  const teachers = useMemo(
    () =>
      [...new Set(allCourses.map((c) => c.teacher).filter(Boolean))].sort(
        (a, b) => String(a).localeCompare(String(b), "zh-CN"),
      ),
    [data],
  );
  const semesters = useMemo(
    () =>
      [...new Set(allCourses.map((c) => c.semester).filter(Boolean))].sort(
        (a, b) => String(b).localeCompare(String(a), "zh-CN"),
      ),
    [data],
  );
  const filteredCourses = useMemo(() => {
    const key = keyword.trim().toLocaleLowerCase();
    return allCourses.filter((course) => {
      const searchable = [
        course.name,
        course.description,
        course.teacher,
        course.semester,
      ]
        .filter(Boolean)
        .join(" ")
        .toLocaleLowerCase();
      return (
        (!key || searchable.includes(key)) &&
        (!teacher || course.teacher === teacher) &&
        (!semester || course.semester === semester)
      );
    });
  }, [allCourses, keyword, teacher, semester]);
  const filtering = Boolean(keyword.trim() || teacher || semester);
  const save = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const body: any = Object.fromEntries(new FormData(e.currentTarget));
    try {
      edit?.id
        ? await api.updateCourse(edit.id, body)
        : await api.createCourse(body);
      notify(edit?.id ? "课程已更新" : "课程已创建");
      setEdit(undefined);
      reload();
    } catch (x) {
      notify(errorText(x));
    }
  };
  if (loading) return <Loading error={error} />;
  return (
    <>
      <div className="course-toolbar">
        <label className="course-search">
          <Search size={16} />
          <input
            aria-label="搜索课程"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder="搜索课程名称、说明或教师"
          />
        </label>
        <select
          aria-label="按教师筛选"
          value={teacher}
          onChange={(e) => setTeacher(e.target.value)}
        >
          <option value="">全部教师</option>
          {teachers.map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </select>
        <select
          aria-label="按学期筛选"
          value={semester}
          onChange={(e) => setSemester(e.target.value)}
        >
          <option value="">全部学期</option>
          {semesters.map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </select>
        <button className="btn primary" onClick={() => setEdit(null)}>
          <Plus size={16} />
          添加课程
        </button>
      </div>
      <div className="course-count">
        <p>
          <b>{filteredCourses.length}</b> 门课程
          {filtering && <span> · 共 {allCourses.length} 门</span>}
        </p>
        {filtering && (
          <button
            className="text-btn"
            onClick={() => {
              setKeyword("");
              setTeacher("");
              setSemester("");
            }}
          >
            清除筛选
            <X size={13} />
          </button>
        )}
      </div>
      {filteredCourses.length ? (
        <div className="card-grid">
          {filteredCourses.map((c, i) => (
            <article className="course-card" key={c.id}>
              <div className="course-no">
                C-{String(i + 1).padStart(2, "0")}
              </div>
              <div className="course-icon">
                <BookOpen size={20} />
              </div>
              <h3>{c.name}</h3>
              <p>{c.description || "还没有课程说明"}</p>
              <dl>
                <div>
                  <dt>教师</dt>
                  <dd>{c.teacher || "—"}</dd>
                </div>
                <div>
                  <dt>学期</dt>
                  <dd>{c.semester || "—"}</dd>
                </div>
              </dl>
              <div className="card-actions">
                <button className="btn subtle" onClick={() => setGraphCourse(c)}>
                  <Network size={14} />
                  知识图谱
                </button>
                <button className="btn subtle" onClick={() => setEdit(c)}>
                  编辑
                </button>
                <button
                  className="icon-btn danger"
                  onClick={async () => {
                    if (confirm(`删除课程“${c.name}”？`)) {
                      await api.deleteCourse(c.id);
                      reload();
                      notify("课程已删除");
                    }
                  }}
                >
                  <Trash2 size={15} />
                </button>
              </div>
            </article>
          ))}
        </div>
      ) : allCourses.length ? (
        <Empty title="没有匹配的课程" text="换一个关键词或清除筛选条件" />
      ) : (
        <Empty title="还没有课程" text="添加第一门课程，再上传资料和安排任务" />
      )}
      {edit !== undefined && (
        <Modal
          title={edit?.id ? "编辑课程" : "添加课程"}
          onClose={() => setEdit(undefined)}
        >
          <form className="form" onSubmit={save}>
            <label>
              课程名称
              <input
                name="name"
                defaultValue={edit?.name}
                required
                maxLength={100}
              />
            </label>
            <label>
              课程说明
              <textarea name="description" defaultValue={edit?.description} />
            </label>
            <div className="form-row">
              <label>
                授课教师
                <input name="teacher" defaultValue={edit?.teacher} />
              </label>
              <label>
                学期
                <input
                  name="semester"
                  defaultValue={edit?.semester}
                  placeholder="如 2026 春"
                />
              </label>
            </div>
            <FormActions
              onCancel={() => setEdit(undefined)}
              submit="保存课程"
            />
          </form>
        </Modal>
      )}
      {graphCourse && (
        <KnowledgeGraphPanel
          course={graphCourse}
          onClose={() => setGraphCourse(null)}
          notify={notify}
        />
      )}
    </>
  );
}
