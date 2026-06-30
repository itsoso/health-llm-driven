'use client';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';

const DISPLAY_FONT = '"Iowan Old Style", "Noto Serif SC", "Songti SC", serif';
const REVA_UI_FENCE_RE = /\n?```reva-ui\s*\n([\s\S]*?)\n?```\n?/g;
const CHART_COLORS = ['#0f9f7a', '#2563eb', '#7c3aed', '#d97706', '#dc2626'];

type Variant = 'dark' | 'light';
type MarkdownSegment =
  | { kind: 'markdown'; text: string }
  | { kind: 'chart'; data: RevaUiLineChartData }
  | { kind: 'empty'; data: RevaUiMetricEmptyStateData };

interface RevaUiLineChartSeries {
  name?: string;
  role?: string;
  points?: Array<number | null>;
}

interface RevaUiLineChartAnnotation {
  x?: string;
  label?: string;
  kind?: string;
}

interface RevaUiLineChartData {
  v: 1;
  component: 'line_chart' | 'metric_line_chart';
  schema?: string;
  metric?: string;
  range?: string;
  title?: string;
  unit?: string;
  x?: string[];
  series?: RevaUiLineChartSeries[];
  annotations?: RevaUiLineChartAnnotation[];
  source?: string;
  data_note?: string;
}

interface RevaUiMetricEmptyStateData {
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

const styles: Record<Variant, {
  p: string; ul: string; ol: string; li: string;
  h1: string; h2: string; h3: string;
  strong: string; em: string;
  inlineCode: string; codeBlock: string; pre: string;
  blockquote: string; table: string; thead: string;
  tr: string; th: string; td: string; hr: string;
  a: string; aHover: string;
}> = {
  dark: {
    p: 'mb-3 last:mb-0 whitespace-pre-wrap text-zinc-100',
    ul: 'mb-3 ml-5 list-none space-y-2',
    ol: 'mb-3 ml-5 list-decimal space-y-2 marker:text-zinc-500',
    li: 'leading-7 text-zinc-100 relative pl-4 before:content-[""] before:absolute before:left-0 before:top-3 before:h-1 before:w-1 before:rounded-full before:bg-teal-300/70',
    h1: 'mb-3 mt-5 text-lg font-semibold first:mt-0 text-white tracking-wide',
    h2: 'mb-2 mt-5 text-base font-semibold first:mt-0 text-white border-l-2 border-teal-300/70 pl-3',
    h3: 'mb-2 mt-4 text-sm font-semibold first:mt-0 text-zinc-200 uppercase tracking-wider',
    strong: 'font-semibold text-white',
    em: 'italic text-zinc-300',
    inlineCode: 'rounded bg-white/[0.08] px-1.5 py-0.5 font-mono text-[12px] text-teal-300',
    codeBlock: 'my-2 block overflow-x-auto rounded-xl bg-black/40 px-4 py-3 font-mono text-xs text-zinc-200',
    pre: 'my-3 overflow-x-auto rounded-xl bg-black/40 p-4',
    blockquote: 'my-3 rounded-r-lg border-l-2 border-zinc-500/40 bg-white/[0.04] py-2 pl-4 text-sm text-zinc-300',
    table: 'min-w-full overflow-hidden rounded-lg border border-white/10 text-[13px]',
    thead: 'bg-white/[0.04]',
    tr: 'border-b border-white/[0.06] last:border-0',
    th: 'px-3 py-2 text-left font-medium text-zinc-200',
    td: 'px-3 py-2 text-zinc-100',
    hr: 'my-5 border-white/10',
    a: 'text-teal-300 underline-offset-2 underline transition-colors hover:text-teal-200',
    aHover: 'hover:text-teal-200',
  },
  light: {
    p: 'mb-2 last:mb-0',
    ul: 'mb-2 ml-4 list-disc space-y-1',
    ol: 'mb-2 ml-4 list-decimal space-y-1',
    li: 'leading-6',
    h1: 'mb-2 mt-3 text-lg font-bold text-gray-900 first:mt-0',
    h2: 'mb-2 mt-3 text-base font-bold text-gray-900 first:mt-0',
    h3: 'mb-1 mt-2 text-sm font-bold text-gray-800 first:mt-0',
    strong: 'font-semibold text-gray-900',
    em: 'italic text-gray-500',
    inlineCode: 'rounded bg-gray-100 px-1 py-0.5 font-mono text-xs text-emerald-700',
    codeBlock: 'my-2 block overflow-x-auto rounded-xl bg-gray-50 px-3 py-2 font-mono text-xs',
    pre: 'my-2 overflow-x-auto rounded-xl bg-gray-50 p-3',
    blockquote: 'my-2 border-l-3 border-emerald-300 bg-emerald-50/50 py-1 pl-3 italic text-gray-600',
    table: 'min-w-full text-xs border border-gray-200 rounded-lg',
    thead: 'bg-gray-50',
    tr: 'border-b border-gray-100',
    th: 'px-2 py-1.5 text-left font-semibold text-gray-700 border border-gray-200',
    td: 'px-2 py-1.5 border border-gray-200',
    hr: 'my-3 border-gray-200',
    a: 'text-emerald-600 underline hover:text-emerald-800',
    aHover: 'hover:text-emerald-800',
  },
};

// 工具步骤徽章 — running/done/failed 三态
function ToolStep({ name, status }: { name?: string; status?: string }) {
  const s = (status || 'running').toLowerCase();
  const label = s === 'done' ? '完成' : s === 'failed' ? '失败' : '执行中';
  const color = s === 'done'
    ? 'border-emerald-400/30 bg-emerald-400/8 text-emerald-200'
    : s === 'failed'
    ? 'border-rose-400/30 bg-rose-400/8 text-rose-200'
    : 'border-slate-400/30 bg-slate-700/40 text-slate-200';
  const dot = s === 'done' ? 'bg-emerald-400' : s === 'failed' ? 'bg-rose-400' : 'bg-slate-300 animate-pulse';
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-medium mr-1.5 mb-1.5 ${color}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
      <span className="font-mono">{name}</span>
      <span className="opacity-60">·</span>
      <span className="opacity-80">{label}</span>
    </span>
  );
}

