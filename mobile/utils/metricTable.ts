/**
 * rank1 GenUI-first · metric_table 契约的纯解析 / 规范化 (无 React / RN 依赖)。
 *
 * 契约 (后端在 ```reva-ui fence 内下发, cap 点亮后才会出现):
 *   {"type":"metric_table","v":1,"title":str≤20字,
 *    "columns":[{"key","label"}×2-4],"rows":[{col-key:str}×1-12],"footnote"?:str}
 *
 * 容错原则:结构不满足最小可渲染要求(有效列 < 2 或有效行 = 0)→ 返回 null。
 * 调用方据此 strip-only —— 既不把原始 JSON 泄漏进正文,也不渲染半张坏卡。
 * 版本号(v)由调用方(revaUiBlocks)判定;本模块只做结构规范化。
 */

export interface MetricTableColumn {
  key: string;
  label: string;
}

export interface MetricTableData {
  title?: string;
  columns: MetricTableColumn[];
  /** 每行:column.key → 已规范化为字符串的单元格文本。缺失单元格补空串。 */
  rows: Record<string, string>[];
  footnote?: string;
}

const MIN_COLUMNS = 2;
const MAX_COLUMNS = 4;
const MAX_ROWS = 12;
/** 契约 title ≤20 字;放宽到 40 作为防御性硬顶,避免异常长文本撑破气泡。 */
const MAX_TITLE_LEN = 40;

function cellText(value: unknown): string {
  if (typeof value === 'string') return value.trim();
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  return '';
}

function normalizeColumns(raw: unknown): MetricTableColumn[] {
  if (!Array.isArray(raw)) return [];
  const cols: MetricTableColumn[] = [];
  const seen = new Set<string>();
  for (const item of raw) {
    if (!item || typeof item !== 'object' || Array.isArray(item)) continue;
    const key = cellText((item as Record<string, unknown>).key);
    const label = cellText((item as Record<string, unknown>).label);
    if (!key || !label || seen.has(key)) continue;
    seen.add(key);
    cols.push({ key, label });
    if (cols.length >= MAX_COLUMNS) break;
  }
  return cols;
}

function normalizeRows(raw: unknown, columns: MetricTableColumn[]): Record<string, string>[] {
  if (!Array.isArray(raw)) return [];
  const rows: Record<string, string>[] = [];
  for (const item of raw) {
    if (!item || typeof item !== 'object' || Array.isArray(item)) continue;
    const source = item as Record<string, unknown>;
    const row: Record<string, string> = {};
    let hasValue = false;
    for (const col of columns) {
      const text = cellText(source[col.key]);
      row[col.key] = text;
      if (text) hasValue = true;
    }
    if (!hasValue) continue; // 全空行丢弃
    rows.push(row);
    if (rows.length >= MAX_ROWS) break;
  }
  return rows;
}

/**
 * 把任意 reva-ui metric_table 块规范化为可渲染数据。
 * 结构不足以渲染 → null(调用方 strip-only)。
 */
export function parseMetricTable(block: unknown): MetricTableData | null {
  if (!block || typeof block !== 'object' || Array.isArray(block)) return null;
  const b = block as Record<string, unknown>;

  const columns = normalizeColumns(b.columns);
  if (columns.length < MIN_COLUMNS) return null;

  const rows = normalizeRows(b.rows, columns);
  if (rows.length === 0) return null;

  const data: MetricTableData = { columns, rows };

  const title = cellText(b.title);
  if (title) data.title = title.slice(0, MAX_TITLE_LEN);

  const footnote = cellText(b.footnote);
  if (footnote) data.footnote = footnote;

  return data;
}
