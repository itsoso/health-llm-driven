export type VoiceInputSource = 'hold_to_talk' | 'realtime_mic';
export type VoiceDraftState = 'recording' | 'transcribing' | 'editable' | 'submitting' | 'failed';
export type VoiceDraftConfidence = 'high' | 'medium' | 'low';

export interface VoiceDraft {
  source: VoiceInputSource;
  rawTranscript: string;
  normalizedText: string;
  confidence: VoiceDraftConfidence;
  asrProvider: string;
  asrModel?: string;
  asrDurationMs?: number;
  state: VoiceDraftState;
  createdAt: number;
}

export function normalizeVoiceTranscript(raw: string): string {
  return String(raw || '')
    .trim()
    .replace(/\s+/g, ' ')
    .replace(/\bh\s*r\s*v\b/gi, 'HRV')
    .replace(/\bb\s*m\s*i\b/gi, 'BMI')
    .replace(/\bgarmin\b/gi, 'Garmin')
    .replace(/(\d+(?:\.\d+)?)\s*(公斤|千克)(?=$|\s|[，。,.;；、])/g, '$1kg')
    .replace(/(\d+(?:\.\d+)?)\s*(毫升|ml|m l)(?=$|\s|[，。,.;；、])/gi, '$1ml')
    .replace(/(\d+(?:\.\d+)?)\s*(大卡|千卡|卡路里|kcal)(?=$|\s|[，。,.;；、])/gi, '$1kcal')
    .replace(/(\d+(?:\.\d+)?)\s*(克|g)(?=$|\s|[，。,.;；、])/gi, '$1g')
    .replace(/\s+([,，。！？!?])/g, '$1')
    .trim();
}

export function estimateVoiceDraftConfidence(normalizedText: string): VoiceDraftConfidence {
  const length = normalizedText.trim().length;
  if (length >= 24 && /[，。；;]/.test(normalizedText)) return 'high';
  if (length >= 4) return 'medium';
  return 'low';
}

export function buildVoiceDraft(args: {
  source: VoiceInputSource;
  rawTranscript: string;
  state?: VoiceDraftState;
  createdAt?: number;
  asr?: {
    provider?: string;
    model?: string;
    durationMs?: number;
    confidence?: VoiceDraftConfidence;
  };
}): VoiceDraft {
  const rawTranscript = String(args.rawTranscript || '').trim();
  const normalizedText = normalizeVoiceTranscript(rawTranscript);
  const asrDurationMs = typeof args.asr?.durationMs === 'number' && Number.isFinite(args.asr.durationMs)
    ? Math.max(0, Math.round(args.asr.durationMs))
    : undefined;
  return {
    source: args.source,
    rawTranscript,
    normalizedText,
    confidence: args.asr?.confidence ?? estimateVoiceDraftConfidence(normalizedText),
    asrProvider: args.asr?.provider || (args.source === 'realtime_mic' ? 'native_realtime' : 'cloud_asr'),
    ...(args.asr?.model ? { asrModel: args.asr.model } : {}),
    ...(asrDurationMs !== undefined ? { asrDurationMs } : {}),
    state: args.state ?? 'editable',
    createdAt: args.createdAt ?? Date.now(),
  };
}

export function buildVoiceDraftExtraContext(draft: VoiceDraft): string {
  return JSON.stringify({
    source: 'mobile_voice_input',
    voice_draft: {
      source: draft.source,
        raw: draft.rawTranscript,
        normalized: draft.normalizedText,
        confidence: draft.confidence,
        asr_provider: draft.asrProvider,
        ...(draft.asrModel ? { asr_model: draft.asrModel } : {}),
        ...(typeof draft.asrDurationMs === 'number' ? { asr_duration_ms: draft.asrDurationMs } : {}),
      },
    instruction: '这条消息来自语音输入。优先按 normalized 理解；raw 仅用于转写纠错和歧义恢复。健康记录、饮食、药物、补剂、日程等写入前要按语义确认。',
  });
}

function safeParseContext(value?: string): Record<string, unknown> | null {
  if (!value || !value.trim()) return null;
  try {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      ? parsed as Record<string, unknown>
      : { text: value };
  } catch {
    return { text: value };
  }
}

export function mergeExtraContext(base?: string, extra?: string): string {
  const baseObject = safeParseContext(base);
  const extraObject = safeParseContext(extra);
  if (!baseObject && !extraObject) return '';
  if (!baseObject) return JSON.stringify(extraObject);
  if (!extraObject) return JSON.stringify(baseObject);
  return JSON.stringify({
    ...baseObject,
    voice_input: extraObject,
  });
}
