/**
 * useSpecialistScorecard + useSpecialistHitRate
 *
 * Task 7: React Query wrappers for
 * - GET /specialists/{name}/scorecard  (详情页)
 * - GET /specialists/hit-rate          (Home chip row)
 */
import { useQuery } from '@tanstack/react-query';
import {
  fetchScorecard,
  fetchHitRate,
  type ScorecardResponse,
  type HitRateResponse,
} from '../services/specialistScorecard';

export function useSpecialistScorecard(name: string | null | undefined, days = 30) {
  return useQuery<ScorecardResponse>({
    queryKey: ['specialist-scorecard', name, days],
    queryFn: () => fetchScorecard(name as string, days),
    enabled: Boolean(name),
    staleTime: 60_000,
  });
}

export function useSpecialistHitRate(days = 30) {
  return useQuery<HitRateResponse>({
    queryKey: ['specialist-hit-rate', days],
    queryFn: () => fetchHitRate(days),
    staleTime: 5 * 60_000, // 5min — 聚合数据, 不需要实时
  });
}
