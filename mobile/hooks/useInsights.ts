import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  getTodayInsight, listRecentInsights, submitInsightFeedback,
  type DailyInsight, type InsightFeedback,
} from '../services/insights';

const KEY_TODAY = ['insights', 'today'] as const;
const KEY_RECENT = (days: number) => ['insights', 'recent', days] as const;

export function useTodayInsight() {
  return useQuery<DailyInsight | null>({
    queryKey: KEY_TODAY,
    queryFn: getTodayInsight,
    staleTime: 5 * 60_000,
  });
}

export function useRecentInsights(days: number = 14) {
  return useQuery<DailyInsight[]>({
    queryKey: KEY_RECENT(days),
    queryFn: () => listRecentInsights(days),
    staleTime: 2 * 60_000,
  });
}

export function useInsightFeedback() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, feedback, note }: { id: number; feedback: InsightFeedback; note?: string }) =>
      submitInsightFeedback(id, feedback, note),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['insights'] });
    },
  });
}
