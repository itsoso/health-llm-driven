import type { ServerCardDescriptor } from '../components/chat/cards/types';

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
