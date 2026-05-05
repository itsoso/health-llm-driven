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

/**
 * 本周回顾语音稿 (E 周聊). voice-chat ?intent=weekly 进入时拉.
 * 80-150 字, 口语化, 末尾问"下周想..."引导用户接话.
 */
export async function fetchWeeklyVoiceScript(): Promise<BriefingVoiceScript> {
  const resp = await api.get<BriefingVoiceScript>('/v1/briefing/weekly-voice-script');
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

export interface ExtractedFact {
  id: number;
  subject: string;
  predicate: string;
  object_value: string;
  confidence: number;
}

export interface ExtractMemoryResponse {
  extracted_count: number;
  facts: ExtractedFact[];
}

/**
 * voice-chat 结束时旁路抽 fact → memory_facts.
 * Karpathy "anterograde amnesia" 解药 — AI 真正记住用户告诉它的事.
 *
 * 失败安全: 后端任何异常都不抛 (let user 退出体验顺畅).
 * 前端调用方应当 fire-and-forget, 不阻塞 router.back().
 */
export async function extractMemoryFromDialog(
  userTurns: string[],
  alertId?: number,
): Promise<ExtractMemoryResponse | null> {
  if (!userTurns || userTurns.length === 0) return null;
  try {
    const resp = await api.post<ExtractMemoryResponse>('/v1/clarification/extract-memory', {
      user_turns: userTurns,
      alert_id: alertId,
    });
    return resp.data;
  } catch {
    return null;
  }
}
