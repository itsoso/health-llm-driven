/** 今日议程 React Query 封装(消费 /agenda/today + 双轨完成 + 跳过)。 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getAgendaToday,
  getRuntimeAgendaRange,
  getSmartAgendaToday,
  completeAgendaItem,
  skipProtocol,
  seedDemo,
  type AgendaCompleteStatus,
  type AgendaSkipReason,
  type AgendaSource,
} from '../services/agenda';

const AGENDA_TODAY_KEY = ['agenda', 'today'];
const AGENDA_SMART_TODAY_KEY = ['agenda', 'today', 'smart'];
const AGENDA_RUNTIME_RANGE_KEY = ['agenda', 'range', 'runtime'];

export function useAgendaToday() {
  return useQuery({
    queryKey: AGENDA_TODAY_KEY,
    queryFn: getAgendaToday,
    staleTime: 60_000,
  });
}

export function useSmartAgendaToday(maxItems = 3) {
  return useQuery({
    queryKey: [...AGENDA_SMART_TODAY_KEY, maxItems],
    queryFn: () => getSmartAgendaToday(maxItems),
    staleTime: 60_000,
  });
}

export function useRuntimeAgendaRange(days = 7) {
  return useQuery({
    queryKey: [...AGENDA_RUNTIME_RANGE_KEY, days],
    queryFn: () => getRuntimeAgendaRange(days),
    staleTime: 60_000,
  });
}

export function useCompleteAgendaItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ source, track = 'protocol', value, status, skipReason }: {
      source: AgendaSource;
      track?: 'protocol' | 'manual';
      value?: Record<string, unknown>;
      status?: AgendaCompleteStatus;
      skipReason?: AgendaSkipReason;
    }) => completeAgendaItem(
      source,
      track,
      value,
      status || skipReason ? { status: status ?? 'done', skipReason } : undefined,
    ),
    onSuccess: () => Promise.all([
      qc.invalidateQueries({ queryKey: ['agenda'] }),
      qc.invalidateQueries({ queryKey: ['timeline', 'today'] }),
      qc.invalidateQueries({ queryKey: ['daily-artifact'] }),
      qc.invalidateQueries({ queryKey: ['today-dynamic-view'] }),
    ]),
  });
}

export function useSkipProtocol() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ protocolId, reason }: { protocolId: number; reason?: string }) =>
      skipProtocol(protocolId, reason),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['agenda'] }),
  });
}

export function useSeedDemo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: seedDemo,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['agenda'] }),
  });
}
