export const API_BASE = import.meta.env.VITE_API_URL || "/api";

export type Entity = Record<string, any>;

export interface MultiCoursePlanCourseInput {
  course_id: number;
  priority: number;
  deadline: string;
  target_minutes: number;
}

export interface MultiCoursePlanRequest {
  title: string;
  goal?: string;
  start_date: string;
  end_date: string;
  daily_minutes: number;
  available_weekdays: number[];
  courses: MultiCoursePlanCourseInput[];
  client_request_id: string;
}

export interface MultiCourseAllocation {
  course_id: number;
  course_name: string;
  priority: number;
  deadline: string;
  target_minutes: number;
  progress_percent: number;
  existing_task_minutes: number;
  required_minutes: number;
  scheduled_minutes: number;
  unscheduled_minutes: number;
  weight: number;
}

export interface MultiCourseScheduledTask {
  course_id: number;
  course_name: string;
  title: string;
  description: string;
  priority: "low" | "medium" | "high" | "urgent";
  estimated_minutes: number;
  planned_date: string;
  due_at: string;
}

export interface MultiCourseDailySchedule {
  date: string;
  total_minutes: number;
  tasks: MultiCourseScheduledTask[];
  course_summary: Array<{
    course_id: number;
    course_name: string;
    minutes: number;
  }>;
  warnings: string[];
}

export interface MultiCoursePlanPreview {
  capacity_minutes: number;
  required_minutes: number;
  scheduled_minutes: number;
  unscheduled_minutes: number;
  warnings: string[];
  daily_schedule: MultiCourseDailySchedule[];
  course_summary: MultiCourseAllocation[];
  version?: number;
}

export interface MultiCoursePlanCreateResult {
  plan: Entity;
  preview: MultiCoursePlanPreview;
  created: boolean;
}

export type KnowledgeGraphJobStatus =
  | "pending"
  | "running"
  | "succeeded"
  | "partial"
  | "failed"
  | "cancelled";

