const HEALTH_METRIC_LABELS = ['睡眠', 'HRV', '步数', '压力', '身体电量', '饮水'] as const;

function escapeTableCell(value: string): string {
  return value.replace(/\|/g, '\\|').trim();
}

function splitValueAndStatus(segment: string): { value: string; status: string } | null {
  const match = segment.trim().match(/^(.*?)\s*((?:✅|⚠️|❌).*)$/u);
  if (!match) return null;
  return {
    value: match[1].trim(),
    status: match[2].trim(),
  };
}

function parseMetricRows(metricsText: string): Array<{ label: string; value: string; status: string }> | null {
  const rows: Array<{ label: string; value: string; status: string }> = [];

  for (let i = 0; i < HEALTH_METRIC_LABELS.length; i += 1) {
    const label = HEALTH_METRIC_LABELS[i];
    const nextLabel = HEALTH_METRIC_LABELS[i + 1];
    const start = metricsText.indexOf(label);
    if (start < 0) return null;

    const valueStart = start + label.length;
    const end = nextLabel ? metricsText.indexOf(nextLabel, valueStart) : metricsText.length;
    if (end < 0) return null;

    const parsed = splitValueAndStatus(metricsText.slice(valueStart, end));
    if (!parsed || !parsed.value || !parsed.status) return null;
    rows.push({ label, ...parsed });
  }

  return rows;
}

export function normalizeSharedAgentContent(content: string): string {
  if (/\n\s*\|.+\|\s*\n\s*\|[\s|:-]+\|/u.test(content)) {
    return content;
  }

  const headerMatch = content.match(/^(.*?)\s+综合评分：([^\s]+)\s+指标\s+数值\s+状态\s+/u);
  if (!headerMatch) return content;

  const adviceMatch = content.match(/\s+(📌\s*)?今日建议：\s*/u);
  if (!adviceMatch || adviceMatch.index == null || adviceMatch.index <= headerMatch[0].length) {
    return content;
  }

  const title = headerMatch[1].trim();
  const score = headerMatch[2].trim();
  const metricsText = content.slice(headerMatch[0].length, adviceMatch.index).trim();
  const rows = parseMetricRows(metricsText);
  if (!rows) return content;

  const afterAdvice = content.slice(adviceMatch.index + adviceMatch[0].length).trim();
  const table = [
    '| 指标 | 数值 | 状态 |',
    '| --- | --- | --- |',
    ...rows.map(row => `| ${escapeTableCell(row.label)} | ${escapeTableCell(row.value)} | ${escapeTableCell(row.status)} |`),
  ].join('\n');

  const adviceTitle = `${adviceMatch[1] || ''}今日建议：`.trim();
  return [
    title,
    `综合评分：${score}`,
    '',
    table,
    '',
    adviceTitle,
    afterAdvice,
  ].join('\n');
}
