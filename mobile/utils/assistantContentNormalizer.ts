import type { ServerCardDescriptor } from '../components/chat/cards/types';
import { extractRevaUiBlocks } from './revaUiBlocks';

export const MAX_ASSISTANT_DISPLAY_LENGTH = 50_000;

const TRUNCATION_NOTICE = '\n\n> 内容过长，已截断显示';
const RAW_TOOL_PROTOCOL_FALLBACK = '这条回复未能正常完成，请重新发送。';
const PLACEHOLDER_FLOOD_THRESHOLD = 6;
const PLACEHOLDER_LINE_RE = /^(?:([.。·…,:;!?！？—_~*#-])\1{0,7})$/u;
const RAW_TOOL_PROTOCOL_PREFIX_RE = /^\s*(?:<tool_call\s*>\s*)?<function\s*=/i;
const RAW_TOOL_PROTOCOL_BLOCK_RE = /^\s*(?:<tool_call\s*>\s*)?<function\s*=\s*["']?[A-Za-z_]\w*["']?\s*>[\s\S]*?(?:<\/function\s*>\s*(?:<\/tool_call\s*>)?|$)\s*/i;

export type AssistantContentQualityFlag =
  | 'empty_content'
  | 'html_break_normalized'
  | 'legacy_artifact_removed'
  | 'placeholder_flood_removed'
  | 'raw_tool_protocol_removed'
  | 'malformed_protocol_block'
  | 'display_length_truncated';

export interface NormalizedAssistantContent {
  text: string;
  cards: ServerCardDescriptor[];
  qualityFlags: AssistantContentQualityFlag[];
}

/**
 * Canonical user-visible assistant content pipeline.
 *
 * Keep this function deterministic and free of raw-content telemetry. Callers may
 * record qualityFlags, but must never log the rejected protocol payload itself.
 */
export function normalizeAssistantContent(
  value: string | null | undefined,
): NormalizedAssistantContent {
  const qualityFlags: AssistantContentQualityFlag[] = [];
  let text = String(value ?? '');

  if (/<br\s*\/?>/i.test(text)) {
    text = text.replace(/<br\s*\/?>/gi, '\n');
    qualityFlags.push('html_break_normalized');
  }

  if (RAW_TOOL_PROTOCOL_PREFIX_RE.test(text)) {
    text = text.replace(RAW_TOOL_PROTOCOL_BLOCK_RE, '').trim() || RAW_TOOL_PROTOCOL_FALLBACK;
    qualityFlags.push('raw_tool_protocol_removed');
  }

  const legacyCleaned = removeLegacyArtifacts(text);
  text = legacyCleaned.text;
  if (legacyCleaned.removed) qualityFlags.push('legacy_artifact_removed');

  const placeholderResult = removePlaceholderFloods(text);
  text = placeholderResult.text;
  if (placeholderResult.removed) qualityFlags.push('placeholder_flood_removed');

  const extracted = extractRevaUiBlocks(text);
  text = extracted.text;
  if (extracted.malformedBlockCount > 0) {
    qualityFlags.push('malformed_protocol_block');
  }

  // During streaming the closing fence may not have arrived yet. Hide the
  // protocol tail instead of briefly rendering raw JSON on the user surface.
  const unfinishedProtocolAt = text.search(/(?:^|\n)```reva-ui\s*(?:\n|$)/);
  if (unfinishedProtocolAt >= 0) {
    text = text.slice(0, unfinishedProtocolAt).trim();
    if (!qualityFlags.includes('malformed_protocol_block')) {
      qualityFlags.push('malformed_protocol_block');
    }
  }

  if (text.length > MAX_ASSISTANT_DISPLAY_LENGTH) {
    const bodyLength = Math.max(0, MAX_ASSISTANT_DISPLAY_LENGTH - TRUNCATION_NOTICE.length);
    text = `${text.slice(0, bodyLength).trimEnd()}${TRUNCATION_NOTICE}`;
    qualityFlags.push('display_length_truncated');
  }

  if (!text && extracted.cards.length === 0) qualityFlags.push('empty_content');

  return {
    text,
    cards: extracted.cards,
    qualityFlags,
  };
}

function removeLegacyArtifacts(value: string): { text: string; removed: boolean } {
  let text = value;
  text = text.replace(/\n?\[附图: [^\]]+\]/g, '');
  text = text.replace(/(^|\n)\|[^\n]*\|\n\|[\s|:\-]+\|(?=\n(?!\s*\|)|\n?$)/g, '');
  text = text.replace(/\n+❌\s*(?=\n|$)/g, '');
  text = text.replace(/```(?:menu_share|card_[a-z_]+)\s*\n[\s\S]*?\n```\s*/g, '');
  return { text, removed: text !== value };
}

function removePlaceholderFloods(value: string): { text: string; removed: boolean } {
  const lines = value.split('\n');
  const kept: string[] = [];
  let removed = false;

  for (let index = 0; index < lines.length;) {
    const token = lines[index].trim();
    if (!PLACEHOLDER_LINE_RE.test(token)) {
      kept.push(lines[index]);
      index += 1;
      continue;
    }

    let end = index + 1;
    while (end < lines.length && lines[end].trim() === token) end += 1;
    if (end - index >= PLACEHOLDER_FLOOD_THRESHOLD) {
      removed = true;
    } else {
      kept.push(...lines.slice(index, end));
    }
    index = end;
  }

  const text = kept
    .map(line => line.trimEnd())
    .join('\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
  return { text, removed };
}