export interface KnowledgeGraphJob {
  id: number;
  user_id: number;
  course_id: number;
  status: KnowledgeGraphJobStatus;
  progress: number;
  stage: string;
  source_hash?: string | null;
  is_active: boolean;
  node_count: number;
  edge_count: number;
  error_message?: string | null;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface KnowledgeGraphSource {
  course_id: number;
  course_name: string;
  material_id: number;
  material_title: string;
  chunk_id: number;
  chunk_index: number;
  page_no?: number | null;
  evidence_text: string;
}

export interface KnowledgeGraphNode {
  id: number;
  name: string;
  node_type: string;
  description?: string | null;
  importance: number;
  confidence: number;
  sources: KnowledgeGraphSource[];
}

export interface KnowledgeGraphEdge {
  id: number;
  source: number;
  target: number;
  relation_type: string;
  weight: number;
  confidence: number;
  sources: KnowledgeGraphSource[];
}

export interface KnowledgeGraph {
  course_id: number;
  course_name: string;
  job_id: number;
  generated_at: string;
  nodes: KnowledgeGraphNode[];
  edges: KnowledgeGraphEdge[];
}

export interface SemanticSearchRequest {
  course_id: number;
  query: string;
  top_k?: number;
  min_similarity?: number;
  material_ids?: number[];
  file_types?: string[];
}

export interface SemanticSearchItem {
  vector_id: string;
  chunk_id: number;
  chunk_index: number;
  course_id: number;
  course_name: string;
  material_id: number;
  material_title: string;
  file_type?: string | null;
  page_no?: number | null;
  content: string;
  distance: number;
  similarity_score: number;
  similarity_percent: number;
}

export interface SemanticSearchResponse {
  course_id: number;
  query: string;
  metric: "cosine";
  min_similarity: number;
  total: number;
  results: SemanticSearchItem[];
}

export function uploadRequest<T = any>(
  endpoint: string,
  body: FormData,
  onProgress?: (percent: number, loaded: number, total: number) => void,
): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}${endpoint}`);
    const token = localStorage.getItem("access_token");
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        onProgress?.(Math.round(event.loaded / event.total * 100), event.loaded, event.total);
      }
    };
    xhr.onerror = () => reject(new Error("上传连接中断，请检查网络或后端服务"));
    xhr.onload = () => {
      let data: any = xhr.responseText;
      try { data = JSON.parse(xhr.responseText || "{}"); } catch { /* 保留文本错误 */ }
      if (xhr.status >= 200 && xhr.status < 300) {
        onProgress?.(100, 1, 1);
        resolve(data as T);
      } else {
        reject(new Error(String(data?.detail || data || `上传失败（${xhr.status}）`)));
      }
    };
    xhr.send(body);
  });
}

async function downloadRequest(endpoint: string, body: FormData): Promise<Blob> {
  const token = localStorage.getItem("access_token");
  const response = await fetch(`${API_BASE}${endpoint}`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body,
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || `导出失败（${response.status}）`);
  }
  return response.blob();
}

export async function request<T = any>(
  endpoint: string,
  options: RequestInit = {},
): Promise<T> {
  const token = localStorage.getItem("access_token");
  const headers = new Headers(options.headers);
  if (!(options.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${endpoint}`, { ...options, headers });
  } catch {
    throw new Error("无法连接本地后端服务，请稍后重试或重新启动程序");
  }
  if (response.status === 401) {
    localStorage.removeItem("access_token");
    localStorage.removeItem("current_user");
    window.dispatchEvent(new Event("auth-expired"));
  }
  if (response.status === 204) return {} as T;
  const isJson = response.headers
    .get("content-type")
    ?.includes("application/json");
  const data = isJson ? await response.json() : await response.text();
  if (!response.ok) {
    const detail = data?.detail;
    let message = Array.isArray(detail)
      ? detail.map((x: any) => x.msg).join("；")
      : detail || data || `请求失败（${response.status}）`;
    if (response.status === 404 && String(message).trim() === "Not Found") {
      message = "当前桌面端连接到了不兼容的旧后端，请完全退出旧版本后重新打开程序";
    }
    throw new Error(String(message));
  }
  return data as T;
}

