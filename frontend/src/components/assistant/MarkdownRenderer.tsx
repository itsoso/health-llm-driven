'use client';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import MetricTableCard, { coerceMetricTable, type RevaUiMetricTableData } from './MetricTableCard';
import MetricEmptyStateCard, { type RevaUiMetricEmptyStateData } from './MetricEmptyStateCard';

const DISPLAY_FONT = '"Iowan Old Style", "Noto Serif SC", "Songti SC", serif';
// warm (Claude 设计语言) 标题用 CJK 衬线优先, 让中文标题也拿到编辑感。
const WARM_SERIF_FONT = '"Songti SC", "Noto Serif SC", "Iowan Old Style", Georgia, serif';
const REVA_UI_FENCE_RE = /\n?```reva-ui\s*\n([\s\S]*?)\n?```\n?/g;
// 未闭合的 reva-ui 开头 (流式中途还没等到收尾 fence): 用于 strip-partial。
const REVA_UI_OPENER_RE = /```reva-ui/;
const CHART_COLORS = ['#0f9f7a', '#2563eb', '#7c3aed', '#d97706', '#dc2626'];

type Variant = 'dark' | 'light' | 'warm';
type MarkdownSegment =
  | { kind: 'markdown'; text: string }
  | { kind: 'chart'; data: RevaUiLineChartData }
  | { kind: 'empty'; data: RevaUiMetricEmptyStateData }
  | { kind: 'table'; data: RevaUiMetricTableData };

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
  // warm — Claude / Anthropic 暖色阅读语言 (仅 ai-assistant 页消费; light 留给 shared 页, 不动)。
  warm: {
    p: 'mb-3 last:mb-0 whitespace-pre-wrap text-[#29261F]',
    ul: 'mb-3 ml-5 list-disc space-y-2 marker:text-[#C96442]',
    ol: 'mb-3 ml-5 list-decimal space-y-2 marker:font-semibold marker:text-[#C96442]',
    li: 'leading-7 text-[#29261F] pl-1',
    h1: 'mb-3 mt-5 text-[19px] font-semibold first:mt-0 text-[#29261F] tracking-[0.01em]',
    h2: 'mb-2 mt-5 text-[17px] font-semibold first:mt-0 text-[#29261F] border-l-2 border-[#C96442] pl-3',
    h3: 'mb-2 mt-4 text-[11px] font-semibold first:mt-0 text-[#948F80] uppercase tracking-[0.09em]',
    strong: 'font-semibold text-[#29261F]',
    em: 'italic text-[#6B665A]',
    inlineCode: 'rounded bg-[#F0EDE4] px-1.5 py-0.5 font-mono text-[12px] text-[#B4573A]',
    codeBlock: 'my-2 block overflow-x-auto rounded-xl bg-[#F0EDE4] px-4 py-3 font-mono text-xs text-[#29261F]',
    pre: 'my-3 overflow-x-auto rounded-xl bg-[#F0EDE4] p-4',
    blockquote: 'my-3 rounded-r-lg border-l-2 border-[#C96442]/50 bg-[#FBF3EE] py-2 pl-4 text-sm text-[#6B665A]',
    table: 'min-w-full overflow-hidden rounded-lg border border-[#E5E1D5] text-[13px] [font-variant-numeric:tabular-nums]',
    thead: 'bg-[#F0EDE4]',
    tr: 'border-b border-[#E5E1D5] last:border-0',
    th: 'px-3 py-2 text-left font-medium text-[#29261F]',
    td: 'px-3 py-2 text-[#29261F]',
    hr: 'my-5 border-[#E5E1D5]',
    a: 'text-[#C96442] underline-offset-2 underline transition-colors hover:text-[#B4573A]',
    aHover: 'hover:text-[#B4573A]',
  },
};

/** 标题字体: dark 用 Iowan 优先, warm 用 CJK 衬线优先, light 保持无衬线。 */
function headingFont(variant: Variant): { fontFamily: string } | undefined {
  if (variant === 'dark') return { fontFamily: DISPLAY_FONT };
  if (variant === 'warm') return { fontFamily: WARM_SERIF_FONT };
  return undefined;
}

export default function MarkdownRenderer({ content, variant = 'light' }: { content: string; variant?: Variant }) {
  const s = styles[variant];
  const segments = splitRevaUiSegments(content);
  // 快路径: 单一 markdown 段 (可能已被 strip 掉未闭合的 partial fence, 所以渲染
  // segment.text 而非原始 content, 否则 partial JSON 会漏进正文)。
  if (segments.length === 1 && segments[0].kind === 'markdown') {
    return <MarkdownRendererBase content={segments[0].text} variant={variant} stylesForVariant={s} />;
  }
  return (
    <>
      {segments.map((segment, index) => {
        if (segment.kind === 'chart') {
          return <RevaUiLineChartCard key={`chart-${index}`} data={segment.data} variant={variant} />;
        }
        if (segment.kind === 'empty') {
          return <MetricEmptyStateCard key={`empty-${index}`} data={segment.data} variant={variant} />;
        }
        if (segment.kind === 'table') {
          return <MetricTableCard key={`table-${index}`} data={segment.data} variant={variant} />;
        }
        if (!segment.text.trim()) return null;
        return (
          <MarkdownRendererBase key={`md-${index}`} content={segment.text} variant={variant} stylesForVariant={s} />
        );
      })}
    </>
  );
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
      components={{
        p: ({ children }) => <p className={s.p}>{children}</p>,
        ul: ({ children }) => <ul className={s.ul}>{children}</ul>,
        ol: ({ children }) => <ol className={s.ol}>{children}</ol>,
        li: ({ children }) => <li className={s.li}>{children}</li>,
        h1: ({ children }) => <h1 className={s.h1} style={headingFont(variant)}>{children}</h1>,
        h2: ({ children }) => <h2 className={s.h2} style={headingFont(variant)}>{children}</h2>,
        h3: ({ children }) => <h3 className={s.h3} style={variant === 'warm' ? undefined : headingFont(variant)}>{children}</h3>,
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
      }}
    >{content}</ReactMarkdown>
  );
}

export function splitRevaUiSegments(content: string): MarkdownSegment[] {
  const segments: MarkdownSegment[] = [];
  let cursor = 0;
  let touched = false; // 是否碰过任何 reva-ui 围栏 (闭合被解析/strip, 或未闭合被 strip)
  REVA_UI_FENCE_RE.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = REVA_UI_FENCE_RE.exec(content)) !== null) {
    touched = true;
    const start = match.index ?? 0;
    const before = content.slice(cursor, start);
    if (before) segments.push({ kind: 'markdown', text: before });
    // 解析失败/未知类型 → block 为 null → 整段围栏被 strip (不 push, cursor 照常前进)。
    const block = parseRevaUiBlock(match[1]);
    if (block) segments.push(block);
    cursor = start + match[0].length;
  }
  let rest = content.slice(cursor);
  // 流式中途: 剩余文本里若还有 ```reva-ui 开头, 必是未闭合块 (闭合的已被上面消费),
  // strip 掉避免半截 JSON 以代码块形式闪现; fence 收尾后下一帧正常解析。
  const openerIdx = rest.search(REVA_UI_OPENER_RE);
  if (openerIdx !== -1) {
    touched = true;
    rest = rest.slice(0, openerIdx);
  }
  if (rest) segments.push({ kind: 'markdown', text: rest });
  if (segments.length) return segments;
  // 碰过 reva-ui 但啥也没剩 (整条消息就是一个被 strip 的围栏) → 渲染空, 不回退裸内容
  // (否则原始 JSON 会泄漏)。没碰过 reva-ui → 保持原样走快路径。
  return touched ? [] : [{ kind: 'markdown', text: content }];
}

function parseRevaUiBlock(payload: string): Exclude<MarkdownSegment, { kind: 'markdown' }> | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(payload.trim());
  } catch {
    return null;
  }
  if (!parsed || typeof parsed !== 'object') return null;
  const block = parsed as { v?: unknown; type?: unknown; component?: unknown } & Record<string, unknown>;
  if (block.v !== 1) return null;
  // 判别键: metric_table 走 type, 图表/空态历史上走 component —— 两者都读, type 优先。
  const kind =
    typeof block.type === 'string' ? block.type : typeof block.component === 'string' ? block.component : '';
  if (kind === 'line_chart' || kind === 'metric_line_chart') {
    const chart = block as unknown as RevaUiLineChartData;
    if (!Array.isArray(chart.x) || !Array.isArray(chart.series)) return null;
    return { kind: 'chart', data: chart };
  }
  if (kind === 'metric_empty_state') {
    return { kind: 'empty', data: block as unknown as RevaUiMetricEmptyStateData };
  }
  if (kind === 'metric_table') {
    const table = coerceMetricTable(block as unknown as RevaUiMetricTableData);
    return table ? { kind: 'table', data: table } : null;
  }
  return null;
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
