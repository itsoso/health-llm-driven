/**
 * System Knowledge claim hooks — used by ClaimSheet and any future surface
 * that wants to render a claim by id.
 *
 * Single claim: useKnowledgeClaim(claimId, { enabled })
 * Multiple claims: useKnowledgeClaims(claimIds, { enabled }) — wraps useQueries
 *                  so each claim has its own cache entry and loading state.
 *
 * staleTime 10min — system KB claims change rarely (lifecycle weekly).
 */
import { useQueries, useQuery } from '@tanstack/react-query';
import {
  getKnowledgeClaim,
  type KnowledgeClaimBundle,
} from '../services/systemKnowledge';

const STALE_TIME = 10 * 60 * 1000;

export function useKnowledgeClaim(claimId: string | null | undefined, opts?: { enabled?: boolean }) {
  return useQuery<KnowledgeClaimBundle>({
    queryKey: ['knowledge-claim', claimId],
    queryFn: () => getKnowledgeClaim(claimId as string),
    enabled: !!claimId && opts?.enabled !== false,
    staleTime: STALE_TIME,
    retry: 1,
  });
}

export function useKnowledgeClaims(
  claimIds: string[],
  opts?: { enabled?: boolean },
) {
  const enabled = opts?.enabled !== false && claimIds.length > 0;
  const results = useQueries({
    queries: claimIds.map((id) => ({
      queryKey: ['knowledge-claim', id],
      queryFn: () => getKnowledgeClaim(id),
      enabled,
      staleTime: STALE_TIME,
      retry: 1,
    })),
  });

  const bundles: KnowledgeClaimBundle[] = [];
  const errors: { claimId: string; error: unknown }[] = [];
  let isLoading = false;

  for (let i = 0; i < results.length; i++) {
    const r = results[i];
    if (r.isLoading) isLoading = true;
    if (r.data) bundles.push(r.data);
    if (r.error) errors.push({ claimId: claimIds[i], error: r.error });
  }

  return { bundles, errors, isLoading };
}
