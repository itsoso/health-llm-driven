import api from './api';

// 每数据源覆盖与最新指标(后端 GET /devices/sources/summary)。
// 该端点无 response_model(OpenAPI 不带类型),故此处手写接口,对标 Mac 的
// DeviceSourcesClient struct。三源(Garmin / Apple Watch / RingConn)各占一行,
// 由 garmin_data.data_source 区分。
export interface DeviceSourceSummary {
  data_source: string;
  days_covered: number;
  latest_date: string | null;
  metrics: Record<string, number>;
}
export interface DeviceSourcesResponse {
  window_days: number;
  sources: DeviceSourceSummary[];
}

export async function getDeviceSourcesSummary(days = 30): Promise<DeviceSourcesResponse> {
  const { data } = await api.get<DeviceSourcesResponse>('/devices/sources/summary', { params: { days } });
  return data;
}

// ── 纯 helper(UI 无关,可单测)──

// HRV 存在单位 bug(部分行存成秒级 0.0xx,应为 ms)。显示层兜底:<2 视为秒 → ×1000。
function hrvMs(v: number): number {
  return v < 2 ? v * 1000 : v;
}

// 指标展示元数据(label + 格式化),顺序即展示顺序。
const METRIC_META: Record<string, { label: string; fmt: (v: number) => string }> = {
  steps: { label: '步数', fmt: (v) => `${Math.round(v)}` },
  resting_heart_rate: { label: '静息心率', fmt: (v) => `${Math.round(v)} bpm` },
  avg_heart_rate: { label: '平均心率', fmt: (v) => `${Math.round(v)} bpm` },
  hrv: { label: 'HRV', fmt: (v) => `${Math.round(hrvMs(v))} ms` },
  total_sleep_duration: { label: '睡眠', fmt: (v) => `${Math.floor(v / 60)}h${Math.round(v % 60)}m` },
  sleep_score: { label: '睡眠评分', fmt: (v) => `${Math.round(v)}` },
  spo2_avg: { label: '血氧均值', fmt: (v) => `${v.toFixed(1)}%` },
  spo2_min: { label: '血氧最低', fmt: (v) => `${v.toFixed(1)}%` },
  active_calories: { label: '活动热量', fmt: (v) => `${Math.round(v)} kcal` },
  distance_meters: { label: '距离', fmt: (v) => `${(v / 1000).toFixed(1)} km` },
};
const METRIC_ORDER = Object.keys(METRIC_META);

/** 单个指标 → {label, text};未知指标返回 null。 */
export function formatMetric(key: string, value: number): { key: string; label: string; text: string } | null {
  const m = METRIC_META[key];
  if (!m) return null;
  return { key, label: m.label, text: m.fmt(value) };
}

/** 按固定顺序取该源所有有值指标的展示项。 */
export function orderedMetrics(metrics: Record<string, number> | null | undefined): { key: string; label: string; text: string }[] {
  if (!metrics) return [];
  return METRIC_ORDER
    .filter((k) => metrics[k] != null)
    .map((k) => formatMetric(k, metrics[k])!)
    .filter(Boolean);
}

/** 源按覆盖天数降序(主力设备在前);后端已排,前端兜底。 */
export function sortedSources(resp: DeviceSourcesResponse | null | undefined): DeviceSourceSummary[] {
  return [...(resp?.sources ?? [])].sort((a, b) => b.days_covered - a.days_covered);
}
