import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { CircleHelp, FileText, Files, Library, RefreshCw, Trash2, Upload, X } from "lucide-react";
import { api, type Entity } from "../../api";
import { useAsyncData as useData } from "../../shared/useAsyncData";
import "./materials.css";

type UploadJob = {
  id: string;
  name: string;
  percent: number;
  status: "uploading" | "processing" | "done" | "error";
  error?: string;
};

type PendingFile = {
  id: string;
  courseId: number;
  file: File;
  status: "ready" | "uploading";
};

const ACCEPTED_EXTENSIONS = new Set(["pdf", "docx", "pptx", "txt", "md"]);
const MAX_FILE_SIZE = 20 * 1024 * 1024;
const MAX_PENDING_FILES = 10;

let uploadJobs: UploadJob[] = [];
const uploadCleanupTimers = new Map<string, number>();
const uploadListeners = new Set<(jobs: UploadJob[]) => void>();
function publishUploads() {
  const snapshot = [...uploadJobs];
  uploadListeners.forEach((listener) => listener(snapshot));
}
function updateUpload(id: string, patch: Partial<UploadJob>) {
  uploadJobs = uploadJobs.map((job) => job.id === id ? { ...job, ...patch } : job).slice(-50);
  publishUploads();
  if (patch.status === "done" && !uploadCleanupTimers.has(id)) {
    const timer = window.setTimeout(() => {
      uploadJobs = uploadJobs.filter((job) => job.id !== id);
      uploadCleanupTimers.delete(id);
      publishUploads();
    }, 2200);
    uploadCleanupTimers.set(id, timer);
  }
}
function removeUpload(id: string) {
  const timer = uploadCleanupTimers.get(id);
  if (timer) window.clearTimeout(timer);
  uploadCleanupTimers.delete(id);
  uploadJobs = uploadJobs.filter((job) => job.id !== id);
  publishUploads();
}
function useUploadJobs() {
  const [jobs, setJobs] = useState<UploadJob[]>(uploadJobs);
  useEffect(() => {
    uploadListeners.add(setJobs);
    setJobs([...uploadJobs]);
    return () => { uploadListeners.delete(setJobs); };
  }, []);
  return jobs;
}

let pendingFiles: PendingFile[] = [];
const pendingListeners = new Set<(files: PendingFile[]) => void>();
function publishPending() {
  const snapshot = [...pendingFiles];
  pendingListeners.forEach((listener) => listener(snapshot));
}
function usePendingFiles() {
  const [files, setFiles] = useState<PendingFile[]>(pendingFiles);
  useEffect(() => {
    pendingListeners.add(setFiles);
    setFiles([...pendingFiles]);
    return () => { pendingListeners.delete(setFiles); };
  }, []);
  return files;
}
function updatePending(id: string, patch: Partial<PendingFile>) {
  pendingFiles = pendingFiles.map((item) => item.id === id ? { ...item, ...patch } : item);
  publishPending();
}
function removePending(id: string) {
  pendingFiles = pendingFiles.filter((item) => item.id !== id);
  publishPending();
}
function addPendingFiles(courseId: number, incoming: File[]) {
  const errors: string[] = [];
  for (const file of incoming) {
    if (pendingFiles.length >= MAX_PENDING_FILES) {
      errors.push(`一次最多确认 ${MAX_PENDING_FILES} 个文件`);
      break;
    }
    const extension = file.name.split(".").pop()?.toLowerCase() || "";
    if (!ACCEPTED_EXTENSIONS.has(extension)) {
      errors.push(`${file.name}：不支持该文件类型`);
      continue;
    }
    if (!file.size) {
      errors.push(`${file.name}：不能上传空文件`);
      continue;
    }
    if (file.size > MAX_FILE_SIZE) {
      errors.push(`${file.name}：超过 20 MB`);
      continue;
    }
    const duplicate = pendingFiles.some(
      (item) => item.courseId === courseId
        && item.file.name === file.name
        && item.file.size === file.size
        && item.file.lastModified === file.lastModified,
    );
    if (duplicate) {
      errors.push(`${file.name}：已经在待上传清单中`);
      continue;
    }
    pendingFiles.push({
      id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
      courseId,
      file,
      status: "ready",
    });
  }
  publishPending();
  return errors;
}

