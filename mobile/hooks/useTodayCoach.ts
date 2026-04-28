import { useQuery } from '@tanstack/react-query';
import { getTodayCoachFocus } from '../services/todayCoach';
import { queryKeys } from '../lib/queryKeys';

function today(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export function useTodayCoach() {
  const date = today();
  return useQuery({
    queryKey: [...queryKeys.todayCoachRoot, date],
    queryFn: () => getTodayCoachFocus(date),
    staleTime: 120_000,
  });
}
