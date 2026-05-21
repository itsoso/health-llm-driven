const HEALTH_METRIC_LABELS = ['睡眠', 'HRV', '步数', '压力', '身体电量', '饮水'] as const;
const WORKOUT_PLAN_HEADINGS = /(?:📋\s*今日锻炼计划|⚠️\s*注意事项|🏋️\s*推荐方案（[^）]+）|🎯\s*今日步数目标|📌\s*今日建议：)/gu;
const MEDICAL_DIAGNOSIS_HEADING = /🔬\s*诊断[:：]\s*([^💊🌿🗣🚨📌]*?)(?=\s+感染机制还原|\s+💊|\s+🌿|\s+🗣|$)/u;
const STRUCTURED_MEDICAL_HEADINGS = /(?:💊\s*治疗策略|🌿\s*补剂调整方案(?:（[^）]+）)?|🗣️?\s*嗓子哑(?:（[^）]+）)?专项护理|🚨\s*何时就医|📌\s*总结)/gu;
const SUPPLEMENT_NAMES = [
  '甘氨酸锌',
  '维生素 C',
  '维生素C',
  'NAC (乙酰半胱氨酸)',
  'NAC',
  '槲皮素 + 菠萝蛋白酶',
  '益生菌 (AKK)',
  '甘氨酸镁',
  '鱼油/Omega-3',
];

function escapeTableCell(value: string): string {
  return value.replace(/\|/g, '\\|').trim();
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
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

  const start = match.index ?? 0;
  const before = content.slice(0, start);
  const after = content.slice(start + match[0].length).trimStart();
  return `${before}${table}${after ? `\n\n${after}` : ''}`;
}

function splitSupplementAdviceAndEvidence(raw: string): { advice: string; evidence: string } {
  const text = raw.trim();
  const match = text.match(/^((?:✅|⚠️|❌)\s*[^。；;]{1,28}?)\s+(.+)$/u);
  if (!match) return { advice: text, evidence: '' };
  return { advice: match[1].trim(), evidence: match[2].trim() };
}

function formatSupplementTable(content: string): string {
  const tableStart = content.indexOf('补剂 建议 科学依据');
  if (tableStart < 0) return content;

  const afterHeaderStart = tableStart + '补剂 建议 科学依据'.length;
  const nextSectionMatch = content.slice(afterHeaderStart).match(/\s+(?:感染期可临时添加|##\s*🗣️?|##\s*🚨|##\s*📌)/u);
  const tableEnd = nextSectionMatch?.index != null
    ? afterHeaderStart + nextSectionMatch.index
    : content.length;
  const tableText = content.slice(afterHeaderStart, tableEnd).trim();
  if (!tableText) return content;

  const namePattern = SUPPLEMENT_NAMES.map(escapeRegExp).join('|');
  const rowPattern = new RegExp(
    `(${namePattern})\\s+((?:✅|⚠️|❌)[\\s\\S]*?)(?=\\s+(?:${namePattern})\\s+(?:✅|⚠️|❌)|$)`,
    'gu',
  );
  const rows = Array.from(tableText.matchAll(rowPattern)).map(match => {
    const { advice, evidence } = splitSupplementAdviceAndEvidence(match[2]);
    return [match[1], advice, evidence];
  });
  if (rows.length < 2) return content;

  const table = [
    '| 补剂 | 建议 | 科学依据 |',
    '| --- | --- | --- |',
    ...rows.map(row => `| ${row.map(escapeTableCell).join(' | ')} |`),
  ].join('\n');

  return `${content.slice(0, tableStart)}${table}${content.slice(tableEnd)}`;
}

function structureFlattenedMedicalAdvice(content: string): string {
  if (
    content.includes('\n## ')
    || (!MEDICAL_DIAGNOSIS_HEADING.test(content) && !STRUCTURED_MEDICAL_HEADINGS.test(content))
  ) {
    STRUCTURED_MEDICAL_HEADINGS.lastIndex = 0;
    return content;
  }
  STRUCTURED_MEDICAL_HEADINGS.lastIndex = 0;

  let structured = content
    .replace(MEDICAL_DIAGNOSIS_HEADING, (_match, title) => `\n\n## 🔬 诊断：${String(title).trim()}\n\n`)
    .replace(STRUCTURED_MEDICAL_HEADINGS, match => `\n\n## ${match.trim()}\n\n`);
  structured = structured
    .replace(/\n{3,}/g, '\n\n')
    .replace(/(## 🔬[^\n]+?混合感染)\s+(感染机制还原)/u, '$1\n\n$2')
    .replace(/\s+(首选：|替代：|青霉素过敏时：|你的特殊情况提醒：|抗病毒（针对鼻病毒）)/gu, '\n\n$1')
    .replace(/\s+(绝对声带休息：|湿化气道：|温盐水漱口：|避免刺激：|控制鼻后滴漏：)/gu, '\n\n$1')
    .split('\n')
    .map(line => line.trim())
    .join('\n')
    .trim();

  return formatSupplementTable(structured);
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

  const structuredMedical = structureFlattenedMedicalAdvice(flattened);
  if (structuredMedical !== flattened) return structuredMedical;

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
