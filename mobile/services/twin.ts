import api from './api';

export interface TwinFreshness {
  garmin?: string | null;
  weight?: string | null;
  labs?: string | null;
  diet?: string | null;
  genetic?: string | null;
  medication?: string | null;
}

export interface TwinMeta {
  user_id: number;
  generated_at: string;
  data_sources: string[];
  build_ms: number;
  cache_status: string;
}

export interface TwinSnapshot {
  meta: TwinMeta;
  freshness: TwinFreshness;
  // 其他分区按需扩展
  [key: string]: any;
}

export async function getMyTwin(opts?: { fresh?: boolean }): Promise<TwinSnapshot> {
  const { data } = await api.get<TwinSnapshot>('/twin/me', {
    params: opts?.fresh ? { fresh: true } : undefined,
  });
  return data;
}

// 纯函数 helper 已迁到 twinHelpers.ts (避免 jest 单测被 axios 链路污染)
export { freshnessAgeDays } from './twinHelpers';
