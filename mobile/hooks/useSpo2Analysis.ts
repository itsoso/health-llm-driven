// useSpo2Analysis — React Query hooks for sleep SpO2 nocturnal analysis (P1b)
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getNightAnalysis,
  reanalyzeNight,
  confirmNoAlcohol,
  getInsights,
  getNightlyTimeseries,
  SpO2NightAnalysis,
  SpO2Insights,
  NightlyTimeseriesResponse,
} from '../services/sleepSpo2';

export function useNightAnalysis(nightDate: string | null) {
  return useQuery<SpO2NightAnalysis>({
    queryKey: ['spo2-analysis', nightDate],
    queryFn: () => getNightAnalysis(nightDate as string),
    enabled: !!nightDate,
    staleTime: 5 * 60 * 1000, // 5min cache
  });
}

export function useNightTimeseries(date: string | null, metrics?: string) {
  return useQuery<NightlyTimeseriesResponse>({
    queryKey: ['night-timeseries', date, metrics],
    queryFn: () => getNightlyTimeseries(date as string, metrics),
    enabled: !!date,
    staleTime: 5 * 60 * 1000,
  });
}

export function useSpo2Insights(weeks = 4) {
  return useQuery<SpO2Insights>({
    queryKey: ['spo2-insights', weeks],
    queryFn: () => getInsights(weeks),
    staleTime: 30 * 60 * 1000, // 30min cache
  });
}

export function useReanalyzeNight() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (nightDate: string) => reanalyzeNight(nightDate),
    onSuccess: (_data, nightDate) => {
      qc.invalidateQueries({ queryKey: ['spo2-analysis', nightDate] });
      qc.invalidateQueries({ queryKey: ['spo2-insights'] });
    },
  });
}

export function useConfirmNoAlcohol() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (nightDate: string) => confirmNoAlcohol(nightDate),
    onSuccess: (_data, nightDate) => {
      qc.invalidateQueries({ queryKey: ['spo2-analysis', nightDate] });
    },
  });
}
