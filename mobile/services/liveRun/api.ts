/**
 * Live Run Coach 后端 API client.一次, 拿 session_id + target_pace
 * - end:   跑后一次性把 events / gps_samples 提交
 * - 跑步过程不打后端 (规则在 mobile 本地)
 */
import api from '../api';

export type LiveRunTargetLabel = 'easy' | 'tempo' | 'fast' | 'custom';

export interface LiveRunStartRequest {
  target_label: LiveRunTargetLabel;
  target_pace_seconds?: number;
  notes?: string;
}

export interface LiveRunEvent {
  ts: string;                    // ISO datetime
  rule_id: string;               // pace_drift / hr_zone_overload / total_load_exceeded
  message: string;
  metric_snapshot?: Record<string, any>;
}

export interface LiveRunGpsSample {
  ts: string;
  lat: number;
  lon: number;
  pace?: number;                 // 秒/公里
  hr?: number;
}

export interface LiveRunEndRequest {
  total_distance_m: number;
  total_duration_s: number;
  avg_pace_seconds?: number;
  avg_hr?: number;
  max_hr?: number;
  z4_plus_minutes?: number;
  calories?: number;
  events?: LiveRunEvent[];
  gps_samples?: LiveRunGpsSample[];
  aborted?: boolean;
}

export interface LiveRunSession {
  id: number;
  user_id: number;
  started_at: string;
  ended_at: string | null;
  target_pace_seconds: number | null;
  target_label: string | null;
  max_z4_minutes: number | null;
  readiness_score: number | null;
  total_distance_m: number;
  total_duration_s: number;
  avg_pace_seconds: number | null;
  avg_hr: number | null;
  max_hr: number | null;
  z4_plus_minutes: number;
  calories: number | null;
  events: LiveRunEvent[];
  gps_samples: LiveRunGpsSample[];
  narrative: string | null;
  narrative_status: string;
  aborted: boolean;
  notes: string | null;
}

export async function startLiveRun(req: LiveRunStartRequest): Promise<LiveRunSession> {
  const r = await api.post<LiveRunSession>('/v1/live-run/start', req);
  return r.data;
}

export async function endLiveRun(id: number, req: LiveRunEndRequest): Promise<LiveRunSession> {
  const r = await api.post<LiveRunSession>(`/v1/live-run/${id}/end`, req);
  return r.data;
}

export async function getLiveRun(id: number): Promise<LiveRunSession> {
  const r = await api.get<LiveRunSession>(`/v1/live-run/${id}`);
  return r.data;
}

export async function listMyLiveRuns(): Promise<LiveRunSession[]> {
  const r = await api.get<LiveRunSession[]>('/v1/live-run/me');
  return r.data;
}

export async function deleteLiveRun(id: number): Promise<void> {
  await api.delete(`/v1/live-run/${id}`);
}
