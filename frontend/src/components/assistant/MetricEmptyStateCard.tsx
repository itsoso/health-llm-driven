'use client';

/**
 * MetricEmptyStateCard — reva-ui `metric_empty_state` GenUI 卡片 (web 侧).
 *
 * 数据不足以画趋势图时, 后端产出这个空态块 (由 MarkdownRenderer 抽取):
 *   {"v":1,"component":"metric_empty_state","title":..,"message":..,
 *    "suggestions":[..],"boundary":..}
 * 从 MarkdownRenderer 拆出来独立成文件, 与 MetricTableCard 同一模式。
 */

export type MetricEmptyStateVariant = 'dark' | 'light' | 'warm';

export interface RevaUiMetricEmptyStateData {
  v: 1;
  component: 'metric_empty_state';
  schema?: string;
  metric?: string;
  range?: string;
  title?: string;
  message?: string;
  suggestions?: string[];
  boundary?: string;
}

export default function MetricEmptyStateCard({
  data,
  variant,
}: {
  data: RevaUiMetricEmptyStateData;
  variant: MetricEmptyStateVariant;
}) {
  const dark = variant === 'dark';
  const suggestions = Array.isArray(data.suggestions) ? data.suggestions.filter(Boolean).slice(0, 4) : [];
  return (
    <div
      className={[
        'my-4 overflow-hidden rounded-2xl border p-4 shadow-sm',
        dark
          ? 'border-white/10 bg-white/[0.06] text-zinc-100'
          : 'border-amber-100 bg-white text-slate-900',
      ].join(' ')}
      data-testid="reva-ui-empty-state-card"
    >
      <div className="mb-2 flex items-start justify-between gap-3">
        <div>
          <div className={dark ? 'text-sm font-semibold text-white' : 'text-sm font-semibold text-slate-950'}>
            {data.title || '数据不足'}
          </div>
          <div className={dark ? 'mt-1 text-sm leading-6 text-zinc-300' : 'mt-1 text-sm leading-6 text-slate-600'}>
            {data.message || '暂无足够数据生成趋势图。'}
          </div>
        </div>
        <div className={dark ? 'rounded-full bg-amber-300/10 px-2.5 py-1 text-xs text-amber-200' : 'rounded-full bg-amber-50 px-2.5 py-1 text-xs text-amber-700'}>
          待补齐
        </div>
      </div>
      {suggestions.length ? (
        <div className="mt-3 grid gap-2">
          {suggestions.map((item, index) => (
            <div
              key={`${item}-${index}`}
              className={dark ? 'rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-sm text-zinc-300' : 'rounded-xl border border-slate-100 bg-slate-50 px-3 py-2 text-sm text-slate-700'}
            >
              {item}
            </div>
          ))}
        </div>
      ) : null}
      {data.boundary ? (
        <div className={dark ? 'mt-3 text-xs leading-5 text-zinc-500' : 'mt-3 text-xs leading-5 text-slate-500'}>
          {data.boundary}
        </div>
      ) : null}
    </div>
  );
}
