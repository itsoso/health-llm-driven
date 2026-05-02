/**
 * Task 3: ExplainSheet 的 React Query hook.
 *
 * 按 source + auditId + ruleId/specialist 唯一化缓存 key.
 * staleTime 5min — reasoning trace 在同一次 evaluate 内不变.
 */
import { useQuery } from '@tanstack/react-query';
import {
  explainSafety,
  explainSpecialist,
  type ExplainResponse,
} from '../services/reasoningTrace';

type Args =
  | { source: 'safety'; auditId: number; ruleId: string; enabled?: boolean }
  | { source: 'specialist'; auditId: number; specialist: string; enabled?: boolean };

export function useReasoningExplain(args: Args) {
  return useQuery<ExplainResponse>({
    queryKey: [
      'reasoning-explain',
      args.source,
      args.auditId,
      args.source === 'safety' ? args.ruleId : args.specialist,
    ],
    queryFn: () =>
      args.source === 'safety'
        ? explainSafety(args.auditId, args.ruleId)
        : explainSpecialist(args.auditId, args.specialist),
    enabled: args.enabled !== false,
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });
}
