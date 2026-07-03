import api from './api';

export type AssistantRecordActionResult =
  | {
      status: 'created';
      type: string;
      message: string;
      recordId?: number;
      undoPath?: string;
    }
  | {
      status: 'needs_manual';
      message: string;
      route: string;
    };

export async function saveAssistantReplyAsMemory(text: string): Promise<void> {
  const value = text.trim();
  if (!value) return;

  await api.post('/memory-facts', {
    tier: 'working',
    subject: 'assistant_reply',
    predicate: 'suggests',
    object_value: value,
    confidence: 0.6,
    tags: ['chat', 'assistant_suggestion'],
    is_sensitive: false,
  });
}

export async function createRecordFromAssistantReply(text: string): Promise<AssistantRecordActionResult> {
  const quickRecordText = buildQuickRecordTextFromAssistantReply(text);
  if (!quickRecordText) {
    return manualRecordFallback();
  }

  try {
    const { data } = await api.post('/quick-record', { text: quickRecordText });
    return {
      status: 'created',
      type: String(data?.type || 'record'),
      message: String(data?.message || '已生成记录'),
      recordId: typeof data?.record_id === 'number' ? data.record_id : undefined,
      undoPath: typeof data?.undo_path === 'string' ? data.undo_path : undefined,
    };
  } catch (error: any) {
    if (error?.response?.status === 400) {
      return manualRecordFallback();
    }
    throw error;
  }
}

export function buildQuickRecordTextFromAssistantReply(text: string): string | null {
  const value = normalizeAssistantText(text);
  if (!value) return null;

  const diet = inferDietQuickRecord(value);
  if (diet) return diet;

  const water = value.match(/(?:喝水|饮水|补水|水)\s*(\d{2,4})\s*(?:ml|毫升)/i);
  if (water) return `喝水${water[1]}`;

  const bp = value.match(/血压\s*(\d{2,3})\s*[/／]\s*(\d{2,3})/);
  if (bp) return `血压${bp[1]}/${bp[2]}`;

  const weight = value.match(/体重\s*([\d.]+)\s*(?:kg|公斤)?/i);
  if (weight) return `体重${weight[1]}`;

  const supplement = value.match(/(?:已服用|已补充|吃了|服用)\s*([A-Za-z0-9\u4e00-\u9fa5 +_-]{2,30}(?:维生素|鱼油|镁|锌|叶酸|益生菌|辅酶|NAC|维C|维D|D3|B族)[A-Za-z0-9\u4e00-\u9fa5 +_-]*)/i);
  if (supplement) return `吃了${supplement[1].trim()}`;

  return null;
}

function normalizeAssistantText(text: string): string {
  return String(text || '')
    .replace(/\*\*/g, '')
    .replace(/^[\s>*#-]+/gm, '')
    .replace(/[✅☑️✔️]/g, '')
    .replace(/\r/g, '\n')
    .trim();
}

function inferDietQuickRecord(text: string): string | null {
  const lines = text
    .split('\n')
    .map(line => line.trim())
    .filter(Boolean)
    .slice(0, 20);
  for (const line of lines) {
    const record = readDietLine(line);
    if (record) return record;
  }
  return readDietLine(text.replace(/\n+/g, ' '));
}

function readDietLine(line: string): string | null {
  const patterns = [
    /(?:已记录|记录(?:了)?)(早餐|午餐|晚餐|加餐|夜宵)\s*[—\-:：]?\s*(.+)/,
    /(早餐|午餐|晚餐|加餐|夜宵)\s*(?:已记录|记录完成)\s*[—\-:：]?\s*(.+)/,
  ];
  for (const pattern of patterns) {
    const match = line.match(pattern);
    if (!match) continue;
    const meal = match[1];
    const food = sanitizeFoodText(match[2]);
    if (food) return `${meal}${food}`;
  }
  return null;
}

function sanitizeFoodText(value: string): string | null {
  const cleaned = value
    .replace(/（[^）]*(?:蛋白|碳水|脂肪|热量|kcal|千卡)[^）]*）/gi, '')
    .split(/[，,。；;]/)[0]
    .replace(/\b\d+(?:\.\d+)?\s*(?:kcal|千卡|cal)\b/gi, '')
    .replace(/\s+/g, ' ')
    .trim();
  if (!cleaned || cleaned.length < 2) return null;
  if (/^(整体评价|进度更新|建议|目标|本餐|这餐)$/.test(cleaned)) return null;
  return cleaned.slice(0, 120);
}

function manualRecordFallback(): AssistantRecordActionResult {
  return {
    status: 'needs_manual',
    message: '没识别到可直接写入的记录，已打开记录页',
    route: '/(tabs)/record',
  };
}
