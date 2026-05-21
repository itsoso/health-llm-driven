const WORKOUT_PLAN_HEADINGS = /(?:📋\s*今日锻炼计划|⚠️\s*注意事项|🏋️\s*推荐方案（[^）]+）|🎯\s*今日步数目标|📌\s*今日建议：)/gu;
const GENERAL_ADVICE_LABELS = [
  '免疫"开窗期"',
  '累积疲劳',
  '时长锁定',
  '频率红线',
  '看灯行事',
  '跑后防护（关键）',
  '跑后防护',
] as const;

function escapeTableCell(value: string): string {
  return value.replace(/\|/g, '\\|').trim();
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function hasMarkdownTable(content: string): boolean {
  return /\n\s*\|.+\|\s*\n\s*\|[\s|:-]+\|/u.test(content);
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

  const start = match.index ?? 0;
  const before = content.slice(0, start);
  const after = content.slice(start + match[0].length).trimStart();
  return `${before}${table}${after ? `\n\n${after}` : ''}`;
}

function structureFlattenedGeneralAdvice(content: string): string {
  if (content.includes('\n## ') || content.includes('\n- ')) return content;

  let structured = content.trim()
    .replace(/\s+(🛑\s*为什么[^？?]{2,80}[？?])\s+/u, '\n\n## $1\n\n')
    .replace(/\s+(🛡️\s*新策略[:：]\S{2,80})\s+/u, '\n\n## $1\n\n')
    .replace(/\s+(💧\s*提醒[:：])\s*/u, '\n\n## $1\n\n')
    .replace(/\s+(📌\s*今日建议[:：])\s*/u, '\n\n## $1\n\n');

  for (const label of GENERAL_ADVICE_LABELS) {
    const pattern = new RegExp(`\\s+(${escapeRegExp(label)}[:：])`, 'gu');
    structured = structured.replace(pattern, '\n\n- $1');
  }

  structured = structured
    .replace(/\s+(总结[:：])/gu, '\n\n**$1** ')
    .split('\n')
    .map(line => line.trim())
    .join('\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();

  if (structured === content || (!structured.includes('\n## ') && !structured.includes('\n- '))) {
    return content;
  }

  return structured;
}

function normalizeFlattenedAgentContent(content: string): string {
  const original = content.trim();
  if (/\n\s*(?:#{1,6}\s+|[-*+]\s+|\d+\.\s+|\|.+\|)/u.test(original)) {
    return original;
  }

  if (hasMarkdownTable(content)) return content.trim();

  const flattened = content.replace(/\s+/g, ' ').trim();
  if (!flattened) return '';

  if (flattened.includes('阶段 内容 时长 说明')) {
    return sectionizeWorkoutPlan(formatWorkoutPlanTable(flattened));
  }

  return structureFlattenedGeneralAdvice(flattened);
}

export function buildAiShareMessage(content: string): string {
  const text = normalizeFlattenedAgentContent(content);
  return text ? `${text}\n\n— 健康 Agent` : '';
}