const processingByCourse = new Map<number, Map<number, string>>();
const activeCourseWatchers = new Set<number>();
function watchProcessing(courseId: number, materialId: number, jobId: string) {
  const materials = processingByCourse.get(courseId) || new Map<number, string>();
  materials.set(materialId, jobId);
  processingByCourse.set(courseId, materials);
  if (activeCourseWatchers.has(courseId)) return;
  activeCourseWatchers.add(courseId);
  void (async () => {
    for (let attempt = 0; attempt < 120; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, 2000));
      const pending = processingByCourse.get(courseId);
      if (!pending?.size) break;
      try {
        const materialsResponse: any = await api.materials(courseId);
        const current = unwrap(materialsResponse);
        for (const [currentMaterialId, currentJobId] of [...pending.entries()]) {
          const material = current.find((item) => Number(item.id) === currentMaterialId);
          if (material?.parse_status === "success") {
            updateUpload(currentJobId, { status: "done", percent: 100 });
            pending.delete(currentMaterialId);
          } else if (material?.parse_status === "failed") {
            updateUpload(currentJobId, { status: "error", error: material.parse_error || "资料解析失败" });
            pending.delete(currentMaterialId);
          }
        }
      } catch {
        // 页面切换或短暂断网不会中止后台任务，下一轮继续确认状态。
      }
    }
    const unfinished = processingByCourse.get(courseId);
    unfinished?.forEach((currentJobId) => {
      updateUpload(currentJobId, { status: "processing", error: "后台仍在处理，可稍后刷新资料列表查看" });
    });
    processingByCourse.delete(courseId);
    activeCourseWatchers.delete(courseId);
  })();
}

async function startUpload(courseId: number, file: File, title?: string) {
  const form = new FormData();
  form.set("file", file);
  if (title?.trim()) form.set("title", title.trim());
  const id = `${Date.now()}-${Math.random()}`;
  const job: UploadJob = {
    id,
    name: file.name || "课程资料",
    percent: 0,
    status: "uploading",
  };
  uploadJobs = [...uploadJobs, job].slice(-50);
  publishUploads();
  try {
    const result: any = await api.uploadMaterial(courseId, form, (percent) => updateUpload(id, { percent }));
    updateUpload(id, { percent: 100, status: "processing" });
    watchProcessing(courseId, Number(result.id), id);
    return result;
  } catch (error) {
    updateUpload(id, { status: "error", error: errorText(error) });
    throw error;
  }
}

