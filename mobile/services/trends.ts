import api from './api';

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
    start: start.toISOString().slice(0, 10),
    end: end.toISOString().slice(0, 10),
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
