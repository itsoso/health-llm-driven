/** In-memory health query cache, scoped to the current authenticated session. */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { QueryClient } from '@tanstack/react-query';
import { subscribeAuthSessionChange } from '../services/api';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 2, staleTime: 60_000, gcTime: 24 * 60 * 60 * 1000 },
  },
});

subscribeAuthSessionChange(() => {
  // clear() alone leaves the last successful result in mounted observers.
  for (const query of queryClient.getQueryCache().getAll()) {
    void query.cancel({ revert: false, silent: true });
    query.setState({ data: undefined, error: null, dataUpdatedAt: 0,
      errorUpdatedAt: 0, status: 'pending', fetchStatus: 'idle' });
  }
  queryClient.clear();
});

export async function retireLegacyQueryCache(): Promise<void> {
  // The global plaintext cache cannot attest its owner. Never hydrate it;
  // remove only this derived cache, preserving drafts and stored records.
  await AsyncStorage.removeItem('HEALTHPILOT_RQ_CACHE_V1');
}
