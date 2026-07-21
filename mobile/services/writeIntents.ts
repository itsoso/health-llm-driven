/**
 * Write 层 v0 客户端 —— 写意图账本(Agent 提议替你写一件事,一键确认才执行)。
 * 后端见 backend/app/api/write_intents.py。GET 顺带跑「复查到点」生成器。
 */
import api from './api';
import type { MedicationSafetyAlert } from './medications';

export interface WriteIntentReceiptPayload {
  operation_id: string;
  status: 'verified' | 'dismissed';
  resource_type: string;
  resource_id: string | number;
  executed_ref?: string | null;
  completed_at: string;
  verified: true;
}

export interface ConfirmWriteIntentResult {
  id?: number;
  status: string;
  decision_status?: 'executed' | 'dismissed' | 'expired';
  executed_ref?: string | null;
  idempotent?: boolean;
  write_receipts?: WriteIntentReceiptPayload[];
  safety_alerts?: MedicationSafetyAlert[];
}

export interface WriteIntent {
  id: number;
  kind: string;
  title: string;
  description: string | null;
  status: string;
  source: string | null;
  trust_tier: string;
  target_type: string | null;
  target_id: number | null;
  payload: Record<string, any> | null;
  executed_ref?: string | null;
  created_at: string | null;
}

export async function getWriteIntents(): Promise<WriteIntent[]> {
  const { data } = await api.get<{ items: WriteIntent[] }>('/write-intents');
  return data?.items ?? [];
}

export async function confirmWriteIntent(id: number): Promise<ConfirmWriteIntentResult> {
  const { data } = await api.post<ConfirmWriteIntentResult>(`/write-intents/${id}/confirm`);
  return data;
}

export async function dismissWriteIntent(id: number): Promise<ConfirmWriteIntentResult> {
  const { data } = await api.post<ConfirmWriteIntentResult>(`/write-intents/${id}/dismiss`);
  return data;
}
