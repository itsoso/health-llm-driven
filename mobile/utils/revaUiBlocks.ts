import type { ServerCardDescriptor } from '../components/chat/cards/types';
import { parseMetricTable } from './metricTable';

const REVA_UI_FENCE_RE = /\n?```reva-ui\s*\n([\s\S]*?)\n?```\n?/g;
const REVA_UI_COMPONENT_TYPES: Record<string, ServerCardDescriptor['type']> = {
  line_chart: 'line_chart',
  metric_line_chart: 'metric_line_chart',
  metric_empty_state: 'metric_empty_state',
  diet_draft: 'diet_draft',
  record_quality: 'record_quality',
  diet_quality: 'record_quality',
  meal_quality: 'record_quality',
};

/**
 * 汇总卡族的 fence `type` 白名单 —— 契约同构:{"type":<此集合>,"v":1,"data":{...}}。
 * 没登记进来 = parser 静默丢弃该卡(本仓库栽过的坑),新卡上线必须同时加这一条。
 */
const REVA_UI_DATA_CARD_TYPES = new Set<string>([
  'diet_daily_summary',
  'sleep_summary',
  'medication_list',
]);

export interface ExtractedRevaUiBlocks {
  text: string;
  cards: ServerCardDescriptor[];
}

export function extractRevaUiBlocks(raw: string): ExtractedRevaUiBlocks {
  const cards: ServerCardDescriptor[] = [];
  let malformedBlockCount = 0;
  const text = raw.replace(REVA_UI_FENCE_RE, (_match, payload: string) => {
    const descriptor = descriptorFromPayload(payload);
    if (descriptor) cards.push(descriptor);
    else malformedBlockCount += 1;
    return '\n';
  });
  const normalizedText = normalizeTextAfterBlockRemoval(text);

  return {
    text: normalizedText || (malformedBlockCount > 0
      ? '这张动态卡片暂时无法显示，请让小巴用文字说明。'
      : ''),
    cards,
  };
}

function descriptorFromPayload(payload: string): ServerCardDescriptor | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(payload.trim());
  } catch {
    return null;
  }
  if (!parsed || typeof parsed !== 'object') return null;
  const block = parsed as Record<string, unknown>;

  // rank1 GenUI-first · metric_table 用 `type` 键 (非 component)。
  // v 必须为 1(未来版本 strip-only),且结构可渲染 (parseMetricTable 校验)。
  if (block.type === 'metric_table') {
    if (block.v !== 1) return null;
    const table = parseMetricTable(block);
    return table ? { type: 'metric_table', data: table } : null;
  }

  // 汇总卡族(diet / sleep / medication…):同用 `type` 键 + 顶层 `data`(非 component,
  // 与 metric_table 一致的 reva-ui fence 契约),data 原样透给对应 CardView。
  // **v 必须是整数 1** —— 后端曾发字符串 "v1" 导致卡片静默丢弃;新卡加进这个集合即可,
  // 走同一条 v 校验,不会再有哪张卡漏掉守卫。
  if (typeof block.type === 'string' && REVA_UI_DATA_CARD_TYPES.has(block.type)) {
    if (block.v !== 1) return null;
    const data = block.data;
    if (!data || typeof data !== 'object') return null;
    return { type: block.type, data };
  }

  const component = typeof block.component === 'string' ? block.component : '';
  const type = REVA_UI_COMPONENT_TYPES[component];
  if (block.v !== 1 || !type) return null;
  return {
    type,
    data: block,
    actions: Array.isArray(block.actions) ? block.actions : undefined,
  };
}

function normalizeTextAfterBlockRemoval(text: string): string {
  return text
    .split('\n')
    .map((line) => line.trimEnd())
    .join('\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}
