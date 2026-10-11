import { useQuery } from '@tanstack/react-query';
import { useSyncExternalStore } from 'react';
import { useAuth } from './useAuth';
import { aiConsentRevision, hasAIConsentIdentity, subscribeAIConsentInvalidation } from '../services/aiConsentState';
import { getDailyDiet, getDietStats, getFrequentFoods, type DietReadSession } from '../services/diet';

function useDietReadSession(): DietReadSession | null {
  const { user, token, isLoading } = useAuth();
  const revision = useSyncExternalStore(subscribeAIConsentInvalidation, aiConsentRevision, aiConsentRevision);
  return !isLoading && token && user && hasAIConsentIdentity() ? { owner: user.id, revision } : null;
}

function requireSession(session: DietReadSession | null): DietReadSession {
  if (!session) throw new Error('auth_session_changed');
  return session;
}

function todayStr(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export function useDailyDiet(date?: string) {
  const d = date || todayStr();
  const session = useDietReadSession();
  return useQuery({
    queryKey: ['diet', 'owner', session?.owner, session?.revision, d],
    queryFn: () => getDailyDiet(d, requireSession(session)),
    enabled: Boolean(session),
    meta: { persist: false },
    gcTime: 0,
    staleTime: 60_000,
  });
}

export function useDietStats(days = 7) {
  const session = useDietReadSession();
  return useQuery({
    queryKey: ['dietStats', 'owner', session?.owner, session?.revision, days],
    queryFn: () => getDietStats(days, requireSession(session)),
    enabled: Boolean(session),
    meta: { persist: false },
    gcTime: 0,
    staleTime: 120_000,
  });
}

export function useFrequentDietFoods(limit = 8, days = 30) {
  const session = useDietReadSession();
  return useQuery({
    queryKey: ['diet', 'owner', session?.owner, session?.revision, 'frequent', limit, days],
    queryFn: () => getFrequentFoods(limit, days, requireSession(session)),
    enabled: Boolean(session),
    meta: { persist: false },
    gcTime: 0,
    staleTime: 10 * 60 * 1000,
  });
}
