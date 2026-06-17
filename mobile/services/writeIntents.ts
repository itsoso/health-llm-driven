/**
 * Write 层 v0 客户端 —— 写意图账本(Agent 提议替你写一件事,一键确认才执行)。
 * 后端见 backend/app/api/write_intents.py。GET 顺带跑「复查到点」生成器。
 */
import api from './api';

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

export async function confirmWriteIntent(id: number): Promise<{ status: string; executed_ref?: string | null }> {
  const { data } = await api.post(`/write-intents/${id}/confirm`);
  return data;
}

export async function dismissWriteIntent(id: number): Promise<{ status: string }> {
  const { data } = await api.post(`/write-intents/${id}/dismiss`);
  return data;
}
