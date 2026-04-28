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

/**
 * 把 freshness 原始字符串 (如 "1h ago" / "今日" / "2026-04-27") 归一化为 age_days 数值.
 * 未知格式返回 null (不做降级判断).
 */
export function freshnessAgeDays(text: string | null | undefined, now = new Date()): number | null {
  if (!text) return null;
  const t = text.trim();

  // "今日" / "今天" / "刚刚" / "1h ago" < 1 day
  if (/今日|今天|刚刚|just now|< ?1 ?day/i.test(t)) return 0;
  if (/(\d+)\s*h\s*ago/i.test(t)) return 0;
  if (/(\d+)\s*min\s*ago/i.test(t)) return 0;

  // "3d ago" / "3 天前"
  const daysMatch = t.match(/(\d+)\s*(d|天|day)/i);
  if (daysMatch) return parseInt(daysMatch[1], 10);

  // "2026-04-15" 形式
  const dateMatch = t.match(/(\d{4})-(\d{2})-(\d{2})/);
  if (dateMatch) {
    const [, y, m, d] = dateMatch;
    const dt = new Date(Number(y), Number(m) - 1, Number(d));
    const diffMs = now.getTime() - dt.getTime();
    return Math.max(0, Math.floor(diffMs / (1000 * 60 * 60 * 24)));
  }

  // "2 个月前" / "6 months ago"
  const monthsMatch = t.match(/(\d+)\s*(个月|months?|mo)/i);
  if (monthsMatch) return parseInt(monthsMatch[1], 10) * 30;

  return null;
}
