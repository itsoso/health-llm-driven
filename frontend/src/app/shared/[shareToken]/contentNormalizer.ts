const HEALTH_METRIC_LABELS = ['睡眠', 'HRV', '步数', '压力', '身体电量', '饮水'] as const;
const WORKOUT_PLAN_HEADINGS = /(?:📋\s*今日锻炼计划|⚠️\s*注意事项|🏋️\s*推荐方案（[^）]+）|🎯\s*今日步数目标|📌\s*今日建议：)/gu;

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

function sectionizeWorkoutPlan(content: string): string {
  const matches = Array.from(content.matchAll(WORKOUT_PLAN_HEADINGS));
  if (matches.length === 0) return content;

  const parts: string[] = [];
  const firstIndex = matches[0].index ?? 0;
  const preface = content.slice(0, firstIndex).trim();
  if (preface) parts.push(preface);

  for (let i = 0; i < matches.length; i += 1) {
    const match = matches[i];
    const start = match.index ?? 0;
    const heading = match[0].replace(/\s+/g, ' ').trim();
    const bodyStart = start + match[0].length;
    const bodyEnd = i + 1 < matches.length ? matches[i + 1].index ?? content.length : content.length;
    const body = content.slice(bodyStart, bodyEnd).trim();

    parts.push(`## ${heading}`);
    if (body) parts.push(body);
  }

  return parts.join('\n\n');
}

function formatWorkoutPlanTable(content: string): string {
  const tablePattern = /阶段\s+内容\s+时长\s+说明\s+热身\s+(.+?)\s+(\d+\s*min)\s+(.+?)\s+主训练\s+(.+?)\s+(\d+\s*min)\s+(.+?)\s+放松\s+(.+?)\s+(\d+\s*min)\s+(.+?)(?=\s+(?:具体选项|[A-Z]\.|🎯|📌)|$)/u;
  const match = content.match(tablePattern);
  if (!match) return content;

  const rows = [
    ['热身', match[1], match[2], match[3]],
    ['主训练', match[4], match[5], match[6]],
    ['放松', match[7], match[8], match[9]],
  ];
  const table = [
    '| 阶段 | 内容 | 时长 | 说明 |',
    '| --- | --- | --- | --- |',
    ...rows.map(row => `| ${row.map(escapeTableCell).join(' | ')} |`),
  ].join('\n');

  return content.replace(match[0], table);
}

export function normalizeSharedAgentContent(content: string): string {
  if (/\n\s*\|.+\|\s*\n\s*\|[\s|:-]+\|/u.test(content)) {
    return content;
  }

  const flattened = content.replace(/\s+/g, ' ').trim();
  if (flattened.includes('阶段 内容 时长 说明')) {
    const signatureMatch = flattened.match(/\s+—\s*健康 Agent$/u);
    const body = signatureMatch && signatureMatch.index != null
      ? flattened.slice(0, signatureMatch.index).trim()
      : flattened;
    const formatted = sectionizeWorkoutPlan(formatWorkoutPlanTable(body));
    return signatureMatch ? `${formatted}\n\n— 健康 Agent` : formatted;
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