function unwrap(data:any):Entity[]{return Array.isArray(data)?data:data?.items||[]}
function errorText(error:unknown){return error instanceof Error?error.message:"操作失败"}
function dateText(value?:string){return value?new Intl.DateTimeFormat("zh-CN",{month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit"}).format(new Date(value)):"—"}
function Loading({error}:{error?:string}){return <div className="empty"><RefreshCw className="spin" size={20}/><b>{error||"正在整理数据"}</b><span>{error?"检查后端服务后刷新页面":"请稍候"}</span></div>}
function Empty({title,text}:{title:string;text:string}){return <div className="empty"><Library size={24}/><b>{title}</b><span>{text}</span></div>}
function Modal({title,children,onClose,wide=false}:{title:string;children:ReactNode;onClose:()=>void;wide?:boolean}){return createPortal(<div className="modal-backdrop" onMouseDown={onClose}><div className={`modal ${wide?"wide":""}`} onMouseDown={event=>event.stopPropagation()}><div className="modal-head"><h2>{title}</h2><button className="icon-btn" onClick={onClose}><X size={18}/></button></div>{children}</div></div>,document.body)}
function CourseSelect({courses,value,onChange}:{courses:Entity[];value?:any;onChange:(value:string)=>void}){return <select value={value||""} onChange={event=>onChange(event.target.value)} required><option value="">选择课程</option>{courses.map(course=><option key={course.id} value={course.id}>{course.name}</option>)}</select>}
function Status({value}:{value:string}){const labels:Record<string,string>={pending:"待处理",processing:"处理中",success:"已完成",failed:"失败"};return <span className={`status ${value}`}>{labels[value]||value}</span>}

export default function MaterialsPage({ notify }: { notify: (message: string) => void }) {
  const courses = useData(() => api.courses(), []),
    [cid, setCid] = useState<number>(0),
    [view, setView] = useState<Entity | null>(null),
    [title, setTitle] = useState(""),
    jobs = useUploadJobs(),
    selectedFiles = usePendingFiles();
  useEffect(() => {
    if (!cid && courses.data?.[0]) setCid(courses.data[0].id);
  }, [courses.data, cid]);
  const mats = useData(
    () => (cid ? api.materials(cid) : Promise.resolve([])),
    [cid],
  );
  const qualityNotice = String(view?.text?.text_preview || "")
    .split("\n")
    .find((line) => line.includes("文本质量提示"));
  const upload = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const ready = selectedFiles.filter((item) => item.status === "ready");
    if (!ready.length) return;
    ready.forEach((item) => updatePending(item.id, { status: "uploading" }));
    let cursor = 0;
    let succeeded = 0;
    let failed = 0;
    const worker = async () => {
      while (cursor < ready.length) {
        const item = ready[cursor++];
        try {
          await startUpload(item.courseId, item.file, ready.length === 1 ? title : undefined);
          removePending(item.id);
          succeeded += 1;
        } catch {
          updatePending(item.id, { status: "ready" });
          failed += 1;
        }
      }
    };
    await Promise.all(Array.from({ length: Math.min(3, ready.length) }, worker));
    if (succeeded) {
      notify(`${succeeded} 个文件已上传，解析与向量化将在后台继续${failed ? `；${failed} 个失败，可重试` : ""}`);
      setTitle("");
      mats.reload();
    } else {
      notify("文件上传失败，请查看上传队列中的错误信息");
    }
  };
  if (courses.loading) return <Loading error={courses.error} />;
  if (!courses.data?.length)
    return <Empty title="请先添加课程" text="资料需要归入一门课程" />;
  return (
    <>
      <div className="split-toolbar">
        <CourseSelect
          courses={courses.data}
          value={cid}
          onChange={(v) => setCid(Number(v))}
        />
        <form className="upload-inline" onSubmit={upload}>
          <input
            name="title"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder={selectedFiles.length > 1 ? "多文件将使用各自文件名" : "资料标题（选填）"}
            disabled={selectedFiles.length > 1}
          />
          <label className="file-btn">
            <Upload size={15} />
            选择文件{selectedFiles.length ? ` (${selectedFiles.length})` : ""}
            <input
              name="file"
              type="file"
              accept=".pdf,.docx,.pptx,.txt,.md"
              multiple
              onChange={(event) => {
                const errors = addPendingFiles(cid, Array.from(event.target.files || []));
                if (errors.length) notify(errors.slice(0, 3).join("；"));
                event.target.value = "";
              }}
            />
          </label>
          <button
            className="btn primary"
            disabled={
              !selectedFiles.some((item) => item.status === "ready")
              || selectedFiles.some((item) => item.status === "uploading")
            }
          >
            上传 {selectedFiles.filter((item) => item.status === "ready").length || ""}
          </button>
        </form>
      </div>
      {selectedFiles.length > 0 && (
        <div className="pending-upload-panel">
          <header>
            <div><Files size={17} /><b>确认待上传文件</b></div>
            <span>最多 10 个，上传时并行处理 3 个</span>
          </header>
          <div>
            {selectedFiles.map((item) => {
              const course = courses.data?.find((value) => value.id === item.courseId);
              return (
                <article key={item.id}>
                  <FileText size={17} />
                  <div>
                    <b>{item.file.name}</b>
                    <span>{course?.name || "未知课程"} · {(item.file.size / 1024 / 1024).toFixed(2)} MB</span>
                  </div>
                  {item.status === "uploading" ? (
                    <span className="pending-state"><RefreshCw className="spin" size={13} />正在上传</span>
                  ) : (
                    <button type="button" className="icon-btn" title="移出清单" onClick={() => removePending(item.id)}>
                      <X size={15} />
                    </button>
                  )}
                </article>
              );
            })}
          </div>
        </div>
      )}
      {jobs.length > 0 && (
        <div className="upload-queue" aria-live="polite">
          {jobs.map((job) => (
            <article key={job.id} className={job.status}>
              <div><b>{job.name}</b><span>{job.status === "uploading" ? `上传中 ${job.percent}%` : job.status === "processing" ? "已接收，后台解析中" : job.status === "done" ? "上传完成" : job.error || "上传失败"}</span></div>
              <i><em style={{ width: `${job.percent}%` }} /></i>
              {(job.status === "done" || job.status === "error") && (
                <button className="icon-btn" type="button" title="关闭" onClick={() => removeUpload(job.id)}><X size={14} /></button>
              )}
            </article>
          ))}
        </div>
      )}
      <div className="hint">
        <CircleHelp size={15} />
        支持一次选择多个 PDF、Word、PPT、TXT、Markdown；单个文件不超过 20 MB。
      </div>
      {mats.loading ? (
        <Loading />
      ) : unwrap(mats.data).length ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>资料</th>
                <th>类型</th>
                <th>大小</th>
                <th>解析状态</th>
                <th>上传时间</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {unwrap(mats.data).map((m) => (
                <tr key={m.id}>
                  <td>
                    <button
                      className="link-cell"
                      onClick={async () => {
                        try {
                          const [text, chunks] = await Promise.all([
                            api.materialText(m.id),
                            api.materialChunks(m.id),
                          ]);
                          setView({ ...m, text, chunks });
                        } catch (x) {
                          notify(errorText(x));
                        }
                      }}
                    >
                      <FileText size={17} />
                      <span>
                        <b>{m.title}</b>
                        <small>{m.original_filename}</small>
                      </span>
                    </button>
                  </td>
                  <td>{String(m.file_type).toUpperCase()}</td>
                  <td>{(m.file_size / 1024 / 1024).toFixed(2)} MB</td>
                  <td>
                    <Status value={m.parse_status} />
                  </td>
                  <td>{dateText(m.created_at)}</td>
                  <td>
                    <div className="row-actions">
                      <button
                        className="icon-btn"
                        title="重新解析"
                        onClick={async () => {
                          await api.parseMaterial(m.id);
                          mats.reload();
                          notify("已重新解析");
                        }}
                      >
                        <RefreshCw size={15} />
                      </button>
                      <button
                        className="icon-btn danger"
                        onClick={async () => {
                          if (confirm("删除这份资料？")) {
                            await api.deleteMaterial(m.id);
                            mats.reload();
                            notify("资料已删除");
                          }
                        }}
                      >
                        <Trash2 size={15} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <Empty
          title="这门课程还没有资料"
          text="上传课件或文档，系统会自动提取文本"
        />
      )}
      {view && (
        <Modal title={view.title} onClose={() => setView(null)} wide>
          <div className="material-detail">
            <div className="detail-actions">
              <button
                className="btn subtle"
                onClick={async () => {
                  await api.rebuildChunks(view.id);
                  notify("文本分块已重建");
                }}
              >
                重建分块
              </button>
              <button
                className="btn primary"
                onClick={async () => {
                  await api.rebuildVectors(view.id);
                  notify("向量索引已重建");
                }}
              >
                建立检索索引
              </button>
            </div>
            <dl className="meta">
              <div>
                <dt>解析状态</dt>
                <dd>{view.parse_status}</dd>
              </div>
              <div>
                <dt>字符数</dt>
                <dd>{view.text?.text_length || 0}</dd>
              </div>
              <div>
                <dt>文本分块</dt>
                <dd>{view.chunks?.total || 0}</dd>
              </div>
            </dl>
            <h3>文本预览</h3>
            {qualityNotice && (
              <div className="material-quality-warning" role="status">
                <CircleHelp size={17} />
                <div>
                  <b>该 PDF 的文本层质量较差</b>
                  <span>{qualityNotice.replace(/^\s*\[?|\]?\s*$/g, "")}</span>
                </div>
              </div>
            )}
            <pre>{view.text?.text_preview || "暂无可预览文本"}</pre>
            <h3>分块内容</h3>
            <div className="chunks">
              {unwrap(view.chunks).map((c: Entity) => (
                <div key={c.id}>
                  <span>
                    #{c.chunk_index + 1}
                    {c.page_no ? ` · 第 ${c.page_no} 页` : ""}
                  </span>
                  <p>{c.content}</p>
                </div>
              ))}
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}
