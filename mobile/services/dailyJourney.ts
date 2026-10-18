import api, { getAuthSessionSnapshot } from './api';

export type JourneyMode = 'unknown' | 'walking' | 'cycling' | 'vehicle';
export interface DailyJourneySession {
  id: string; client_id: string; local_date: string; timezone: string;
  status: 'active' | 'paused' | 'ended'; version: number; segment: number;
  started_at: string; deadline_at: string; ended_at: string | null; expires_at: string;
  retention_days: 1 | 7; point_count: number;
}
export interface DailyJourneyPoint {
  id: string; recorded_at: string; latitude: number; longitude: number;
  accuracy_m: number; speed_mps: number | null;
}
export interface DailyJourneyReview {
  session: DailyJourneySession;
  points: (DailyJourneyPoint & { segment: number })[];
  segments: { id: string; point_ids: string[]; started_at: string; ended_at: string;
    distance_m: number; distance_display: string; mode: JourneyMode;
    mode_source: 'estimated' | 'user'; label: string | null }[];
  stops: { id: string; latitude: number; longitude: number; started_at: string; ended_at: string;
    duration_seconds: number; duration_display: string; label: string | null }[];
  gaps: { started_at: string; ended_at: string; reason: 'pause' | 'signal_gap' | 'low_accuracy' | 'implausible_speed' }[];
  summary: { distance_m: number; distance_display: string; observed_seconds: number;
    observed_display: string; stop_count: number; point_count: number; note: string };
}
export interface DailyJourneyAnnotation { target_id: string; label?: string; mode?: JourneyMode }
function config(token = getAuthSessionSnapshot().token) {
  if (!token) throw new Error('请先登录后记录行程');
  return { __revaExpectedAuthToken: token } as Record<string, unknown>;
}
const root = '/daily-journeys/sessions';
export const dailyJourneyAPI = {
  async list(date: string, token?: string): Promise<{ items: DailyJourneySession[] }> {
    return (await api.get(root, { ...config(token), params: { date } })).data;
  },
  async get(id: string, token?: string): Promise<DailyJourneySession> {
    return (await api.get(`${root}/${encodeURIComponent(id)}`, config(token))).data;
  },
  async start(body: { request_id: string; client_id: string; timezone: string; retention_days: 1 | 7; consent: true }, token?: string): Promise<DailyJourneySession> {
    return (await api.post(root, body, config(token))).data;
  },
  async state(id: string, body: { action: 'pause' | 'resume' | 'end'; expected_version: number; client_id: string }, token?: string): Promise<DailyJourneySession> {
    return (await api.post(`${root}/${encodeURIComponent(id)}/state`, body, config(token))).data;
  },
  async points(id: string, body: { client_id: string; segment: number; points: DailyJourneyPoint[] }, token?: string): Promise<{ accepted: number; duplicate: number; session: DailyJourneySession }> {
    return (await api.post(`${root}/${encodeURIComponent(id)}/points`, body, config(token))).data;
  },
  async review(id: string, token?: string): Promise<DailyJourneyReview> {
    return (await api.get(`${root}/${encodeURIComponent(id)}/review`, config(token))).data;
  },
  async annotate(id: string, body: { expected_version: number; annotations: DailyJourneyAnnotation[] }, token?: string): Promise<DailyJourneySession> {
    return (await api.patch(`${root}/${encodeURIComponent(id)}/annotations`, body, config(token))).data;
  },
  async remove(id: string, token?: string): Promise<void> {
    await api.delete(`${root}/${encodeURIComponent(id)}`, config(token));
  },
};

/** Never surface server payloads, URLs, coordinates, or credentials in UI errors. */
export function dailyJourneyError(error: unknown): string {
  const status = (error as { response?: { status?: number } })?.response?.status;
  if (status === 401 || status === 403) return '登录或定位授权已变化，请重新打开行程';
  if (status === 404 || status === 410) return '这条行程已删除或已到保留期限';
  if (status === 409) return '行程状态已改变，请刷新后重试';
  if (status === 422) return '行程数据未通过校验，采集已中断';
  return '暂时无法同步行程，已保留本机待同步状态';
}
