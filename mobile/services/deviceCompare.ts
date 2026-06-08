import api from './api';

// 双设备一致性对比(后端 /devices/compare):同时戴 Apple Watch + Garmin 时,
// 同指标并排比 + 一致度。只有 ≥2 个来源都有的指标才出现在 comparisons 里。
export interface DeviceMetricCompare {
  metric: string;
  label: string;
  unit: string;
  by_source: Record<string, number>; // {garmin: 51, apple_watch: 46}
  diff: number;
  agreement: number | null; // 1=完全一致,越低差异越大;null=均值为0无法算
}
export interface DeviceComparison {
  sources: string[];
  window_days: number;
  comparisons: DeviceMetricCompare[];
  note: string;
}

export async function getDeviceComparison(days = 7): Promise<DeviceComparison> {
  const { data } = await api.get<DeviceComparison>('/devices/compare', { params: { days } });
  return data;
}

// ── 纯 helper(UI 无关,可单测)──

const SOURCE_LABELS: Record<string, string> = {
  garmin: 'Garmin',
  apple_watch: 'Apple Watch',
  apple_health: 'Apple Watch',
  withings: 'Withings',
};

/** data_source 原始值 → 展示名(未知则原样)。 */
export function sourceLabel(src: string): string {
  return SOURCE_LABELS[src] ?? src;
}

/** 至少两个来源、且有可比指标才算"可对比";否则主页不渲染。 */
export function hasComparison(resp: DeviceComparison | null | undefined): boolean {
  return !!resp && (resp.comparisons?.length ?? 0) > 0;
}

/**
 * 取最值得看的一条:一致度最低(差异最大)优先 —— 用户最想知道哪台和哪台对不上。
 * agreement 为 null 视为 1(无差异信息)排最后。空 → null。
 */
export function pickTopDisagreement(
  resp: DeviceComparison | null | undefined,
): DeviceMetricCompare | null {
  const list = resp?.comparisons ?? [];
  if (list.length === 0) return null;
  return [...list].sort((a, b) => (a.agreement ?? 1) - (b.agreement ?? 1))[0];
}
