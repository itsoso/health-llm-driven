import { useQuery } from '@tanstack/react-query';
import { getSleepRecords, getSleepStats, getSleepDebt, type SleepRecord, type SleepStats, type SleepDebt } from '@/services/sleep';

export function useSleepRecords(limit = 14) {
  return useQuery<SleepRecord[]>({
    queryKey: ['sleepRecords', limit],
    queryFn: () => getSleepRecords(limit),
    staleTime: 120_000,
  });
}

export function useSleepStats(days = 7) {
  return useQuery<SleepStats>({
    queryKey: ['sleepStats', days],
    queryFn: () => getSleepStats(days),
    staleTime: 120_000,
  });
}

export function useSleepDebt(days = 14) {
  return useQuery<SleepDebt>({
    queryKey: ['sleepDebt', days],
    queryFn: () => getSleepDebt(days),
    staleTime: 300_000,
  });
}
