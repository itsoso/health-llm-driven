const isTableRow = (line: string) => /^\s*\|.*\|\s*$/.test(line);
const isDividerRow = (line: string) => /^\s*\|[\s\-:|]+\|\s*$/.test(line);

// 一整行同时含 header + 分隔行, 中间用 `||` 黏连: `| 指标 | 数值 || --- | --- |`。
// LLM (尤其弱模型) 常把表头和 |---| 分隔吐在一行, react-native-markdown-display
// 解析不了 → 渲染成生 markdown 原文。切成 header + divider 两行。
const GLUED_TABLE_SPLIT = /^(\s*\|[^\n]*?\|)\s*\|(\s*[:\-\s|]+\|\s*)$/;

/**
 * 规范化 LLM 吐出的「脏 markdown」, 让 react-native-markdown-display 能解析:
 *  - `##标题` / `###1.` → `## 标题` / `### 1.` (ATX 标题 # 后补空格; 无空格时解析器把整行当普通文本)
 *  - `1.text` → `1. text` (有序列表标记后补空格)
 *  - `| 指标 | 数值 || --- | --- |` 黏成一行的表头+分隔 → 拆成两行
 *
 * 只做「补空格 / 拆黏连行」这类保守修复, 不改文字内容, 不吃合法 markdown
 * (已有空格的标题 / 正常列表不受影响)。目标: 即使 LLM 吐脏 markdown 也能正常渲染,
 * 不依赖 ChatBubble「等一会 setState 才刷正」的时序。
 */
export function normalizeLooseMarkdown(md: string): string {
  const lines = md.split('\n');
  const out: string[] = [];

  for (const raw of lines) {
    let line = raw;

    // 1) 先拆开黏成一行的「表头 || 分隔行」。拆完两行分别继续走标题/列表规范化没意义
    //    (它们是表格行), 直接推入让后续 preprocessMarkdownTables 处理。
    const glued = line.match(GLUED_TABLE_SPLIT);
    if (glued) {
      out.push(glued[1].trimEnd());
      out.push(`|${glued[2].trimEnd()}`);
      continue;
    }

    // 2) ATX 标题: 行首 1-6 个 # 后若紧跟非空格非 # 字符, 补一个空格。
    //    `##今日状态总览` → `## 今日状态总览`; `###1. 方案` → `### 1. 方案`。
    //    已有空格 (`## 标题`) 或纯 `###` 分隔不动。
    line = line.replace(/^(\s*)(#{1,6})(?=[^\s#])/, '$1$2 ');

    // 3) 有序列表标记后补空格: `1.今天` → `1. 今天` (行首, 允许前导空格/缩进)。
    //    markdown-display 要求 `数字.` 后有空格才认列表; 无空格时整行当普通文本。
    line = line.replace(/^(\s*)(\d{1,9})\.(?=\S)/, '$1$2. ');

    out.push(line);
  }

  return out.join('\n');
}

function splitTableRow(line: string): string[] {
  return line
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map(cell => cell.trim())
    .filter(Boolean);
}

function pushListRows(out: string[], rows: string[][]): void {
  for (const row of rows) {
    const first = row[0] ? `**${row[0]}**` : '';
    const rest = row.slice(1).filter(Boolean).join(' · ');
    const text = `${first}${first && rest ? ' · ' : ''}${rest}`.trim();
    if (text) out.push(`- ${text}`);
  }
}

export function containsMarkdownTable(md: string): boolean {
  const lines = md.split('\n');
  for (let i = 0; i < lines.length; i += 1) {
    if (isTableRow(lines[i]) && isDividerRow(lines[i + 1] ?? '')) return true;
    if (isDividerRow(lines[i]) && isTableRow(lines[i + 1] ?? '')) return true;
  }
  return false;
}

export function preprocessMarkdownTables(md: string): string {
  // 先规范化脏 markdown (拆黏连表头/分隔 + 补标题/列表空格), 再做表格→列表降级。
  // 顺序要紧: 黏成一行的 `header || ---` 必须先拆成两行, 下面的表格识别才认得出。
  const lines = normalizeLooseMarkdown(md).split('\n');
  const out: string[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    const next = lines[i + 1];

    if (isTableRow(line) && next && isDividerRow(next)) {
      const headers = splitTableRow(line);
      const rows: string[][] = [];
      i += 2;
      while (i < lines.length && isTableRow(lines[i]) && !isDividerRow(lines[i])) {
        rows.push(splitTableRow(lines[i]));
        i += 1;
      }
      if (headers.length > 0) out.push(`**${headers.join(' · ')}**`);
      pushListRows(out, rows);
      out.push('');
      continue;
    }

    if (isDividerRow(line) && next && isTableRow(next)) {
      const rows: string[][] = [];
      i += 1;
      while (i < lines.length && isTableRow(lines[i]) && !isDividerRow(lines[i])) {
        rows.push(splitTableRow(lines[i]));
        i += 1;
      }
      pushListRows(out, rows);
      out.push('');
      continue;
    }

    out.push(line);
    i += 1;
  }

  return out.join('\n');
}
