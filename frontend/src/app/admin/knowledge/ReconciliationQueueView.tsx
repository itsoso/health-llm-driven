'use client';

// KB Phase-B P3 只读对账队列视图。消费 /admin/knowledge/reconciliation/{scan,candidates}。
// 纯读 + 扫描触发(detector 只写候选旁路表,零 serving mutation)。relation_tag=NULL 的候选
// 是「待 P5 judge/人判」;只有 content_hash 完全相同的才是 'duplicate'。canonical_hint = D1
// (down-dedao reviewed 恒 canonical);None = 无 reviewed 锚,只能走人。

export interface ReconCandidate {
  id: number;
  kind: string;
  left_doc_id: string;
  right_doc_id: string;
  entity_type: string | null;
  entity_id: string | null;
  relation_tag: string | null;
  score: number | null;
  signals: {
    detectors?: string[];
    canonical_reason?: string;
    edge_neighborhood?: { overlap_score?: number; shared_count?: number };
    alias_overlap?: { shared_tokens?: string[] };
    [k: string]: unknown;
  };
  canonical_hint: string | null;
  status: string;
  detected_at: string | null;
  reviewed_by: string | null;
}

export interface ReconQueueData {
  total: number;
  limit: number;
  offset: number;
  candidates: ReconCandidate[];
}

export interface ReconScanResult {
  created: number;
  skipped_existing: number;
  truncated: boolean;
  oversized_buckets: number;
  oversized_neighbor_tokens: number;
  malformed_alias_docs: number;
  scanned_docs: number;
  total_open: number;
}

const DETECTOR_COLORS: Record<string, string> = {
  content_hash: 'bg-rose-500/15 text-rose-300 border-rose-500/30',
  entity_id: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  normalized_title: 'bg-sky-500/15 text-sky-300 border-sky-500/30',
  edge_neighborhood: 'bg-violet-500/15 text-violet-300 border-violet-500/30',
  alias_overlap: 'bg-teal-500/15 text-teal-300 border-teal-500/30',
};

function DetectorChip({ name }: { name: string }) {
  const cls = DETECTOR_COLORS[name] || 'bg-slate-600/20 text-slate-300 border-slate-600/40';
  return <span className={`rounded border px-1.5 py-0.5 text-[10px] ${cls}`}>{name}</span>;
}

const STATUS_OPTIONS = ['open', 'approved', 'rejected', 'deferred'];
const KIND_OPTIONS = ['', 'entity_align', 'claim_overlap'];

