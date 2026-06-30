import type { ServerCardDescriptor } from '../components/chat/cards/types';

const REVA_UI_FENCE_RE = /\n?```reva-ui\s*\n([\s\S]*?)\n?```\n?/g;

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
  if (block.v !== 1 || block.component !== 'line_chart') return null;
  return {
    type: 'line_chart',
    data: block,
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
