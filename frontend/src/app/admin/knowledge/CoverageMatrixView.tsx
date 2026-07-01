'use client';

// KB 覆盖矩阵「融合可见」视图(P1)。数据来自 /admin/knowledge/coverage_report 的 coverage_matrix
// (后端 P0 已算好:entity_type × origin 覆盖 + 权威校验 + 跨源重叠)。纯展示,不改数据。

export interface CoverageCell {
  entity_type: string;
  origin: string;
  doc_count: number;
  reviewed_count: number;
  avg_confidence: number | null;
}

export interface CrossSourceDup {
  signal: string;
  key: string;
  entity_type: string;
  origins: string[];
  doc_ids: string[];
}

export interface CoverageMatrix {
  matrix: CoverageCell[];
  origins: string[];
  entity_types: string[];
  totals: { doc_count: number; reviewed_count: number };
  cross_source_duplicates: CrossSourceDup[];
  validation: {
    count_invariant_ok: boolean;
    matrix_total: number;
    actual_total: number;
    independent_total: number;
    reviewed_le_doc_ok: boolean;
    cross_source_dup_count: number;
    alias_level_dups_out_of_scope: boolean;
  };
}

export function CoverageMatrixView({ data }: { data: CoverageMatrix }) {
  const { matrix, totals, cross_source_duplicates, validation } = data;
  const ok = validation.count_invariant_ok && validation.reviewed_le_doc_ok;

  const byType = new Map<string, CoverageCell[]>();
  for (const c of matrix) {
    const arr = byType.get(c.entity_type) ?? [];
    arr.push(c);
    byType.set(c.entity_type, arr);
  }
  const rows = Array.from(byType.entries())
    .map(([entity_type, cells]) => ({
      entity_type,
      total: cells.reduce((s, c) => s + c.doc_count, 0),
      reviewed: cells.reduce((s, c) => s + c.reviewed_count, 0),
      origins: [...cells].sort((a, b) => b.doc_count - a.doc_count),
    }))
    .sort((a, b) => b.total - a.total);

  return (
    <section className="mt-6 rounded-xl border border-slate-800 bg-[#111820]">
      <div className="border-b border-slate-800 p-4">
        <h2 className="text-lg font-semibold">来源覆盖矩阵 · 融合可见</h2>
        <p className="mt-1 text-xs text-slate-400">
          entity_type × origin 覆盖 + 权威校验 + 跨源重叠(= Phase B 对账目标)。纯读,不改数据。
        </p>
      </div>

      <div
        className={`mx-4 mt-4 rounded-lg border p-3 text-sm ${
          ok
            ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200'
            : 'border-red-500/40 bg-red-500/10 text-red-200'
        }`}
      >
        <span className="font-semibold">{ok ? '✓ 数据校验通过' : '✗ 数据校验异常'}</span>
        {' · '}
        count 不变量{' '}
        {validation.count_invariant_ok
          ? `一致 (${validation.independent_total})`
          : `失败 (${validation.matrix_total} ≠ ${validation.independent_total})`}
        {' · '}
        {totals.doc_count} 文档 · {totals.reviewed_count} reviewed
        {' · '}
        <span className="text-amber-200">{validation.cross_source_dup_count} 跨源重叠</span>
        {validation.alias_level_dups_out_of_scope && (
          <span className="text-slate-400"> · 别名级重复(Hp/幽门螺杆菌)留待 Phase B 实体对齐</span>
        )}
      </div>

      <div className="p-4">
        <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          按类型的来源覆盖
        </div>
        <div className="mt-2 space-y-2">
          {rows.map((r) => (
            <div
              key={r.entity_type}
              className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-800 bg-slate-950/40 p-2"
            >
              <span className="w-32 shrink-0 text-sm font-medium text-slate-200">{r.entity_type}</span>
              <span className="text-xs text-slate-400">
                {r.total} 篇 ({r.reviewed} reviewed)
              </span>
              <div className="flex flex-wrap gap-1">
                {r.origins.map((c) => (
                  <span
                    key={c.origin}
                    title={`${c.doc_count} 篇, ${c.reviewed_count} reviewed`}
                    className="rounded-full border border-slate-700 px-2 py-0.5 text-[11px] text-slate-300"
                  >
                    {c.origin} · {c.doc_count}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      {cross_source_duplicates.length > 0 && (
        <div className="border-t border-slate-800 p-4">
          <div className="text-xs font-semibold uppercase tracking-wide text-amber-300">
            跨源重叠 {cross_source_duplicates.length} 项 · Phase B 对账目标
          </div>
          <div className="mt-2 space-y-1.5">
            {cross_source_duplicates.map((d, i) => (
              <div
                key={`${d.signal}-${d.key}-${i}`}
                className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-2 text-xs"
              >
                <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-300">
                  {d.signal}
                </span>
                <span className="ml-2 font-medium text-slate-200">{d.entity_type}</span>
                <span className="ml-2 text-slate-400">{d.origins.join(' ↔ ')}</span>
                <div className="mt-1 text-[11px] text-slate-500">
                  {d.doc_ids.slice(0, 4).join(' · ')}
                  {d.doc_ids.length > 4 ? ` …+${d.doc_ids.length - 4}` : ''}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
