'use client';

/**
 * MetricTableCard — reva-ui `metric_table` GenUI 卡片 (rank1 GenUI-first, web 侧).
 *
 * 后端在 assistant 正文里塞一个 ```reva-ui 围栏块 (MarkdownRenderer 负责抽取):
 *   {"type":"metric_table","v":1,"title":str,"columns":[{key,label}×2-4],
 *    "rows":[{col-key:str}×1-12],"footnote":optional}
 *
 * 静态表 (无交互), 窄屏横向滚动. 颜色对齐 ai-assistant 页 `.ai-assistant-theme`
 * 的 Claude 暖色 token (paper/card/hairline/ink), 与 MarkdownRenderer 的 warm
 * markdown 样式同一批 hex —— 直接写死 hex 而非 var(--rd-*), 这样 shared 页
 * (light, 无该 scope) 也能正常上色。
 */

export type MetricTableVariant = 'dark' | 'light' | 'warm';

export interface RevaUiMetricTableColumn {
  key?: string;
  label?: string;
}

export interface RevaUiMetricTableData {
  v: 1;
  /** 契约主字段: type==='metric_table' (chart/empty 用 component, 这里两者都收). */
  type?: string;
  component?: string;
  schema?: string;
  title?: string;
  columns?: RevaUiMetricTableColumn[];
  rows?: Array<Record<string, unknown>>;
  footnote?: string;
}

// warm 标题衬线, 与 MarkdownRenderer.WARM_SERIF_FONT 保持一致 (中文衬线优先)。
const WARM_SERIF_FONT = '"Songti SC", "Noto Serif SC", "Iowan Old Style", Georgia, serif';

interface Palette {
  border: string;
  bg: string;
  ink: string;
  muted: string;
  faint: string;
  headBg: string;
  rowBorder: string;
}

const PALETTES: Record<MetricTableVariant, Palette> = {
  // Claude 暖色 — 对齐 --rd-hair / --rd-card / --rd-ink / --rd-ink-2 / --rd-ink-3 / --rd-rail。
  warm: { border: '#E5E1D5', bg: '#FCFBF7', ink: '#29261F', muted: '#6B665A', faint: '#948F80', headBg: '#F0EDE4', rowBorder: '#EFEADD' },
  light: { border: '#E2E8F0', bg: '#FFFFFF', ink: '#0F172A', muted: '#475569', faint: '#64748B', headBg: '#F8FAFC', rowBorder: '#F1F5F9' },
  dark: { border: 'rgba(255,255,255,0.10)', bg: 'rgba(255,255,255,0.06)', ink: '#FAFAFA', muted: '#D4D4D8', faint: '#A1A1AA', headBg: 'rgba(255,255,255,0.05)', rowBorder: 'rgba(255,255,255,0.06)' },
};

/**
 * 校验并归一化 metric_table block。结构不满足最低要求 (至少 1 列 + 1 行, 列有
 * 字符串 key) → 返回 null, 调用方 (MarkdownRenderer) 会静默 strip 掉整个围栏。
 */
export function coerceMetricTable(block: RevaUiMetricTableData): RevaUiMetricTableData | null {
  const isTable = block.type === 'metric_table' || block.component === 'metric_table';
  if (!isTable) return null;
  const columns = (Array.isArray(block.columns) ? block.columns : []).filter(
    (c): c is RevaUiMetricTableColumn =>
      !!c && typeof c === 'object' && typeof c.key === 'string' && c.key.length > 0,
  );
  const rows = (Array.isArray(block.rows) ? block.rows : []).filter(
    (r): r is Record<string, unknown> => !!r && typeof r === 'object' && !Array.isArray(r),
  );
  if (columns.length < 1 || rows.length < 1) return null;
  return { ...block, columns, rows };
}

/** 单元格取值: 只渲染标量 (string/number/boolean), 契约里都是 str; 其它跳过。 */
function cellText(row: Record<string, unknown>, key?: string): string {
  if (!key) return '';
  const value = row[key];
  if (value === null || value === undefined) return '';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return '';
}

export default function MetricTableCard({
  data,
  variant = 'warm',
}: {
  data: RevaUiMetricTableData;
  variant?: MetricTableVariant;
}) {
  const p = PALETTES[variant] ?? PALETTES.warm;
  const columns = (Array.isArray(data.columns) ? data.columns : []).filter(c => typeof c?.key === 'string');
  const rows = Array.isArray(data.rows) ? data.rows : [];
  if (!columns.length || !rows.length) return null;
  const title = (data.title ?? '').trim();

  return (
    <div
      className="my-4 overflow-hidden rounded-2xl border shadow-sm"
      style={{ borderColor: p.border, backgroundColor: p.bg, color: p.ink }}
      data-testid="reva-ui-metric-table-card"
    >
      {title ? (
        <div className="px-4 pb-2 pt-4">
          <div
            className="text-[15px] font-semibold leading-6"
            style={{ color: p.ink, fontFamily: variant === 'warm' ? WARM_SERIF_FONT : undefined }}
          >
            {title}
          </div>
        </div>
      ) : null}

      <div className="overflow-x-auto px-4 pb-1">
        <table className="min-w-full border-collapse text-[13px] tabular-nums">
          <thead>
            <tr>
              {columns.map((col, ci) => (
                <th
                  key={col.key ?? ci}
                  scope="col"
                  className="whitespace-nowrap px-3 py-2 text-left text-[12px] font-medium"
                  style={{ color: p.muted, backgroundColor: p.headBg, borderBottom: `1px solid ${p.border}` }}
                >
                  {col.label ?? col.key}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, ri) => (
              <tr
                key={ri}
                style={{ borderBottom: ri === rows.length - 1 ? 'none' : `1px solid ${p.rowBorder}` }}
              >
                {columns.map((col, ci) => (
                  <td
                    key={col.key ?? ci}
                    className={`whitespace-pre-wrap px-3 py-2 align-top ${ci === 0 ? 'font-medium' : ''}`}
                    style={{ color: p.ink }}
                  >
                    {cellText(row, col.key)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {data.footnote ? (
        <div className="px-4 pb-4 pt-2 text-[11px] leading-5" style={{ color: p.faint }}>
          {data.footnote}
        </div>
      ) : null}
    </div>
  );
}
