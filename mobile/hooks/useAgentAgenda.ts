import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '../lib/queryKeys';
import { getAgentAgenda } from '../services/agentAgenda';

function today(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export function useAgentAgenda() {
  const date = today();
  return useQuery({
    queryKey: [...queryKeys.agentAgendaRoot, date],
    queryFn: () => getAgentAgenda(date),
    staleTime: 120_000,
  });
}
