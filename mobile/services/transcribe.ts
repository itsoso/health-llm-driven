import * as FileSystem from 'expo-file-system/legacy';
import api from './api';
import { requireAIConsent } from './aiConsent';

export interface TranscribeAudioResult {
  text: string;
  provider: string;
  model?: string;
  durationMs: number;
  confidence?: 'high' | 'medium' | 'low';
  empty: boolean;
}

function readConfidence(value: unknown): TranscribeAudioResult['confidence'] {
  return value === 'high' || value === 'medium' || value === 'low' ? value : undefined;
}

export async function transcribeAudioDetailed(fileUri: string): Promise<TranscribeAudioResult> {
  await requireAIConsent();
  const base64 = await FileSystem.readAsStringAsync(fileUri, {
    encoding: FileSystem.EncodingType.Base64,
  });

  const ext = fileUri.split('.').pop() ?? 'm4a';
  const startedAt = Date.now();
  const { data } = await api.post<{
    text?: string;
    provider?: string;
    model?: string;
    duration_ms?: number;
    confidence?: string;
  }>('/chat/transcribe', {
    audio_base64: base64,
    audio_format: ext,
  });
  const text = String(data.text || '').trim();
  const durationMs = typeof data.duration_ms === 'number' && Number.isFinite(data.duration_ms)
    ? Math.max(0, Math.round(data.duration_ms))
    : Date.now() - startedAt;
  return {
    text,
    provider: data.provider || 'cloud_asr',
    ...(data.model ? { model: data.model } : {}),
    durationMs,
    ...(readConfidence(data.confidence) ? { confidence: readConfidence(data.confidence) } : {}),
    empty: text.length === 0,
  };
}

export async function transcribeAudio(fileUri: string): Promise<string> {
  return (await transcribeAudioDetailed(fileUri)).text;
}
