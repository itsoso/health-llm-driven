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