export const api = {
  login: (body: Entity) =>
    request("/auth/login", { method: "POST", body: JSON.stringify(body) }),
  register: (body: Entity) =>
    request("/auth/register", { method: "POST", body: JSON.stringify(body) }),
  me: () => request("/auth/me"),
  updateAvatar: (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return request("/auth/avatar", { method: "PUT", body });
  },
  deleteAvatar: () => request("/auth/avatar", { method: "DELETE" }),
  changePassword: (body: Entity) =>
    request("/auth/password", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  verifyPassword: (currentPassword: string) =>
    request("/auth/password/verify", {
      method: "POST",
      body: JSON.stringify({ current_password: currentPassword }),
    }),
  llmConfig: () => request("/auth/llm-config"),
  saveLlmConfig: (body: Entity) =>
    request("/auth/llm-config", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  disableLlmConfig: (currentPassword: string) =>
    request("/auth/llm-config", {
      method: "DELETE",
      body: JSON.stringify({ current_password: currentPassword }),
    }),
  dashboard: (days = 7) => request(`/dashboard/overview?trend_days=${days}`),
  courses: () => request<Entity[]>("/courses"),
  createCourse: (body: Entity) =>
    request("/courses", { method: "POST", body: JSON.stringify(body) }),
  updateCourse: (id: number, body: Entity) =>
    request(`/courses/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  deleteCourse: (id: number) => request(`/courses/${id}`, { method: "DELETE" }),
  createKnowledgeGraphJob: (courseId: number) =>
    request<KnowledgeGraphJob>(`/courses/${courseId}/knowledge-graph/jobs`, {
      method: "POST",
    }),
  knowledgeGraphJob: (courseId: number, jobId: number) =>
    request<KnowledgeGraphJob>(
      `/courses/${courseId}/knowledge-graph/jobs/${jobId}`,
    ),
  knowledgeGraph: (courseId: number) =>
    request<KnowledgeGraph>(`/courses/${courseId}/knowledge-graph`),
  knowledgeGraphVersions: (courseId: number) =>
    request<{ total: number; items: KnowledgeGraphJob[] }>(
      `/courses/${courseId}/knowledge-graph/versions`,
    ),
  cancelKnowledgeGraphJob: (courseId: number, jobId: number) =>
    request<{ status: "cancelled" | "deleted" }>(
      `/courses/${courseId}/knowledge-graph/jobs/${jobId}`,
      { method: "DELETE" },
    ),
  materials: (courseId: number) =>
    request<Entity[]>(`/courses/${courseId}/materials`),
  uploadMaterial: (
    courseId: number,
    form: FormData,
    onProgress?: (percent: number, loaded: number, total: number) => void,
  ) => uploadRequest(`/courses/${courseId}/materials`, form, onProgress),
  materialText: (id: number) => request(`/materials/${id}/text`),
  materialChunks: (id: number, skip = 0) =>
    request(`/materials/${id}/chunks?skip=${skip}&limit=100`),
  parseMaterial: (id: number) =>
    request(`/materials/${id}/parse`, { method: "POST" }),
  rebuildChunks: (id: number, size = 800, overlap = 120) =>
    request(
      `/materials/${id}/chunks/rebuild?chunk_size=${size}&chunk_overlap=${overlap}`,
      { method: "POST" },
    ),
  rebuildVectors: (id: number) =>
    request(`/materials/${id}/vectors/rebuild`, { method: "POST" }),
  deleteMaterial: (id: number) =>
    request(`/materials/${id}`, { method: "DELETE" }),
  deleteAllMaterials: () => request("/materials", { method: "DELETE" }),
  search: (body: SemanticSearchRequest) =>
    request<SemanticSearchResponse>("/search/semantic", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  tasks: (query = "") => request(`/tasks${query ? `?${query}` : ""}`),
  taskOverview: () => request("/tasks/overview"),
  createTask: (body: Entity) =>
    request("/tasks", { method: "POST", body: JSON.stringify(body) }),
  updateTask: (id: number, body: Entity) =>
    request(`/tasks/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  taskStatus: (id: number, status: string) =>
    request(`/tasks/${id}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }),
  deleteTask: (id: number) => request(`/tasks/${id}`, { method: "DELETE" }),
  plans: () => request("/study-plans"),
  createPlan: (body: Entity) =>
    request("/study-plans", { method: "POST", body: JSON.stringify(body) }),
  updatePlan: (id: number, body: Entity) =>
    request(`/study-plans/${id}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  planStatus: (id: number, status: string) =>
    request(`/study-plans/${id}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }),
  planTasks: (id: number) => request(`/study-plans/${id}/tasks`),
  planProgress: (id: number) => request(`/study-plans/${id}/progress`),
  createPlanTask: (id: number, body: Entity) =>
    request(`/study-plans/${id}/tasks`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  deletePlanTask: (planId: number, taskId: number) =>
    request(`/study-plans/${planId}/tasks/${taskId}`, { method: "DELETE" }),
  deletePlan: (id: number) =>
    request(`/study-plans/${id}`, { method: "DELETE" }),
  multiPlanPreview: (body: MultiCoursePlanRequest) =>
    request<MultiCoursePlanPreview>("/study-plans/multi/preview", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  createMultiPlan: (body: MultiCoursePlanRequest) =>
    request<MultiCoursePlanCreateResult>("/study-plans/multi", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  multiPlanCourses: (id: number) =>
    request<{
      total: number;
      items: Array<{
        id: number;
        course_id: number;
        course_name: string;
        priority: number;
        deadline: string;
        target_minutes: number;
        weight: number;
      }>;
    }>(`/study-plans/${id}/courses`),
  multiPlanSchedule: (id: number) =>
    request<MultiCourseDailySchedule[]>(`/study-plans/${id}/schedule`),
  previewMultiPlanRegeneration: (id: number) =>
    request<MultiCoursePlanPreview>(
      `/study-plans/${id}/multi/preview-regeneration`,
      { method: "POST" },
    ),
  regenerateMultiPlan: (id: number, expectedVersion: number) =>
    request<MultiCoursePlanCreateResult>(
      `/study-plans/${id}/multi/regenerate`,
      {
        method: "POST",
        body: JSON.stringify({ expected_version: expectedVersion }),
      },
    ),
  notes: (query = "") => request(`/notes${query ? `?${query}` : ""}`),
  createNote: (body: Entity) =>
    request("/notes", { method: "POST", body: JSON.stringify(body) }),
  updateNote: (id: number, body: Entity) =>
    request(`/notes/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  deleteNote: (id: number) => request(`/notes/${id}`, { method: "DELETE" }),
  syncNote: (id: number, provider: "notion" | "obsidian") =>
    request(`/notes/${id}/sync/${provider}`, { method: "POST" }),
  syncRecords: (id: number) => request(`/notes/${id}/sync-records`),
  testIntegration: (provider: "notion" | "obsidian") =>
    request(`/notes/integrations/${provider}/test`, { method: "POST" }),
  integrationConfig: () => request("/notes/integrations/config"),
  saveIntegrationConfig: (body: Entity) =>
    request("/notes/integrations/config", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  records: () => request("/learning/records?limit=200"),
  summary: (courseId?: number) =>
    request(`/learning/summary${courseId ? `?course_id=${courseId}` : ""}`),
  createRecord: (body: Entity) =>
    request("/learning/records", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateRecord: (id: number, body: Entity) =>
    request(`/learning/records/${id}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  deleteRecord: (id: number) =>
    request(`/learning/records/${id}`, { method: "DELETE" }),
  courseProgress: (id: number) => request(`/learning/courses/${id}/progress`),
  updateProgress: (id: number, body: Entity) =>
    request(`/learning/courses/${id}/progress`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  sessions: (courseId?: number) =>
    request(`/agent/sessions${courseId ? `?course_id=${courseId}` : ""}`),
  messages: (id: number) => request(`/agent/sessions/${id}/messages`),
  chat: (body: Entity) =>
    request("/agent/chat", { method: "POST", body: JSON.stringify(body) }),
  deleteSession: (id: number) =>
    request(`/agent/sessions/${id}`, { method: "DELETE" }),
  auditOverview: () => request("/audit/overview"),
  auditLogs: (category = "") =>
    request(`/audit/logs?limit=150${category ? `&category=${category}` : ""}`),
  exportBackup: (currentPassword: string) => {
    const form = new FormData();
    form.set("current_password", currentPassword);
    return downloadRequest("/backup/export", form);
  },
  importBackup: (
    currentPassword: string,
    file: File,
    onProgress?: (percent: number, loaded: number, total: number) => void,
  ) => {
    const form = new FormData();
    form.set("current_password", currentPassword);
    form.set("file", file);
    return uploadRequest("/backup/import", form, onProgress);
  },
};

export async function streamAgent(
  body: Entity,
  onEvent: (event: Entity) => void,
): Promise<Entity> {
  const token = localStorage.getItem("access_token");
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/agent/chat/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
    });
  } catch {
    throw new Error("无法连接后端服务，请确认 FastAPI 已启动");
  }
  if (!response.ok || !response.body) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || `Agent 请求失败（${response.status}）`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result: Entity = {};
  let persisted: Entity = {};
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() || "";
    for (const frame of frames) {
      const payload = frame
        .split("\n")
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trim())
        .join("\n");
      if (!payload || payload === "[DONE]") continue;
      const event = JSON.parse(payload);
      onEvent(event);
      if (event.type === "persisted") persisted = event;
      if (event.type === "result") result = event;
      if (event.type === "error")
        throw Object.assign(new Error(event.message || "Agent 执行失败"), {
          sessionId: event.session_id || persisted.session_id,
        });
    }
    if (done) break;
  }
  if (!result.session_id) {
    throw Object.assign(new Error("Agent 连接提前结束，已保留当前对话记录"), {
      sessionId: persisted.session_id,
    });
  }
  return result;
}
