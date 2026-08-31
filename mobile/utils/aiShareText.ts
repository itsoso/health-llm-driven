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

function removeFencedBlocks(content: string): string {
  return content.replace(/```[\w-]*\s*[\s\S]*?```/g, '\n');
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
  if (/(?:^|\n)\s*(?:#{1,6}\s+|[-*+]\s+|\d+\.\s+|\|.+\|)/u.test(original)) {
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

function stripInlineMarkdown(value: string): string {
  return value
    .replace(/[*_`~#]/g, '')
    .replace(/[✅✔️]/gu, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function extractFirst(pattern: RegExp, text: string): string | null {
  const match = text.match(pattern);
  return match?.[1]?.trim() || null;
}

function normalizeMealLabel(value: string | null): string | null {
  if (!value) return null;
  const v = value.trim();
  if (/早餐/.test(v)) return '早餐';
  if (/午餐/.test(v)) return '午餐';
  if (/晚餐/.test(v)) return '晚餐';
  if (/加餐|零食|夜宵/.test(v)) return '加餐';
  return v.length <= 4 ? v : null;
}

function buildDietShareMessage(content: string, style: 'compact' | 'xiaohongshu' = 'compact'): string | null {
  const flattened = content.replace(/\s+/g, ' ').trim();
  const hasDietSignal = /(?:已记录|记录完成|已写入|饮食记录(?:完成|已保存|已写入)?|本餐|这餐).{0,80}(?:kcal|千卡|蛋白|碳水|脂肪)/iu.test(flattened)
    || /(?:kcal|千卡|蛋白|碳水|脂肪).{0,80}(?:已记录|记录完成|已写入|饮食记录(?:完成|已保存|已写入)?|本餐|这餐)/iu.test(flattened);
  if (!hasDietSignal) return null;

  const meal = normalizeMealLabel(extractFirst(/已记录\s*([^—\-，,。；;\s]{1,6})/u, flattened)
    || extractFirst(/(早餐|午餐|晚餐|加餐|夜宵)/u, flattened));
  const food = stripInlineMarkdown(extractFirst(/(?:已记录[^—\-]*[—-]\s*)(.+?)(?=[，,。；;]\s*\d|，?\s*\d+(?:\.\d+)?\s*(?:kcal|千卡)|$)/iu, flattened)
    || extractFirst(/(?:食物|餐食|内容)[:：]\s*(.+?)(?=[，,。；;]|$)/iu, flattened)
    || '');
  const kcal = extractFirst(/(\d+(?:\.\d+)?)\s*(?:kcal|千卡)/iu, flattened);
  const protein = extractFirst(/蛋白(?:质)?\s*(\d+(?:\.\d+)?)\s*g/iu, flattened);
  const carbs = extractFirst(/碳水(?:化合物)?\s*(\d+(?:\.\d+)?)\s*g/iu, flattened);
  const fat = extractFirst(/脂肪\s*(\d+(?:\.\d+)?)\s*g/iu, flattened);
  const nextMatch = flattened.match(/(下一步|下一餐建议|早餐建议|午餐建议|晚餐建议|加餐建议|建议)[:：]\s*(.+?)(?:\s*(?:#|— 小巴)|$)/iu);
  const nextPrefix = nextMatch?.[1] || '';
  const nextBody = stripInlineMarkdown(nextMatch?.[2] || '');
  const nextAction = nextBody && /^(早餐|午餐|晚餐|加餐)建议$/u.test(nextPrefix)
    ? `${nextPrefix.replace('建议', '')}${nextBody}`
    : nextBody;

  if (!food && !kcal) return null;

  if (style === 'xiaohongshu') {
    const lines = [`今天的饮食打卡${meal ? `｜${meal}` : ''} 🍱`, ''];
    lines.push('不追求每餐都完美，先把真实吃下的东西记清楚。', '');

    if (food) lines.push('🥢 这一餐', food, '');

    const macroLine = [
      protein ? `蛋白质 ${Number(protein)}g` : null,
      carbs ? `碳水 ${Number(carbs)}g` : null,
      fat ? `脂肪 ${Number(fat)}g` : null,
    ].filter(Boolean).join(' ｜ ');
    if (kcal || macroLine) {
      lines.push('📊 营养估算');
      if (kcal) lines.push(`热量 ${Number(kcal)} kcal`);
      if (macroLine) lines.push(macroLine);
      lines.push('');
    }

    if (nextAction) {
      const nextTitle = /^(?:下一餐|早餐|午餐|晚餐|加餐)建议$/u.test(nextPrefix)
        ? '💡 下一餐怎么接'
        : '💡 下一步怎么做';
      lines.push(nextTitle, nextAction, '');
    }

    lines.push(
      '记录一餐，才更容易看见自己的饮食节奏。',
      '营养数据为估算值，实际会因食材、份量和烹饪方式变化。',
      '',
      '#健康饮食 #饮食记录 #一日三餐 #健康管理 #小巴',
    );
    return lines.join('\n');
  }

  const lines = ['今天这餐被小巴认真记下来了', ''];
  const mealLine = [meal, food].filter(Boolean).join(' · ');
  if (mealLine) lines.push(mealLine, '');

  const metricLine = [
    kcal ? `${Number(kcal)} kcal` : null,
    protein ? `蛋白 ${Number(protein)}g` : null,
    carbs ? `碳水 ${Number(carbs)}g` : null,
    fat ? `脂肪 ${Number(fat)}g` : null,
  ].filter(Boolean).join(' · ');
  if (metricLine) lines.push(metricLine, '');

  if (nextAction) lines.push(`下一步：${nextAction}`, '');
  lines.push('#饮食记录 #健康管理 #小巴', '', '— 小巴');
  return lines.join('\n');
}

function stripCaptionLine(line: string): string {
  return stripInlineMarkdown(line
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/^#{1,6}\s*/u, '')
    .replace(/^[-*+]\s+/u, '')
    .replace(/^\d+[.)、]\s*/u, '')
    .replace(/\[(.*?)\]\([^)]*\)/g, '$1'));
}

function tableLineToCaption(line: string): string | null {
  const trimmed = line.trim();
  if (!/^\|.*\|$/u.test(trimmed)) return null;
  const cells = trimmed
    .replace(/^\|/u, '')
    .replace(/\|$/u, '')
    .split('|')
    .map(stripCaptionLine)
    .map(value => value.trim())
    .filter(Boolean);
  if (cells.length === 0) return null;
  if (cells.every(cell => /^:?-{2,}:?$/u.test(cell))) return null;
  if (cells.length === 1) return cells[0];
  if (cells.length === 2) return `${cells[0]}：${cells[1]}`;
  return `${cells[0]}：${cells.slice(1).join('，')}`;
}

function toXiaohongshuPlainLines(content: string): string[] {
  const normalized = normalizeFlattenedAgentContent(removeFencedBlocks(content));
  const lines = normalized
    .split(/\n+/)
    .map((rawLine) => {
      const tableLine = tableLineToCaption(rawLine);
      if (tableLine) return tableLine;
      return stripCaptionLine(rawLine);
    })
    .map(line => line.replace(/\s+/g, ' ').trim())
    .filter(Boolean)
    .filter(line => !/^[-:| ]+$/u.test(line))
    .filter(line => !/^---+$/u.test(line))
    .filter(line => !/^今日建议[:：]?$/u.test(line))
    .filter(line => !/^小巴$/u.test(line))
    .filter(line => !/^仅作健康管理参考/u.test(line))
    .filter(line => !/^#/.test(line))
    .filter(line => !/^指标：数值/u.test(line));

  const result: string[] = [];
  let totalLength = 0;
  for (const line of lines) {
    if (result.includes(line)) continue;
    const nextLength = totalLength + line.length;
    if (nextLength > 420 && result.length > 0) break;
    result.push(line.length > 130 ? `${line.slice(0, 127).trim()}...` : line);
    totalLength = nextLength;
    if (result.length >= 5) break;
  }
  return result;
}

function buildConciseAdviceLines(content: string): string[] {
  const result = toXiaohongshuPlainLines(content);

  if (result.length > 0) return result;
  const fallback = stripCaptionLine(removeFencedBlocks(content).replace(/\s+/g, ' '));
  return fallback ? [fallback.slice(0, 180)] : [];
}

export function buildAiShareMessage(content: string): string {
  const dietShare = buildDietShareMessage(content);
  if (dietShare) return dietShare;

  const text = normalizeFlattenedAgentContent(content);
  return text ? `${text}\n\n— 小巴` : '';
}

export function buildXiaohongshuShareMessage(content: string): string {
  const dietShare = buildDietShareMessage(content, 'xiaohongshu');
  if (dietShare) return dietShare;

  const adviceLines = buildConciseAdviceLines(content);
  if (adviceLines.length === 0) return '';

  return [
    '小巴给我的今日建议',
    '',
    ...adviceLines,
    '',
    '仅作健康管理参考，不替代医生诊疗。',
    '#健康管理 #生活方式改善 #小巴',
  ].join('\n');
}
