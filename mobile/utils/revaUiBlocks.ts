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

export interface ExtractedRevaUiBlocks {
  text: string;
  cards: ServerCardDescriptor[];
}

export function extractRevaUiBlocks(raw: string): ExtractedRevaUiBlocks {
  const cards: ServerCardDescriptor[] = [];
  const text = raw.replace(REVA_UI_FENCE_RE, (_match, payload: string) => {
    const descriptor = descriptorFromPayload(payload);
    if (descriptor) cards.push(descriptor);
    return '\n';
  });

  return {
    text: normalizeTextAfterBlockRemoval(text),
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
