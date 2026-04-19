/**
 * 健康咨询 API 客户端 (RN 端)
 *
 * 对应后端 `/api/v1/health-consultations/me/*`.
 * 跟 frontend/src/services/api/records.ts 的 healthConsultationApi 完全等价.
 */
import api from './api';

export interface ConsultListItem {
  id: number;
  version: number;
  title: string;
  topic?: string;
  consultation_type: string;
  triggered_by: string;
  status: string;
  summary?: string;
  verification_scheduled_at?: string;
  created_at: string;
  total_items: number;
  hypothesis_count: number;
  action_count: number;
  prediction_count: number;
  red_flag_count: number;
  pending_count: number;
}

export interface ConsultationItem {
  id: number;
  consultation_id: number;
  item_type: 'hypothesis' | 'action' | 'prediction' | 'red_flag' | 'note';
  item_code?: string;
  priority: number;
  title: string;
  content_markdown?: string;
  meta: Record<string, unknown>;
  status: string;
  due_date?: string;
  user_note?: string;
  outcome?: string;
  actual_value?: string;
  verified_at?: string;
  completed_at?: string;
  created_at: string;
  updated_at: string;
}

export interface ConsultationDetail extends ConsultListItem {
  chief_complaint?: string;
  input_snapshot?: Record<string, unknown>;
  rationale_markdown: string;
  verified_at?: string;
  generated_by?: string;
  llm_model?: string;
  items: ConsultationItem[];
}

export async function listConsultations(limit = 20): Promise<ConsultListItem[]> {
  const { data } = await api.get<ConsultListItem[]>('/health-consultations/me', {
    params: { limit },
  });
  return data || [];
}

export async function listActiveConsultations(): Promise<ConsultListItem[]> {
  const { data } = await api.get<ConsultListItem[]>('/health-consultations/me/active');
  return data || [];
}

export async function getConsultation(id: number): Promise<ConsultationDetail> {
  const { data } = await api.get<ConsultationDetail>(`/health-consultations/me/${id}`);
  return data;
}

export async function updateConsultationItem(
  itemId: number,
  payload: Partial<Pick<ConsultationItem, 'status' | 'user_note' | 'outcome' | 'actual_value'>>,
): Promise<ConsultationItem> {
  const { data } = await api.patch<ConsultationItem>(
    `/health-consultations/me/items/${itemId}`,
    payload,
  );
  return data;
}

export async function verifyPredictions(id: number): Promise<{
  verified_count: number;
  predictions: Array<{ item_id: number; item_code?: string; status: string; actual_value?: string }>;
}> {
  const { data } = await api.post(`/health-consultations/me/${id}/verify`);
  return data;
}
