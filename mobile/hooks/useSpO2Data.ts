import { useQuery } from '@tanstack/react-query';
import { getSpO2Nightly, getSpO2LatestNight, type SpO2NightlyData } from '../services/spo2';

export function useSpO2Nightly(date: string | null) {
  return useQuery<SpO2NightlyData>({
    queryKey: ['spo2Nightly', date],
    queryFn: () => getSpO2Nightly(date!),
    staleTime: 120_000,
    enabled: !!date,
  });
}

export function useSpO2LatestNight() {
  return useQuery<SpO2NightlyData | null>({
    queryKey: ['spo2LatestNight'],
    queryFn: getSpO2LatestNight,
    staleTime: 120_000,
  });
}
