import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { useCallback, useSyncExternalStore } from 'react';
import { useAuth } from './useAuth';
import { aiConsentRevision, hasAIConsentIdentity, subscribeAIConsentInvalidation } from '../services/aiConsentState';
import { getAuthSessionSnapshot, subscribeAuthSessionChange } from '../services/api';
import { fetchMyProgress, type ProgressDashboard } from '../services/myProgress';
import { fetchHealthOperatingReview, type HealthOperatingReview, type ReviewWindowDays } from '../services/healthOperatingReview';
import { assertProgressReadSession, isProgressReadSessionCurrent, type ProgressReadSession } from '../services/progressReadSession';

function authGeneration(): number {
  return getAuthSessionSnapshot().generation;
}

function requireSession(session: ProgressReadSession | null): ProgressReadSession {
  if (!session) throw new Error('auth_session_changed');
  assertProgressReadSession(session);
  return session;
}

export interface MyProgressQueryResult {
  progress: UseQueryResult<ProgressDashboard, Error>;
  review: UseQueryResult<HealthOperatingReview, Error>;
  canRead: boolean;
  refresh: () => Promise<void>;
  refreshing: boolean;
}

export function useMyProgress(days: ReviewWindowDays): MyProgressQueryResult {
  const { user, token, isLoading } = useAuth();
  const revision = useSyncExternalStore(subscribeAIConsentInvalidation, aiConsentRevision, aiConsentRevision);
  const generation = useSyncExternalStore(subscribeAuthSessionChange, authGeneration, authGeneration);
  const transport = getAuthSessionSnapshot();
  const canRead = Boolean(
    !isLoading && token && user && Number.isSafeInteger(user.id) && user.id > 0 &&
    transport.initialized && transport.token === token && hasAIConsentIdentity(),
  );
  const session: ProgressReadSession | null = canRead && user ? { owner: user.id, revision, generation } : null;
  const progress = useQuery({
    queryKey: ['my-progress', 'owner', session?.owner, session?.revision, session?.generation, days],
    queryFn: () => fetchMyProgress(days, requireSession(session)),
    enabled: canRead,
    meta: { persist: false },
    gcTime: 0,
    staleTime: 120_000,
  });
  const review = useQuery({
    queryKey: ['daily-plan-review', 'owner', session?.owner, session?.revision, session?.generation, days],
    queryFn: () => fetchHealthOperatingReview(days, requireSession(session)),
    enabled: canRead,
    meta: { persist: false },
    gcTime: 0,
    staleTime: 120_000,
  });
  const { refetch: refetchProgress } = progress;
  const { refetch: refetchReview } = review;
  const refresh = useCallback(async (): Promise<void> => {
    if (!session || !isProgressReadSessionCurrent(session)) return;
    await Promise.all([refetchProgress(), refetchReview()]);
  }, [session, refetchProgress, refetchReview]);

  return { progress, review, canRead, refresh, refreshing: progress.isRefetching || review.isRefetching };
}
