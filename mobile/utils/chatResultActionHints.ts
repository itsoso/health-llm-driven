export type ChatResultActionKey = 'plan' | 'memory' | 'record' | 'followup';

export type ChatResultActionHint = {
  key: ChatResultActionKey;
  priority: 'primary' | 'secondary';
};

type DeriveInput = {
  text: string;
  toolsUsed?: string[];
  sourcesUsed?: string[];
};

export function deriveChatResultActions(input: DeriveInput): ChatResultActionHint[] {
  const text = normalize(input.text);
  if (!text) return [];

  const hasRecord = looksLikeDeterministicRecord(text);
  const hasMemory = looksMemoryWorthy(text, input.sourcesUsed);
  const hasPlan = !hasRecord && looksActionable(text, input.toolsUsed);

  const ordered: ChatResultActionKey[] = [];
  if (hasRecord) ordered.push('record');
  else if (hasPlan) ordered.push('plan');
  else if (hasMemory) ordered.push('memory');

  if (hasMemory && !ordered.includes('memory')) ordered.push('memory');
  if (hasPlan && !ordered.includes('plan') && ordered.length < 2) ordered.push('plan');
  if (!ordered.includes('followup')) ordered.push('followup');

  return ordered.slice(0, 3).map((key, index) => ({
    key,
    priority: index === 0 && key !== 'followup' ? 'primary' : 'secondary',
  }));
}

function normalize(text: string): string {
  return String(text || '')
    .replace(/\*\*/g, '')
    .replace(/^[\s>*#-]+/gm, '')
    .replace(/\r/g, '\n')
    .trim();
}

function looksDeterministicDietRecord(text: string): boolean {
  return /(?:已记录|记录(?:了)?)(早餐|午餐|晚餐|加餐|夜宵)\s*[—\-:：]?\s*.{2,}/.test(text)
    || /(早餐|午餐|晚餐|加餐|夜宵)\s*(?:已记录|记录完成)\s*[—\-:：]?\s*.{2,}/.test(text);
}

function looksLikeDeterministicRecord(text: string): boolean {
  if (looksDeterministicDietRecord(text)) return true;
  if (/(?:喝水|饮水|补水|水)\s*\d{2,4}\s*(?:ml|毫升)/i.test(text)) return true;
  if (/血压\s*\d{2,3}\s*[/／]\s*\d{2,3}/.test(text)) return true;
  if (/体重\s*[\d.]+\s*(?:kg|公斤)?/i.test(text)) return true;
  if (/(?:已服用|已补充|吃了|服用)\s*[A-Za-z0-9\u4e00-\u9fa5 +_-]{2,30}(?:维生素|鱼油|镁|锌|叶酸|益生菌|辅酶|NAC|维C|维D|D3|B族)/i.test(text)) return true;
  return false;
}

function looksMemoryWorthy(text: string, sourcesUsed?: string[]): boolean {
  if (sourcesUsed?.some(source => /memory|记忆/i.test(source))) return true;
  return /我记得|记住|后续我会|你的(?:偏好|习惯|目标|禁忌|过敏|长期)|你对.{1,12}敏感|你(?:通常|经常|工作日|周末)/.test(text);
}

function looksActionable(text: string, toolsUsed?: string[]): boolean {
  if (toolsUsed?.some(tool => /agenda|action|plan|write_intent/i.test(tool))) return true;
  if (/今日建议|今天建议|下一步|行动计划|执行建议|建议你/.test(text) && hasConcreteAction(text)) return true;
  if (/(?:今晚|明天|本周|睡前|餐后|饭后|起床后|训练后).{0,24}(?:分钟|步行|散步|上床|补水|记录|复查|测量|停止进食)/.test(text)) return true;
  return /\d+\s*(?:分钟|min|ml|毫升|点|:|：).{0,28}(?:步行|散步|上床|睡|补水|记录|训练|复查)/i.test(text);
}

function hasConcreteAction(text: string): boolean {
  return /步行|散步|上床|睡前|停止进食|补水|喝水|记录|测量|复查|提醒|训练|拉伸|冥想|服用|预约/.test(text)
    || /\d+\s*(?:分钟|min|ml|毫升|点|:|：)/i.test(text);
}
