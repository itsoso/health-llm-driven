import { useQuery } from '@tanstack/react-query';
import { getGarminSleepData, computeSleepStats, getSleepDebt, type GarminSleepDay, type SleepStats, type SleepDebt } from '@/services/sleep';

export function useSleepStats(days = 7) {
  return useQuery<SleepStats>({
    queryKey: ['sleepStats', days],
    queryFn: async () => {
      const garminData = await getGarminSleepData(days);
      return computeSleepStats(garminData);
    },
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
