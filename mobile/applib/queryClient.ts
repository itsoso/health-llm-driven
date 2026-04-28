/**
 * React Query client + AsyncStorage persister.
 *
 * Why persist:
 *   Cold-start UX was "6 cards all spinning" because every query rebuilt
 *   from scratch. Persisting the cache means the user sees yesterday's
 *   dashboard immediately, then a background refetch updates it.
 *
 * Cache lifetime:
 *   - gcTime 24h: keep hydrated queries in memory for a full day of use
 *   - maxAge 24h: discard disk cache older than 24h (don't show stale
 *     health readings for days)
 *   - buster = app version: bumping the version (schema changes) wipes
 *     all persisted caches automatically
 *
 * Only *successful* queries are persisted; errors and pending states
 * are never written to disk, so a transient outage can't poison the cache.
 */

import AsyncStorage from '@react-native-async-storage/async-storage';
import { QueryClient } from '@tanstack/react-query';
import { createAsyncStoragePersister } from '@tanstack/query-async-storage-persister';
import Constants from 'expo-constants';

const APP_VERSION =
  (Constants.expoConfig?.version as string | undefined) || '0.0.0';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 2,
      staleTime: 60_000,
      gcTime: 24 * 60 * 60 * 1000,
    },
  },
});

export const asyncStoragePersister = createAsyncStoragePersister({
  storage: AsyncStorage,
  key: 'HEALTHPILOT_RQ_CACHE_V1',
  throttleTime: 1_000,
});

export const persistOptions = {
  persister: asyncStoragePersister,
  maxAge: 24 * 60 * 60 * 1000,
  buster: APP_VERSION,
  dehydrateOptions: {
    shouldDehydrateQuery: (q: { state: { status: string } }) =>
      q.state.status === 'success',
  },
} as const;
