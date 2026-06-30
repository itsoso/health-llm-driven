import { useQuery } from '@tanstack/react-query';
import type { TrendSeries, TimeRange } from '../services/trends';
import { fetchWeightTrend, fetchBPTrend, fetchIndicatorTrend, fetchGarminMetricTrend } from '../services/trends';

const GARMIN_METRICS = new Set(['heart_rate', 'hrv', 'body_battery', 'sleep', 'sleep_score', 'steps']);
export function isGarminMetric(name: string) {
  return GARMIN_METRICS.has(name);
}

export function useWeightHistory(range: TimeRange) {
  return useQuery<TrendSeries[]>({
    queryKey: ['weightTrend', range],
    queryFn: () => fetchWeightTrend(range),
    staleTime: 120_000,
  });
}

export function useBPHistory(range: TimeRange) {
  return useQuery<TrendSeries[]>({
    queryKey: ['bpTrend', range],
    queryFn: () => fetchBPTrend(range),
    staleTime: 120_000,
  });
}

export function useIndicatorTrend(name: string, range: TimeRange) {
  return useQuery<TrendSeries[]>({
    queryKey: ['indicatorTrend', name, range],
    queryFn: () => fetchIndicatorTrend(name, range),
    staleTime: 300_000,
    enabled: !!name,
  });
}

export function useGarminMetricTrend(metric: string, range: TimeRange) {
  return useQuery<TrendSeries[]>({
    queryKey: ['garminMetricTrend', metric, range],
    queryFn: () => fetchGarminMetricTrend(metric, range),
    staleTime: 120_000,
    enabled: !!metric && GARMIN_METRICS.has(metric),
  });
}
