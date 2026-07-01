'use client';

import { useMemo } from 'react';

// KB 邻域图 SVG 视图(P2,纯 SVG 自绘同心圆布局,零 npm 依赖)。数据来自 /admin/knowledge/graph。
// 种子居中,hop-1 内环、hop-2 外环;节点按 entity_type 上色,draft 用虚线黄边。

export interface GraphNode {
  doc_id: string;
  doc_type: string;
  entity_type: string | null;
  title: string | null;
  review_status: string | null;
  origin: string | null;
  confidence: number | null;
  hop: number;
}
export interface GraphEdge {
  src: string;
  dst: string;
  relation: string;
  confidence: number | null;
  origin: string | null;
}
export interface GraphData {
  seed: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  truncated: boolean;
  node_count: number;
  hops: number;
  not_found?: boolean;
}

const TYPE_COLORS: Record<string, string> = {
  condition: '#f87171',
  gene: '#a78bfa',
  drug: '#60a5fa',
  supplement: '#34d399',
  food: '#fbbf24',
  nutrient: '#4ade80',
  intervention: '#22d3ee',
  biomarker: '#f472b6',
  snp: '#c084fc',
  behavior: '#94a3b8',
  concept: '#cbd5e1',
  article: '#64748b',
  course: '#818cf8',
  specialty: '#fb923c',
  aging_hallmark: '#e879f9',
};
function colorFor(t: string | null): string {
  return (t && TYPE_COLORS[t]) || '#94a3b8';
}

const W = 720;
const H = 520;

export function KnowledgeGraphView({
  data,
  onSelect,
}: {
  data: GraphData;
  onSelect?: (n: GraphNode) => void;
}) {
  const pos = useMemo(() => {
    const cx = W / 2;
    const cy = H / 2;
    const byHop: Record<number, GraphNode[]> = {};
    data.nodes.forEach((n) => {
      (byHop[n.hop] ??= []).push(n);
    });
    const radii = [0, Math.min(W, H) * 0.3, Math.min(W, H) * 0.46];
    const p: Record<string, { x: number; y: number }> = {};
    Object.entries(byHop).forEach(([h, ns]) => {
      const hop = Number(h);
      const r = radii[hop] ?? radii[2];
      ns.forEach((n, i) => {
        const a = hop === 0 ? -Math.PI / 2 : (i / ns.length) * 2 * Math.PI - Math.PI / 2;
        p[n.doc_id] = { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) };
      });
    });
    return p;
  }, [data]);

  if (data.not_found) {
    return <div className="p-4 text-sm text-slate-400">种子文档不存在。</div>;
  }
  if (!data.nodes.length) {
    return <div className="p-4 text-sm text-slate-400">无邻域数据。</div>;
  }

  const types = Array.from(
    new Set(data.nodes.map((n) => n.entity_type).filter(Boolean)),
  ) as string[];

  return (
    <div>
      {data.truncated && (
        <div className="mb-2 text-xs text-amber-300">⚠️ 节点超上限已截断,仅显示部分邻域。</div>
      )}
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full rounded-lg border border-slate-800 bg-slate-950/40"
      >
        {data.edges.map((e, i) => {
          const a = pos[e.src];
          const b = pos[e.dst];
          if (!a || !b) return null;
          return (
            <line key={`${e.src}-${e.dst}-${i}`} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="#334155" strokeWidth={1} />
          );
        })}
        {data.nodes.map((n) => {
          const p = pos[n.doc_id];
          if (!p) return null;
          const isSeed = n.hop === 0;
          const draft = n.review_status !== 'reviewed';
          return (
            <g
              key={n.doc_id}
              transform={`translate(${p.x},${p.y})`}
              className="cursor-pointer"
              onClick={() => onSelect?.(n)}
            >
              <circle
                r={isSeed ? 11 : 7}
                fill={colorFor(n.entity_type)}
                stroke={draft ? '#fbbf24' : '#0f172a'}
                strokeWidth={draft ? 2 : 1}
                strokeDasharray={draft ? '3 2' : undefined}
              />
              <text x={0} y={isSeed ? -15 : -11} textAnchor="middle" className="fill-slate-300 text-[9px]">
                {(n.title || n.doc_id).slice(0, 14)}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="mt-2 flex flex-wrap gap-2 text-[10px] text-slate-400">
        {types.map((t) => (
          <span key={t} className="inline-flex items-center gap-1">
            <span className="inline-block h-2 w-2 rounded-full" style={{ background: colorFor(t) }} />
            {t}
          </span>
        ))}
        <span className="inline-flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-full border border-dashed border-amber-400" />
          draft(虚线黄边)
        </span>
      </div>
    </div>
  );
}
