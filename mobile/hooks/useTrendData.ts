import { useQuery } from '@tanstack/react-query';
import type { TrendSeries, TimeRange } from '@/services/trends';
import { fetchWeightTrend, fetchBPTrend, fetchIndicatorTrend } from '@/services/trends';

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
