import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { buildDataPrompts, fetchDataHealthStatus } from '../services/dataHealth';
import { queryKeys } from '../lib/queryKeys';

export function useDataHealth() {
  const query = useQuery({
    queryKey: queryKeys.dataHealth,
    queryFn: fetchDataHealthStatus,
    staleTime: 120_000,
  });

  const prompts = useMemo(() => buildDataPrompts(query.data), [query.data]);

  return { ...query, prompts };
}
