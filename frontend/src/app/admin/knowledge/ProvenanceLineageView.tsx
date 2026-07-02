'use client';

// KB Phase-A View 3:provenance 溯源 + 生命周期面板。消费 /admin/knowledge/document/{doc_id}。
// 纯读展示,无 merge 按钮。渲染 origin → source_repo@commit → license_scope → external_sources[]
// → provenance_lineage[](P4 合并折入的来源)→ candidate_duplicates 计数 → merged_into(若归档)。

export interface KBDocMeta {
  origin?: string;
  review_status?: string;
  license_scope?: string;
  source_repo?: string;
  source_commit?: string;
  source_path?: string;
  merged_into?: string;
  aliases?: string[];
  candidate_duplicates?: string[];
  external_sources?: Array<{ source?: string; title?: string; url?: string; kind?: string }>;
  provenance_lineage?: Array<{
    folded_doc_id?: string;
    origin?: string;
    license_scope?: string;
    folded_at?: string;
    folded_by?: string;
  }>;
  [k: string]: unknown;
}

export interface KBDocPayload {
  doc_id: string;
  doc_type: string;
  entity_type: string | null;
  title: string | null;
  summary: string | null;
  confidence: number | null;
  evidence_level: string | null;
  is_archived: boolean;
  sources?: unknown[];
  metadata: KBDocMeta;
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-2 text-xs">
      <span className="w-24 shrink-0 text-slate-500">{label}</span>
      <span className="text-slate-300">{children}</span>
    </div>
  );
}

export function ProvenanceLineageView({
  data,
  loading,
  docId,
  input,
  onInputChange,
  onLookup,
  notFound,
}: {
  data?: KBDocPayload;
  loading: boolean;
  docId: string;
  input: string;
  onInputChange: (v: string) => void;
  onLookup: () => void;
  notFound: boolean;
}) {
  const m = data?.metadata ?? {};
  return (
    <section className="mt-6 rounded-xl border border-slate-800 bg-[#111820]">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 p-4">
        <div>
          <h2 className="text-lg font-semibold">provenance 溯源 · View 3</h2>
          <p className="mt-1 text-xs text-slate-400">
            单文档来源链(只读)。合并后 canonical 的 <span className="text-teal-300">provenance_lineage</span>
            记录 P4 折入的来源;归档 loser 显示 merged_into。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <input
            value={input}
            onChange={(e) => onInputChange(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && onLookup()}
            placeholder="doc_id"
            className="w-72 rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none focus:border-teal-400"
          />
          <button
            type="button"
            onClick={onLookup}
            disabled={!input.trim() || loading}
            className="rounded-md bg-teal-500 px-3 py-2 text-sm font-medium text-slate-950 hover:bg-teal-400 disabled:opacity-60"
          >
            查
          </button>
        </div>
      </div>

      <div className="p-4">
        {!docId && <div className="p-2 text-sm text-slate-500">粘贴 doc_id 查来源链。</div>}
        {docId && loading && <div className="p-2 text-sm text-slate-400">加载中…</div>}
        {docId && !loading && notFound && <div className="p-2 text-sm text-amber-300">文档不存在。</div>}
        {data && (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium text-slate-200">{data.title || data.doc_id}</span>
              <span className="rounded bg-slate-700/40 px-1.5 py-0.5 text-[10px] text-slate-300">{data.doc_type}</span>
              {data.entity_type && <span className="text-[11px] text-slate-500">{data.entity_type}</span>}
              <span
                className={`rounded px-1.5 py-0.5 text-[10px] ${
                  m.review_status === 'reviewed'
                    ? 'bg-emerald-500/15 text-emerald-300'
                    : m.review_status === 'archived'
                      ? 'bg-slate-600/30 text-slate-400'
                      : 'bg-amber-500/15 text-amber-300'
                }`}
              >
                {m.review_status ?? '?'}
              </span>
              {data.is_archived && <span className="text-[10px] text-slate-500">archived</span>}
            </div>

            <div className="space-y-1.5 rounded-lg border border-slate-800 bg-slate-950/40 p-3">
              <Row label="origin"><span className="text-teal-300">{m.origin ?? '-'}</span></Row>
              <Row label="source">
                {m.source_repo ? `${m.source_repo}${m.source_commit ? `@${String(m.source_commit).slice(0, 10)}` : ''}` : '-'}
                {m.source_path ? <span className="ml-2 text-slate-500">{m.source_path}</span> : null}
              </Row>
              <Row label="license">
                <span className={m.license_scope === 'internal_transformed_claims' ? 'text-rose-300' : 'text-slate-300'}>
                  {m.license_scope ?? '-'}
                </span>
              </Row>
              {data.evidence_level && <Row label="evidence">{data.evidence_level}{typeof data.confidence === 'number' ? ` · conf ${data.confidence.toFixed(2)}` : ''}</Row>}
              {m.merged_into && (
                <Row label="merged_into"><span className="text-amber-300 font-mono">{m.merged_into}</span>(已折入,掉出 serving)</Row>
              )}
              {m.aliases && m.aliases.length > 0 && (
                <Row label="aliases">{m.aliases.slice(0, 12).join(' · ')}{m.aliases.length > 12 ? ` … +${m.aliases.length - 12}` : ''}</Row>
              )}
              {m.candidate_duplicates && m.candidate_duplicates.length > 0 && (
                <Row label="疑似重复">{m.candidate_duplicates.length} 条(未合并候选)</Row>
              )}
            </div>

            {m.external_sources && m.external_sources.length > 0 && (
              <div>
                <div className="mb-1 text-xs text-slate-500">外部来源 external_sources</div>
                <div className="space-y-1">
                  {m.external_sources.map((s, i) => (
                    <div key={i} className="rounded border border-slate-800 bg-slate-950/40 px-2 py-1 text-[11px] text-slate-300">
                      {s.title || s.source}{s.kind ? <span className="ml-2 text-slate-500">[{s.kind}]</span> : null}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {m.provenance_lineage && m.provenance_lineage.length > 0 && (
              <div>
                <div className="mb-1 text-xs text-teal-300">合并折入来源 provenance_lineage(P4)</div>
                <div className="space-y-1">
                  {m.provenance_lineage.map((p, i) => (
                    <div key={i} className="rounded border border-teal-500/30 bg-teal-500/5 px-2 py-1 text-[11px] text-slate-300">
                      <span className="font-mono text-teal-200">{p.folded_doc_id}</span>
                      <span className="ml-2 text-slate-500">{p.origin}</span>
                      {p.license_scope ? <span className="ml-2 text-slate-500">· {p.license_scope}</span> : null}
                      {p.folded_by ? <span className="ml-2 text-slate-500">· by {p.folded_by}</span> : null}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
