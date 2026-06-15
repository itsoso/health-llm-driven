/** 今日议程 React Query 封装(消费 /agenda/today + 双轨完成 + 跳过)。 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getAgendaToday, completeAgendaItem, skipProtocol, seedDemo, type AgendaSource,
} from '../services/agenda';

const AGENDA_TODAY_KEY = ['agenda', 'today'];

export function useAgendaToday() {
  return useQuery({
    queryKey: AGENDA_TODAY_KEY,
    queryFn: getAgendaToday,
    staleTime: 60_000,
  });
}

export function useCompleteAgendaItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (source: AgendaSource) => completeAgendaItem(source),
    onSuccess: () => qc.invalidateQueries({ queryKey: AGENDA_TODAY_KEY }),
  });
}

export function useSkipProtocol() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ protocolId, reason }: { protocolId: number; reason?: string }) =>
      skipProtocol(protocolId, reason),
    onSuccess: () => qc.invalidateQueries({ queryKey: AGENDA_TODAY_KEY }),
  });
}

export function useSeedDemo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: seedDemo,
    onSuccess: () => qc.invalidateQueries({ queryKey: AGENDA_TODAY_KEY }),
  });
}
