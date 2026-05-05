import api from './api';

export interface BriefingVoiceScript {
  script: string;
  char_count: number;
  generated_at: string;
  target_date: string;
}

/**
 * 拉今日晨间语音简报短稿 (60-90 字).
 * 后端走 build_twin + 规则抽取, 缓存 10min, 多次调用便宜.
 */
export async function fetchBriefingVoiceScript(): Promise<BriefingVoiceScript> {
  const resp = await api.get<BriefingVoiceScript>('/v1/briefing/voice-script');
  return resp.data;
}

export interface ClarificationOpener {
  opener: string;
  rationale: string;
  alert_type: string;
  alert_id: number;
}

/**
 * Anomaly alert 主动澄清开场白 — 进 voice-chat ?intent=clarify&alert_id=X 时拉.
 * 拿到 opener 后 speakDirect 播 + 进 listening 接话, AI 像主动开口的教练.
 */
export async function fetchClarificationOpener(alertId: number): Promise<ClarificationOpener> {
  const resp = await api.get<ClarificationOpener>('/v1/clarification/opener', {
    params: { alert_id: alertId },
  });
  return resp.data;
}
