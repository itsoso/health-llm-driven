import api from './api';
import { formatLocalDate } from '../utils/dietDate';

export type TimeRange = '1W' | '1M' | '3M' | '6M' | '1Y';

export interface TrendDataPoint {
  date: string;
  value: number;
  secondaryValue?: number;
  unit: string;
  isAbnormal?: boolean;
}

export interface TrendSeries {
  label: string;
  color: string;
  data: TrendDataPoint[];
  referenceRange?: { low: number; high: number };
}

export function timeRangeToDates(range: TimeRange): { start: string; end: string } {
  const end = new Date();
  const start = new Date();
  switch (range) {
    case '1W': start.setDate(end.getDate() - 7); break;
    case '1M': start.setMonth(end.getMonth() - 1); break;
    case '3M': start.setMonth(end.getMonth() - 3); break;
    case '6M': start.setMonth(end.getMonth() - 6); break;
    case '1Y': start.setFullYear(end.getFullYear() - 1); break;
  }
  return {
    start: formatLocalDate(start),
    end: formatLocalDate(end),
  };
}

export async function fetchWeightTrend(range: TimeRange): Promise<TrendSeries[]> {
  const { start, end } = timeRangeToDates(range);
  const { data } = await api.get('/weight/records/me', {
    params: { start_date: start, end_date: end, limit: 365 },
  });
  const records = Array.isArray(data) ? data : data.records ?? [];
  const weightPoints: TrendDataPoint[] = records.map((r: any) => ({
    date: r.record_date,
    value: r.weight,
    unit: 'kg',
  }));
  const bmiPoints: TrendDataPoint[] = records
    .filter((r: any) => r.bmi != null)
    .map((r: any) => ({
      date: r.record_date,
      value: r.bmi,
      unit: '',
    }));
  const series: TrendSeries[] = [
    { label: '体重', color: '#FF9F0A', data: weightPoints },
  ];
  if (bmiPoints.length > 0) {
    series.push({
      label: 'BMI',
      color: '#64D2FF',
      data: bmiPoints,
      referenceRange: { low: 18.5, high: 24.9 },
    });
  }
  return series;
}

export async function fetchBPTrend(range: TimeRange): Promise<TrendSeries[]> {
  const { start, end } = timeRangeToDates(range);
  const { data } = await api.get('/blood-pressure/records/me', {
    params: { start_date: start, end_date: end, limit: 365 },
  });
  const records = Array.isArray(data) ? data : data.records ?? [];
  return [
    {
      label: '收缩压',
      color: '#FF453A',
      data: records.map((r: any) => ({
        date: r.record_date,
        value: r.systolic,
        unit: 'mmHg',
      })),
      referenceRange: { low: 90, high: 120 },
    },
    {
      label: '舒张压',
      color: '#FF9F0A',
      data: records.map((r: any) => ({
        date: r.record_date,
        value: r.diastolic,
        unit: 'mmHg',
      })),
      referenceRange: { low: 60, high: 80 },
    },
  ];
}

export async function fetchIndicatorTrend(
  name: string,
  range: TimeRange,
): Promise<TrendSeries[]> {
  const { data } = await api.get(
    `/family-health/medical-indicators/trend/${encodeURIComponent(name)}`,
  );
  const points: TrendDataPoint[] = (data.data_points ?? []).map((p: any) => ({
    date: p.date,
    value: p.value,
    unit: p.unit || '',
    isAbnormal: p.is_abnormal,
  }));
  const refRange =
    points.length > 0 && data.data_points?.[0]?.reference_low != null
      ? { low: data.data_points[0].reference_low, high: data.data_points[0].reference_high }
      : undefined;
  return [
    {
      label: data.indicator_name ?? name,
      color: '#0A8F8F',
      data: points,
      referenceRange: refRange,
    },
  ];
}

/**
 * Garmin 日数据趋势 (心率 / HRV / Body Battery / 睡眠 / 步数).
 * 复用 dashboard 端点: /daily-health/garmin/me?start_date=&end_date=
 * 返回按 record_date 升序的点序列. metric 取值:
 *   - heart_rate → resting_heart_rate
 *   - hrv → hrv
 *   - body_battery → body_battery_current (主) / body_battery_most_charged (次)
 *   - sleep → total_sleep_duration / 60 (h)
 *   - sleep_score → sleep_score
 *   - steps → steps
 */
const GARMIN_METRIC_CFG: Record<string, { label: string; color: string; unit: string; field: string; transform?: (v: number) => number; refRange?: { low: number; high: number } }> = {
  heart_rate: { label: '静息心率', color: '#FF375F', unit: 'bpm', field: 'resting_heart_rate', refRange: { low: 50, high: 80 } },
  hrv: { label: 'HRV', color: '#40C8E0', unit: 'ms', field: 'hrv' },
  body_battery: { label: '电量 (当前)', color: '#30D158', unit: '', field: 'body_battery_current' },
  sleep: { label: '睡眠时长', color: '#BF5AF2', unit: 'h', field: 'total_sleep_duration', transform: (v) => v / 60, refRange: { low: 7, high: 9 } },
  sleep_score: { label: '睡眠评分', color: '#5E8CFF', unit: '分', field: 'sleep_score', refRange: { low: 80, high: 100 } },
  steps: { label: '步数', color: '#34C759', unit: '步', field: 'steps' },
};

export async function fetchGarminMetricTrend(
  metric: string,
  range: TimeRange,
): Promise<TrendSeries[]> {
  const cfg = GARMIN_METRIC_CFG[metric];
  if (!cfg) return [];

  const { start, end } = timeRangeToDates(range);
  const { data } = await api.get('/daily-health/garmin/me', {
    params: { start_date: start, end_date: end },
  });
  const days = Array.isArray(data) ? data : data?.records ?? [];

  const points: TrendDataPoint[] = days
    .map((d: any) => {
      const raw = d[cfg.field];
      if (raw == null || raw === 0) return null;
      const v = cfg.transform ? cfg.transform(raw) : raw;
      return { date: d.record_date, value: Number.isFinite(v) ? v : 0, unit: cfg.unit };
    })
    .filter((p: TrendDataPoint | null): p is TrendDataPoint => p !== null)
    .sort((a: TrendDataPoint, b: TrendDataPoint) => a.date.localeCompare(b.date));

  const series: TrendSeries[] = [
    { label: cfg.label, color: cfg.color, data: points, referenceRange: cfg.refRange },
  ];

  // 电量附上"峰值"副线
  if (metric === 'body_battery') {
    const peakPoints: TrendDataPoint[] = days
      .map((d: any) => {
        const raw = d.body_battery_most_charged;
        if (raw == null || raw === 0) return null;
        return { date: d.record_date, value: raw, unit: '' };
      })
      .filter((p: TrendDataPoint | null): p is TrendDataPoint => p !== null)
      .sort((a: TrendDataPoint, b: TrendDataPoint) => a.date.localeCompare(b.date));
    if (peakPoints.length > 0) {
      series.push({ label: '当日峰值', color: '#A0E7C0', data: peakPoints });
    }
  }

  return series;
}