export default function MarkdownRenderer({ content, variant = 'light' }: { content: string; variant?: Variant }) {
  const s = styles[variant];
  const segments = splitRevaUiSegments(content);
  if (segments.length > 1 || segments[0]?.kind !== 'markdown') {
    return (
      <>
        {segments.map((segment, index) => {
          if (segment.kind === 'chart') {
            return <RevaUiLineChartCard key={`chart-${index}`} data={segment.data} variant={variant} />;
          }
          if (segment.kind === 'empty') {
            return <RevaUiMetricEmptyStateCard key={`empty-${index}`} data={segment.data} variant={variant} />;
          }
          if (!segment.text.trim()) return null;
          return (
            <MarkdownRendererBase key={`md-${index}`} content={segment.text} variant={variant} stylesForVariant={s} />
          );
        })}
      </>
    );
  }
  return <MarkdownRendererBase content={content} variant={variant} stylesForVariant={s} />;
}

function MarkdownRendererBase({
  content,
  variant,
  stylesForVariant: s,
}: {
  content: string;
  variant: Variant;
  stylesForVariant: (typeof styles)[Variant];
}) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[rehypeRaw]}
      components={{
        p: ({ children }) => <p className={s.p}>{children}</p>,
        ul: ({ children }) => <ul className={s.ul}>{children}</ul>,
        ol: ({ children }) => <ol className={s.ol}>{children}</ol>,
        li: ({ children }) => <li className={s.li}>{children}</li>,
        h1: ({ children }) => <h1 className={s.h1} style={variant === 'dark' ? { fontFamily: DISPLAY_FONT } : undefined}>{children}</h1>,
        h2: ({ children }) => <h2 className={s.h2} style={variant === 'dark' ? { fontFamily: DISPLAY_FONT } : undefined}>{children}</h2>,
        h3: ({ children }) => <h3 className={s.h3} style={variant === 'dark' ? { fontFamily: DISPLAY_FONT } : undefined}>{children}</h3>,
        strong: ({ children }) => <strong className={s.strong}>{children}</strong>,
        em: ({ children }) => <em className={s.em}>{children}</em>,
        code: ({ ...props }: any) => {
          const inline = !props.className?.includes('language-');
          return inline
            ? <code className={s.inlineCode} {...props} />
            : <code className={s.codeBlock} {...props} />;
        },
        pre: ({ children }) => <pre className={s.pre}>{children}</pre>,
        blockquote: ({ children }) => <blockquote className={s.blockquote}>{children}</blockquote>,
        table: ({ children }) => <div className="my-3 overflow-x-auto"><table className={s.table}>{children}</table></div>,
        thead: ({ children }) => <thead className={s.thead}>{children}</thead>,
        ...(variant === 'dark' ? { tbody: ({ children }: any) => <tbody className="bg-transparent">{children}</tbody> } : {}),
        tr: ({ children }) => <tr className={s.tr}>{children}</tr>,
        th: ({ children }) => <th className={s.th}>{children}</th>,
        td: ({ children }) => <td className={s.td}>{children}</td>,
        hr: () => <hr className={s.hr} />,
        a: ({ children, href }) => <a href={href} target="_blank" rel="noopener noreferrer" className={s.a}>{children}</a>,
        // @ts-expect-error 自定义元素
        'tool-step': ({ name, status }: any) => <ToolStep name={name} status={status} />,
      }}
    >{content}</ReactMarkdown>
  );
}

