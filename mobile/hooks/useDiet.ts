import { useQuery } from '@tanstack/react-query';
import { getDailyDiet, getDietStats, type DailyDietSummary, type DietStats } from '@/services/diet';

function todayStr(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export function useDailyDiet(date?: string) {
  const d = date || todayStr();
  return useQuery<DailyDietSummary>({
    queryKey: ['diet', d],
    queryFn: () => getDailyDiet(d),
    staleTime: 60_000,
  });
}

export function useDietStats(days = 7) {
  return useQuery<DietStats>({
    queryKey: ['dietStats', days],
    queryFn: () => getDietStats(days),
    staleTime: 120_000,
  });
}
