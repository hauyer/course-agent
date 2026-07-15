import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  AlertTriangle,
  BookOpen,
  CheckCircle2,
  Clock3,
  Network,
  RefreshCw,
  Search,
  X,
} from "lucide-react";
import {
  api,
  type Entity,
  type KnowledgeGraph,
  type KnowledgeGraphEdge,
  type KnowledgeGraphJob,
  type KnowledgeGraphNode,
  type KnowledgeGraphSource,
} from "../../api";
import "./knowledge-graph.css";

type SelectedItem =
  | { kind: "node"; value: KnowledgeGraphNode }
  | { kind: "edge"; value: KnowledgeGraphEdge }
  | null;

const terminalStatuses = new Set(["succeeded", "partial", "failed", "cancelled"]);
const statusNames: Record<string, string> = {
  pending: "等待开始",
  running: "生成中",
  succeeded: "已完成",
  partial: "部分完成",
  failed: "失败",
  cancelled: "已取消",
};
const relationNames: Record<string, string> = {
  prerequisite: "前置知识",
  contains: "包含",
  part_of: "属于",
  related_to: "相关",
  contrast: "对比",
  applies_to: "应用于",
};

function errorText(error: unknown) {
  return error instanceof Error ? error.message : "操作失败";
}

function timeText(value?: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function Sources({ sources }: { sources: KnowledgeGraphSource[] }) {
  return (
    <div className="graph-sources">
      <h4>证据来源</h4>
      {sources.map((source) => (
        <details key={`${source.material_id}-${source.chunk_id}`}>
          <summary>
            <span>{source.material_title}</span>
            <small>
              {source.page_no ? `第 ${source.page_no} 页 · ` : ""}
              片段 #{source.chunk_index + 1}
            </small>
          </summary>
          <p>{source.evidence_text}</p>
        </details>
      ))}
    </div>
  );
}

export default function KnowledgeGraphPanel({
  course,
  onClose,
  notify,
}: {
  course: Entity;
  onClose: () => void;
  notify: (message: string) => void;
}) {
  const chartElement = useRef<HTMLDivElement | null>(null);
  const chartInstance = useRef<import("echarts/core").EChartsType | null>(null);
  const [graph, setGraph] = useState<KnowledgeGraph | null>(null);
  const [versions, setVersions] = useState<KnowledgeGraphJob[]>([]);
  const [job, setJob] = useState<KnowledgeGraphJob | null>(null);
  const [selected, setSelected] = useState<SelectedItem>(null);
  const [keyword, setKeyword] = useState("");
  const [nodeType, setNodeType] = useState("");
  const [relationType, setRelationType] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    setError("");
    try {
      const versionResult = await api.knowledgeGraphVersions(course.id);
      setVersions(versionResult.items);
      const active = versionResult.items.find((item) =>
        item.status === "pending" || item.status === "running"
      );
      if (active) setJob(active);
      try {
        setGraph(await api.knowledgeGraph(course.id));
      } catch (graphError) {
        const message = errorText(graphError);
        if (!message.includes("还没有成功生成")) setError(message);
        setGraph(null);
      }
    } catch (refreshError) {
      setError(errorText(refreshError));
    } finally {
      setLoading(false);
    }
  }, [course.id]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!job || terminalStatuses.has(job.status)) return;
    let disposed = false;
    let timer: number | undefined;
    const poll = async () => {
      try {
        const current = await api.knowledgeGraphJob(course.id, job.id);
        if (disposed) return;
        setJob(current);
        if (terminalStatuses.has(current.status)) {
          await refresh();
          return;
        }
      } catch (pollError) {
        if (!disposed) setError(errorText(pollError));
      }
      if (!disposed) timer = window.setTimeout(poll, 1600);
    };
    timer = window.setTimeout(poll, 1000);
    return () => {
      disposed = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [course.id, job?.id, job?.status, refresh]);

  const nodeTypes = useMemo(
    () => [...new Set(graph?.nodes.map((node) => node.node_type) || [])].sort(),
    [graph],
  );
  const relationTypes = useMemo(
    () => [...new Set(graph?.edges.map((edge) => edge.relation_type) || [])].sort(),
    [graph],
  );
  const visible = useMemo(() => {
    if (!graph) return { nodes: [] as KnowledgeGraphNode[], edges: [] as KnowledgeGraphEdge[], limited: false };
    const search = keyword.trim().toLocaleLowerCase();
    const matching = graph.nodes.filter(
      (node) =>
        (!nodeType || node.node_type === nodeType)
        && (!search || `${node.name} ${node.description || ""}`.toLocaleLowerCase().includes(search)),
    );
    const limited = matching.length > 250;
    const nodes = matching.slice(0, 250);
    const ids = new Set(nodes.map((node) => node.id));
    const edges = graph.edges
      .filter(
        (edge) =>
          ids.has(edge.source)
          && ids.has(edge.target)
          && (!relationType || edge.relation_type === relationType),
      )
      .slice(0, 500);
    return { nodes, edges, limited: limited || graph.edges.length > 500 };
  }, [graph, keyword, nodeType, relationType]);

  useEffect(() => {
    const element = chartElement.current;
    if (!element || !graph || !visible.nodes.length) return;
    let disposed = false;
    let removeResize: () => void = () => {};
    void import("./graph-echarts").then(({ echarts }) => {
      if (disposed || !chartElement.current) return;
      chartInstance.current?.dispose();
      const chart = echarts.init(chartElement.current, undefined, { renderer: "canvas" });
      chartInstance.current = chart;
      const categories = [...new Set(visible.nodes.map((node) => node.node_type))];
      chart.setOption({
        animationDurationUpdate: 420,
        series: [
          {
            type: "graph",
            layout: "force",
            roam: true,
            draggable: true,
            force: { repulsion: 170, edgeLength: [65, 145], gravity: 0.08 },
            label: { show: visible.nodes.length <= 70, position: "right", color: "#344138" },
            lineStyle: { color: "#9ba99d", curveness: 0.08, opacity: 0.72 },
            emphasis: { focus: "adjacency", lineStyle: { width: 2.5, opacity: 1 } },
            categories: categories.map((name) => ({ name })),
            data: visible.nodes.map((node) => ({
              id: String(node.id),
              name: node.name,
              category: categories.indexOf(node.node_type),
              symbolSize: 24 + node.importance * 25,
              value: node.importance,
              rawId: node.id,
              itemStyle: {
                color: ["#6f846f", "#a27e5d", "#687d82", "#85806a", "#7b716f"][
                  categories.indexOf(node.node_type) % 5
                ],
                borderColor: "#f8faf7",
                borderWidth: 2,
                shadowBlur: 8,
                shadowColor: "rgba(55, 70, 58, .16)",
              },
            })),
            links: visible.edges.map((edge) => ({
              id: `edge-${edge.id}`,
              source: String(edge.source),
              target: String(edge.target),
              label: relationNames[edge.relation_type] || edge.relation_type,
              rawId: edge.id,
              lineStyle: { width: 1 + edge.weight * 1.8 },
            })),
          },
        ],
      });
      chart.on("click", (params) => {
        const data = params.data as { rawId?: number } | null | undefined;
        const rawId = data?.rawId;
        if (!rawId) return;
        if (params.dataType === "edge") {
          const edge = graph.edges.find((item) => item.id === rawId);
          if (edge) setSelected({ kind: "edge", value: edge });
        } else {
          const node = graph.nodes.find((item) => item.id === rawId);
          if (node) setSelected({ kind: "node", value: node });
        }
      });
      const resize = () => chart.resize();
      window.addEventListener("resize", resize);
      removeResize = () => window.removeEventListener("resize", resize);
    });
    return () => {
      disposed = true;
      removeResize();
      chartInstance.current?.dispose();
      chartInstance.current = null;
    };
  }, [graph, visible]);

  const createJob = async () => {
    setBusy(true);
    setError("");
    try {
      const created = await api.createKnowledgeGraphJob(course.id);
      setJob(created);
      setVersions((current) => [created, ...current]);
      notify("知识图谱任务已创建，将在后台分批生成");
    } catch (createError) {
      const message = errorText(createError);
      setError(message);
      notify(message);
    } finally {
      setBusy(false);
    }
  };

  const selectedEdgeNames = useMemo(() => {
    if (!graph || selected?.kind !== "edge") return null;
    return {
      source: graph.nodes.find((node) => node.id === selected.value.source)?.name || "未知节点",
      target: graph.nodes.find((node) => node.id === selected.value.target)?.name || "未知节点",
    };
  }, [graph, selected]);

  const currentJob = job && (job.status === "pending" || job.status === "running")
    ? job
    : versions[0] || job;

  return createPortal(
    <div className="modal-backdrop graph-backdrop" onMouseDown={onClose}>
      <div className="knowledge-modal" onMouseDown={(event) => event.stopPropagation()}>
        <header className="knowledge-modal-head">
          <div>
            <span><Network size={17} />课程知识图谱</span>
            <h2>{course.name}</h2>
          </div>
          <div className="knowledge-head-actions">
            <button
              className="btn primary"
              disabled={busy || currentJob?.status === "pending" || currentJob?.status === "running"}
              onClick={createJob}
            >
              <RefreshCw className={busy ? "spin" : ""} size={15} />
              {graph ? "重新构建" : "生成图谱"}
            </button>
            <button className="icon-btn" onClick={onClose}><X size={19} /></button>
          </div>
        </header>

        <div className="knowledge-modal-body">
          {currentJob && (
            <section className={`graph-job-state ${currentJob.status}`}>
              <div className="job-state-main">
                {currentJob.status === "succeeded" ? <CheckCircle2 size={18} /> : <Clock3 size={18} />}
                <div>
                  <b>{statusNames[currentJob.status] || currentJob.status}</b>
                  <span>{currentJob.stage}</span>
                </div>
              </div>
              <div className="job-progress"><i style={{ width: `${currentJob.progress}%` }} /></div>
              <strong>{currentJob.progress}%</strong>
              {(currentJob.status === "pending" || currentJob.status === "running") && (
                <button
                  className="text-btn danger"
                  onClick={async () => {
                    await api.cancelKnowledgeGraphJob(course.id, currentJob.id);
                    setJob({ ...currentJob, status: "cancelled", stage: "已由用户取消" });
                    notify("图谱生成任务已取消");
                  }}
                >
                  取消
                </button>
              )}
              {currentJob.error_message && (
                <details className="graph-job-warning">
                  <summary>部分资料未能处理，已保留其他批次的有效结果</summary>
                  <p>{currentJob.error_message}</p>
                </details>
              )}
            </section>
          )}

          {error && (
            <div className="graph-error"><AlertTriangle size={16} /><span>{error}</span></div>
          )}

          {graph ? (
            <>
              <section className="graph-toolbar">
                <label><Search size={15} /><input value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="搜索知识点" /></label>
                <select value={nodeType} onChange={(event) => setNodeType(event.target.value)}>
                  <option value="">全部节点类型</option>
                  {nodeTypes.map((value) => <option key={value} value={value}>{value}</option>)}
                </select>
                <select value={relationType} onChange={(event) => setRelationType(event.target.value)}>
                  <option value="">全部关系</option>
                  {relationTypes.map((value) => <option key={value} value={value}>{relationNames[value] || value}</option>)}
                </select>
                <div className="graph-counts"><b>{graph.nodes.length}</b> 节点 · <b>{graph.edges.length}</b> 关系</div>
              </section>
              {visible.limited && <p className="graph-limit-note">图谱较大，当前画布最多展示 250 个节点和 500 条关系；可通过搜索与筛选缩小范围。</p>}
              <div className="graph-workspace">
                <div className="graph-canvas-wrap">
                  {visible.nodes.length ? (
                    <div className="graph-canvas" ref={chartElement} />
                  ) : (
                    <div className="graph-empty"><Search size={23} /><b>没有匹配的知识点</b><span>尝试清除搜索或筛选条件</span></div>
                  )}
                  <span className="graph-help">滚轮缩放 · 拖动画布 · 点击节点或连线查看证据</span>
                </div>
                <aside className="graph-inspector">
                  {!selected ? (
                    <div className="graph-inspector-empty"><BookOpen size={22} /><b>选择一个知识点或关系</b><span>这里会展示描述、置信度和资料证据。</span></div>
                  ) : selected.kind === "node" ? (
                    <>
                      <span className="inspector-type">{selected.value.node_type}</span>
                      <h3>{selected.value.name}</h3>
                      <p>{selected.value.description || "暂无补充描述"}</p>
                      <dl>
                        <div><dt>重要度</dt><dd>{Math.round(selected.value.importance * 100)}%</dd></div>
                        <div><dt>置信度</dt><dd>{Math.round(selected.value.confidence * 100)}%</dd></div>
                      </dl>
                      <Sources sources={selected.value.sources} />
                    </>
                  ) : (
                    <>
                      <span className="inspector-type">{relationNames[selected.value.relation_type] || selected.value.relation_type}</span>
                      <h3>{selectedEdgeNames?.source} → {selectedEdgeNames?.target}</h3>
                      <dl>
                        <div><dt>权重</dt><dd>{Math.round(selected.value.weight * 100)}%</dd></div>
                        <div><dt>置信度</dt><dd>{Math.round(selected.value.confidence * 100)}%</dd></div>
                      </dl>
                      <Sources sources={selected.value.sources} />
                    </>
                  )}
                </aside>
              </div>
            </>
          ) : loading ? (
            <div className="graph-loading"><RefreshCw className="spin" size={22} /><b>正在读取图谱状态</b></div>
          ) : (
            <div className="graph-empty main"><Network size={30} /><b>还没有可查看的知识图谱</b><span>生成过程只使用已解析的课程资料，并为每个知识点保留证据。</span></div>
          )}

          {versions.length > 0 && (
            <section className="graph-versions">
              <h3>生成记录</h3>
              <div>
                {versions.slice(0, 8).map((version) => (
                  <article key={version.id}>
                    <span className={`status ${version.status}`}>{statusNames[version.status] || version.status}</span>
                    <b>#{version.id}</b>
                    <span>{version.node_count} 节点 · {version.edge_count} 关系</span>
                    <time>{timeText(version.finished_at || version.created_at)}</time>
                    {version.is_active && <em>当前版本</em>}
                  </article>
                ))}
              </div>
            </section>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}