function splitRevaUiSegments(content: string): MarkdownSegment[] {
  const segments: MarkdownSegment[] = [];
  let cursor = 0;
  REVA_UI_FENCE_RE.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = REVA_UI_FENCE_RE.exec(content)) !== null) {
    const start = match.index ?? 0;
    const before = content.slice(cursor, start);
    if (before) segments.push({ kind: 'markdown', text: before });
    const block = parseRevaUiBlock(match[1]);
    if (block) segments.push(block);
    cursor = start + match[0].length;
  }
  const rest = content.slice(cursor);
  if (rest) segments.push({ kind: 'markdown', text: rest });
  return segments.length ? segments : [{ kind: 'markdown', text: content }];
}

function parseRevaUiBlock(payload: string): Extract<MarkdownSegment, { kind: 'chart' | 'empty' }> | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(payload.trim());
  } catch {
    return null;
  }
  if (!parsed || typeof parsed !== 'object') return null;
  const block = parsed as RevaUiLineChartData | RevaUiMetricEmptyStateData;
  if (block.v !== 1) return null;
  if (block.component === 'line_chart' || block.component === 'metric_line_chart') {
    const chart = block as RevaUiLineChartData;
    if (!Array.isArray(chart.x) || !Array.isArray(chart.series)) return null;
    return { kind: 'chart', data: chart };
  }
  if (block.component === 'metric_empty_state') {
    return { kind: 'empty', data: block as RevaUiMetricEmptyStateData };
  }
  return null;
}

