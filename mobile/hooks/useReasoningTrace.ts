import { useQuery } from '@tanstack/react-query';
import {
  listRecentTraces, getTraceDetail,
  type TraceListResponse, type ReasoningTrace,
} from '../services/reasoningTrace';

export function useRecentTraces(params?: {
  days?: number;
  limit?: number;
  decision_type?: string;
  include_suppressed?: boolean;
}) {
  const key = ['reasoningTrace', 'recent', params ?? {}] as const;
  return useQuery<TraceListResponse>({
    queryKey: key,
    queryFn: () => listRecentTraces(params),
    staleTime: 60_000,
  });
}

export function useTraceDetail(traceId: string | null) {
  return useQuery<ReasoningTrace>({
    queryKey: ['reasoningTrace', 'detail', traceId],
    queryFn: () => getTraceDetail(traceId as string),
    enabled: !!traceId,
    staleTime: 60_000,
  });
}
