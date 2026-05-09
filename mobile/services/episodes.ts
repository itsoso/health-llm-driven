/**
 * Episodes API client — Agent-Native v3 闭环单元.
 *
 * Backend: backend/app/api/episodes.py
 *   GET  /episodes/me                  当前用户最近 Episode 列表
 *   GET  /episodes/{id}                单个 Episode 详情 (含 actions)
 *   POST /episodes/{id}/feedback       提交反馈 (action_done / action_skipped / pain / answer)
 */
import api from './api';

export type RiskLevel = 'L0' | 'L1' | 'L2' | 'L3' | 'L4';
export type EpisodeStatus = 'open' | 'closed' | 'expired' | 'escalated';
export type ActionStatus = 'pending' | 'done' | 'skipped' | 'expired';

export interface EpisodeAction {
  id: number;
  sequence: number;
  title: string;
  body: string | null;
  icon: string | null;
  action_type: string;
  template_id: string | null;
  evidence_id: string | null;
  time_window_start: string | null;
  time_window_end: string | null;
  status: ActionStatus;
  completed_at: string | null;
  skipped_at: string | null;
}

export interface EpisodeListItem {
  id: number;
  episode_type: string;
  occurred_at: string;
  status: EpisodeStatus;
  risk_level: RiskLevel;
  risk_flags: string[] | null;
  protocol_slug: string | null;
  protocol_version: string | null;
  headline: string | null;
  actions_total: number;
  actions_done: number;
}

export interface EpisodeOutcome {
  actions_total: number;
  actions_done: number;
  actions_skipped: number;
  completion_rate: number | null;
  metrics_delta: Record<string, number> | null;
  summary: string | null;
}

export interface EpisodeDetail extends EpisodeListItem {
  source_type: string | null;
  source_id: number | null;
  context_snapshot: Record<string, any> | null;
  baseline_snapshot: Record<string, any> | null;
  actions: EpisodeAction[];
  outcome: EpisodeOutcome | null;
}

export type FeedbackKind =
  | 'action_done'
  | 'action_skipped'
  | 'pain_report'
  | 'rpe'
  | 'sleep_quality'
  | 'inline_answer'
  | 'replan_request';

export interface FeedbackPayload {
  kind: FeedbackKind;
  action_id?: number;
  payload?: Record<string, any>;
  source?: 'mobile' | 'voice' | 'siri' | 'push_inline';
}

export interface FeedbackResponse {
  id: number;
  episode_id: number;
  action_id: number | null;
  kind: FeedbackKind;
  payload: Record<string, any> | null;
  source: string;
  created_at: string;
}

export async function listMyEpisodes(params?: {
  days?: number;
  limit?: number;
  episode_type?: string;
  status?: EpisodeStatus;
}): Promise<EpisodeListItem[]> {
  const { data } = await api.get<EpisodeListItem[]>('/episodes/me', { params });
  return data || [];
}

export async function getEpisode(id: number): Promise<EpisodeDetail> {
  const { data } = await api.get<EpisodeDetail>(`/episodes/${id}`);
  return data;
}

export async function submitEpisodeFeedback(
  episodeId: number,
  payload: FeedbackPayload,
): Promise<FeedbackResponse> {
  const { data } = await api.post<FeedbackResponse>(
    `/episodes/${episodeId}/feedback`,
    payload,
  );
  return data;
}