function RevaUiMetricEmptyStateCard({ data, variant }: { data: RevaUiMetricEmptyStateData; variant: Variant }) {
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

function RevaUiLineChartCard({ data, variant }: { data: RevaUiLineChartData; variant: Variant }) {
  const dark = variant === 'dark';
  const title = data.title || '指标趋势';
  const unit = data.unit || '';
  const x = Array.isArray(data.x) ? data.x : [];
  const series = (Array.isArray(data.series) ? data.series : [])
    .filter(item => Array.isArray(item.points) && item.points.some(point => typeof point === 'number'));
  const annotations = Array.isArray(data.annotations) ? data.annotations.filter(a => a?.label) : [];

  const values = series.flatMap(item =>
    (item.points || []).filter((point): point is number => typeof point === 'number' && Number.isFinite(point)),
  );
  if (!x.length || !series.length || !values.length) return null;

  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = Math.max(max - min, 1);
  const yMin = Math.max(0, min - span * 0.16);
  const yMax = max + span * 0.16;
  const width = 640;
  const height = 220;
  const left = 44;
  const right = 18;
  const top = 20;
  const bottom = 34;
  const plotW = width - left - right;
  const plotH = height - top - bottom;
  const xPos = (index: number) => left + (x.length === 1 ? plotW / 2 : (plotW * index) / (x.length - 1));
  const yPos = (value: number) => top + plotH - ((value - yMin) / (yMax - yMin)) * plotH;
  const gridValues = Array.from({ length: 4 }, (_, i) => yMin + ((yMax - yMin) * i) / 3);

  return (
    <div
      className={[
        'my-4 overflow-hidden rounded-2xl border p-4 shadow-sm',
        dark
          ? 'border-white/10 bg-white/[0.06] text-zinc-100'
          : 'border-emerald-100 bg-white text-slate-900',
      ].join(' ')}
      data-testid="reva-ui-chart-card"
    >
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <div className={dark ? 'text-sm font-semibold text-white' : 'text-sm font-semibold text-slate-950'}>
            {title}
          </div>
          {data.data_note ? (
            <div className={dark ? 'mt-1 text-xs text-zinc-400' : 'mt-1 text-xs text-slate-500'}>
              {data.data_note}
            </div>
          ) : null}
        </div>
        <div className={dark ? 'rounded-full bg-emerald-300/10 px-2.5 py-1 text-xs text-emerald-200' : 'rounded-full bg-emerald-50 px-2.5 py-1 text-xs text-emerald-700'}>
          {data.range || data.metric || '趋势'}
        </div>
      </div>

      <div className="overflow-x-auto">
        <svg viewBox={`0 0 ${width} ${height}`} className="h-[220px] min-w-[520px] w-full" role="img" aria-label={title}>
          <rect x="0" y="0" width={width} height={height} rx="16" fill={dark ? 'rgba(10,15,18,0.34)' : '#f8faf9'} />
          {gridValues.map((value, index) => {
            const y = yPos(value);
            return (
              <g key={`grid-${index}`}>
                <line x1={left} x2={width - right} y1={y} y2={y} stroke={dark ? 'rgba(255,255,255,0.08)' : '#e2e8f0'} />
                <text x={left - 8} y={y + 4} textAnchor="end" fontSize="11" fill={dark ? '#a1a1aa' : '#64748b'}>
                  {formatTick(value)}
                </text>
              </g>
            );
          })}
          <text x={left} y={14} fontSize="11" fill={dark ? '#a1a1aa' : '#64748b'}>{unit}</text>
          {series.map((item, seriesIndex) => (
            <g key={`${item.name || 'series'}-${seriesIndex}`}>
              {pathsForSeries(item.points || [], xPos, yPos).map((path, pathIndex) => (
                <path
                  key={pathIndex}
                  d={path}
                  fill="none"
                  stroke={CHART_COLORS[seriesIndex % CHART_COLORS.length]}
                  strokeWidth={item.role?.includes('avg') ? 2 : 2.6}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  opacity={item.role?.includes('avg') ? 0.76 : 1}
                />
              ))}
              {(item.points || []).map((point, pointIndex) => (
                typeof point === 'number' ? (
                  <circle
                    key={pointIndex}
                    cx={xPos(pointIndex)}
                    cy={yPos(point)}
                    r={2.6}
                    fill={CHART_COLORS[seriesIndex % CHART_COLORS.length]}
                    opacity={item.role?.includes('avg') ? 0.45 : 0.9}
                  />
                ) : null
              ))}
            </g>
          ))}
          {x.map((label, index) => {
            const show = x.length <= 8 || index === 0 || index === x.length - 1 || index % Math.ceil(x.length / 6) === 0;
            if (!show) return null;
            return (
              <text key={label + index} x={xPos(index)} y={height - 12} textAnchor="middle" fontSize="11" fill={dark ? '#a1a1aa' : '#64748b'}>
                {label}
              </text>
            );
          })}
        </svg>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        {series.map((item, index) => (
          <span key={`${item.name || 'series'}-legend-${index}`} className={dark ? 'inline-flex items-center gap-1.5 text-xs text-zinc-300' : 'inline-flex items-center gap-1.5 text-xs text-slate-600'}>
            <span className="h-2 w-2 rounded-full" style={{ backgroundColor: CHART_COLORS[index % CHART_COLORS.length] }} />
            {item.name || `序列 ${index + 1}`}
          </span>
        ))}
      </div>
      {annotations.length ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {annotations.slice(0, 3).map((annotation, index) => (
            <span
              key={`${annotation.label}-${index}`}
              className={dark ? 'rounded-full border border-white/10 bg-white/[0.05] px-2.5 py-1 text-xs text-zinc-300' : 'rounded-full border border-emerald-100 bg-emerald-50 px-2.5 py-1 text-xs text-emerald-800'}
            >
              {annotation.label}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function pathsForSeries(
  points: Array<number | null>,
  xPos: (index: number) => number,
  yPos: (value: number) => number,
): string[] {
  const paths: string[] = [];
  let current = '';
  points.forEach((point, index) => {
    if (typeof point !== 'number' || !Number.isFinite(point)) {
      if (current) {
        paths.push(current);
        current = '';
      }
      return;
    }
    const command = current ? 'L' : 'M';
    current += `${command}${xPos(index).toFixed(1)},${yPos(point).toFixed(1)} `;
  });
  if (current) paths.push(current);
  return paths;
}

function formatTick(value: number): string {
  if (Math.abs(value) >= 1000) return `${Math.round(value)}`;
  if (Math.abs(value) >= 10) return `${Math.round(value)}`;
  return value.toFixed(1);
}
