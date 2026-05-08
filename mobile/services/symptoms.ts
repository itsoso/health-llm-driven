import api from './api';

export type BodyPart =
  | 'eye' | 'respiratory' | 'skin' | 'digestive'
  | 'musculoskeletal' | 'head' | 'general' | 'other';

export const BODY_PARTS: Array<{ value: BodyPart; label: string; emoji: string }> = [
  { value: 'eye', label: '眼睛', emoji: '👁️' },
  { value: 'respiratory', label: '呼吸道', emoji: '🫁' },
  { value: 'head', label: '头部', emoji: '🧠' },
  { value: 'digestive', label: '消化道', emoji: '🫃' },
  { value: 'musculoskeletal', label: '肌肉/骨关节', emoji: '🦴' },
  { value: 'skin', label: '皮肤', emoji: '🖐️' },
  { value: 'general', label: '全身', emoji: '🧍' },
  { value: 'other', label: '其他', emoji: '❓' },
];

export interface SymptomEntry {
  id: number;
  user_id: number;
  occurred_at: string;
  body_part: BodyPart;
  description: string;
  severity: number | null;
  triggers: string[];
  duration_minutes: number | null;
  source: 'manual' | 'voice' | 'siri';
  notes: string | null;
  created_at: string;
}

export interface SymptomCreatePayload {
  body_part: BodyPart;
  description: string;
  severity?: number;
  triggers?: string[];
  duration_minutes?: number;
  occurred_at?: string;
  source?: 'manual' | 'voice' | 'siri';
  notes?: string;
}

export async function createSymptom(payload: SymptomCreatePayload): Promise<SymptomEntry> {
  const { data } = await api.post<SymptomEntry>('/symptoms', payload);
  return data;
}

export async function listMySymptoms(params?: {
  start_date?: string;
  end_date?: string;
  body_part?: BodyPart;
  limit?: number;
}): Promise<SymptomEntry[]> {
  const { data } = await api.get<SymptomEntry[]>('/symptoms/me', { params });
  return data || [];
}

export async function deleteSymptom(id: number): Promise<void> {
  await api.delete(`/symptoms/${id}`);
}