export function ReconciliationQueueView({
  data,
  loading,
  onScan,
  scanning,
  scanResult,
  status,
  kind,
  onStatusChange,
  onKindChange,
}: {
  data?: ReconQueueData;
  loading: boolean;
  onScan: () => void;
  scanning: boolean;
  scanResult?: ReconScanResult;
  status: string;
  kind: string;
  onStatusChange: (s: string) => void;
  onKindChange: (k: string) => void;
}) {
  return (
    <section className="mt-6 rounded-xl border border-slate-800 bg-[#111820]">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 p-4">
        <div>
          <h2 className="text-lg font-semibold">跨源对账队列 · P3</h2>
          <p className="mt-1 text-xs text-slate-400">
            检测器只 SURFACE 跨源重复候选(旁路表,零 serving mutation、零自动合并)。
            <span className="text-rose-300">duplicate</span> 仅指 content_hash 字节相同;其余 relation_tag 空=待判。
          </p>
        </div>
        <button
          type="button"
          onClick={onScan}
          disabled={scanning}
          className="rounded-md bg-teal-500 px-3 py-2 text-sm font-medium text-slate-950 hover:bg-teal-400 disabled:opacity-60"
        >
          {scanning ? '扫描中…' : '运行检测器扫描'}
        </button>
      </div>

      {scanResult && (
        <div className="border-b border-slate-800 px-4 py-3 text-xs text-slate-300">
          <div className="flex flex-wrap gap-x-4 gap-y-1">
            <span>新增 <b className="text-teal-300">{scanResult.created}</b></span>
            <span>跳过(已存在) {scanResult.skipped_existing}</span>
            <span>扫描文档 {scanResult.scanned_docs}</span>
            <span>当前 open {scanResult.total_open}</span>
            {scanResult.truncated && <span className="text-amber-300">⚠️ 写入截断(超候选上限)</span>}
            {scanResult.oversized_buckets > 0 && (
              <span className="text-amber-300">⚠️ 超大桶跳过 {scanResult.oversized_buckets}</span>
            )}
            {scanResult.oversized_neighbor_tokens > 0 && (
              <span className="text-amber-300">⚠️ 超级 hub 跳过 {scanResult.oversized_neighbor_tokens}</span>
            )}
            {scanResult.malformed_alias_docs > 0 && (
              <span className="text-amber-300">⚠️ 脏 aliases {scanResult.malformed_alias_docs}</span>
            )}
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2 border-b border-slate-800 px-4 py-3 text-xs">
        <span className="text-slate-400">状态</span>
        {STATUS_OPTIONS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => onStatusChange(s)}
            className={`rounded-md border px-2 py-1 ${
              status === s ? 'border-teal-400 text-teal-300' : 'border-slate-700 text-slate-400'
            }`}
          >
            {s}
          </button>
        ))}
        <span className="ml-3 text-slate-400">类型</span>
        {KIND_OPTIONS.map((k) => (
          <button
            key={k || 'all'}
            type="button"
            onClick={() => onKindChange(k)}
            className={`rounded-md border px-2 py-1 ${
              kind === k ? 'border-teal-400 text-teal-300' : 'border-slate-700 text-slate-400'
            }`}
          >
            {k || '全部'}
          </button>
        ))}
      </div>

      <div className="p-4">
        {loading && <div className="p-4 text-sm text-slate-400">加载中…</div>}
        {!loading && data && data.candidates.length === 0 && (
          <div className="p-4 text-sm text-slate-500">
            无 {status} 候选。先「运行检测器扫描」生成候选。
          </div>
        )}
        {!loading && data && data.candidates.length > 0 && (
          <>
            <div className="mb-2 text-xs text-slate-500">共 {data.total} 条(显示前 {data.candidates.length})</div>
            <div className="space-y-2">
              {data.candidates.map((c) => (
                <div key={c.id} className="rounded-lg border border-slate-800 bg-slate-950/40 p-3 text-sm">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded bg-slate-700/40 px-1.5 py-0.5 text-[10px] text-slate-300">{c.kind}</span>
                    {c.relation_tag ? (
                      <span className="rounded bg-rose-500/15 px-1.5 py-0.5 text-[10px] text-rose-300 border border-rose-500/30">
                        {c.relation_tag}
                      </span>
                    ) : (
                      <span className="rounded bg-slate-600/20 px-1.5 py-0.5 text-[10px] text-slate-400 border border-slate-600/40">
                        待判
                      </span>
                    )}
                    {typeof c.score === 'number' && (
                      <span className="text-[11px] text-slate-400">score {c.score.toFixed(2)}</span>
                    )}
                    {c.entity_type && <span className="text-[11px] text-slate-500">{c.entity_type}</span>}
                    <span className="ml-auto text-[10px] text-slate-500">#{c.id} · {c.status}</span>
                  </div>
                  <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 font-mono text-[11px] text-slate-300">
                    <span className={c.canonical_hint === c.left_doc_id ? 'text-emerald-300' : ''}>{c.left_doc_id}</span>
                    <span className="text-slate-600">↔</span>
                    <span className={c.canonical_hint === c.right_doc_id ? 'text-emerald-300' : ''}>{c.right_doc_id}</span>
                  </div>
                  <div className="mt-2 flex flex-wrap items-center gap-1.5">
                    {(c.signals.detectors || []).map((d) => (
                      <DetectorChip key={d} name={d} />
                    ))}
                    {c.signals.alias_overlap?.shared_tokens && c.signals.alias_overlap.shared_tokens.length > 0 && (
                      <span className="text-[10px] text-slate-500">
                        共享词: {c.signals.alias_overlap.shared_tokens.slice(0, 6).join(' · ')}
                      </span>
                    )}
                    {typeof c.signals.edge_neighborhood?.shared_count === 'number' && (
                      <span className="text-[10px] text-slate-500">
                        共享邻居 {c.signals.edge_neighborhood.shared_count}
                      </span>
                    )}
                  </div>
                  <div className="mt-1.5 text-[10px] text-slate-500">
                    canonical:{' '}
                    {c.canonical_hint ? (
                      <span className="text-emerald-300">{c.canonical_hint}</span>
                    ) : (
                      <span className="text-amber-300">无 reviewed 锚 → 走人</span>
                    )}
                    {c.signals.canonical_reason ? ` · ${c.signals.canonical_reason}` : ''}
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </section>
  );
}
