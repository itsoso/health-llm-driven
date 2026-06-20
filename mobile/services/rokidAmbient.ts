import api from './api';
import {
  getRokidIntegrationStatus,
  openHiRokid,
  type RokidIntegrationStatus,
} from '../modules/rokid-bridge';

export const ROKID_SURFACE = 'rokid_glasses';
export const ROKID_DEVICE_TYPE = 'glasses';
export const ROKID_PRIVACY_CLASS = 'health_l3';

export type RokidVisualIntent =
  | 'food_scan'
  | 'medication_scan'
  | 'supplement_scan'
  | 'label_scan'
  | 'environment_scan'
  | 'note_scan';

export type RokidAudioIntent =
  | 'food'
  | 'symptom'
  | 'fatigue'
  | 'mood'
  | 'supplement'
  | 'medication'
  | 'movement'
  | 'note';

export type SubmitRokidVisualInput = {
  intent: RokidVisualIntent;
  imageUri?: string;
  imageSha256?: string;
  ocrText?: string;
  recognitionResult?: Record<string, unknown>;
  confidence?: number;
  capturedAt?: string;
  privacyClass?: string;
  meta?: Record<string, unknown>;
};

export type RokidAmbientEventResponse = {
  id?: number;
  status?: string | null;
  target_type?: string | null;
  target_id?: number | null;
};

export type SubmitRokidVisualInputResponse = {
  event?: RokidAmbientEventResponse;
  recommended_next_action?: Record<string, string> | null;
};

export type SubmitRokidAudioInput = {
  intent: RokidAudioIntent;
  transcript: string;
  confidence?: number;
  capturedAt?: string;
  privacyClass?: string;
  meta?: Record<string, unknown>;
};

export async function submitRokidVisualInput(input: SubmitRokidVisualInput): Promise<SubmitRokidVisualInputResponse> {
  const response = await api.post<SubmitRokidVisualInputResponse>('/ambient/visual-inputs', {
    intent: input.intent,
    source: ROKID_SURFACE,
    device_type: ROKID_DEVICE_TYPE,
    image_uri: input.imageUri,
    image_sha256: input.imageSha256,
    ocr_text: input.ocrText,
    recognition_result: input.recognitionResult,
    confidence: input.confidence,
    captured_at: input.capturedAt,
    privacy_class: input.privacyClass ?? ROKID_PRIVACY_CLASS,
    meta: input.meta,
  });
  return response.data;
}

export async function submitRokidAudioInput(input: SubmitRokidAudioInput) {
  const response = await api.post('/ambient/audio-inputs', {
    intent: input.intent,
    transcript: input.transcript,
    source: ROKID_SURFACE,
    device_type: ROKID_DEVICE_TYPE,
    confidence: input.confidence,
    captured_at: input.capturedAt,
    privacy_class: input.privacyClass ?? ROKID_PRIVACY_CLASS,
    meta: input.meta,
  });
  return response.data;
}

export async function listRokidGlanceCards() {
  const response = await api.get('/ambient/glance-cards', {
    params: { surface: ROKID_SURFACE },
  });
  return response.data;
}

export async function openRokidCompanionIfAvailable(): Promise<{
  opened: boolean;
  status: RokidIntegrationStatus;
}> {
  const status = await getRokidIntegrationStatus();
  if (!status.canOpenHiRokid) {
    return { opened: false, status };
  }
  return {
    opened: await openHiRokid(),
    status,
  };
}
