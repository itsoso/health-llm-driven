import { useEffect, useRef } from 'react';
import { AppState } from 'react-native';
import { useQueryClient } from '@tanstack/react-query';
import { invalidateHealthSnapshot } from '../applib/queryKeys';
import { maybeSyncHealthKitOnForeground } from '../services/healthKitForegroundSync';

export function useHealthKitForegroundSync(enabled: boolean) {
  const queryClient = useQueryClient();
  const mountedRef = useRef(false);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    if (!enabled) return;

    const run = async () => {
      const result = await maybeSyncHealthKitOnForeground();
      if (!mountedRef.current || result.status !== 'synced') return;
      await invalidateHealthSnapshot(queryClient);
      if (__DEV__) {
        // eslint-disable-next-line no-console
        console.log('[HealthKit] foreground sync complete', {
          imported: result.totalImported,
          coverage: result.coverage,
        });
      }
    };

    run();
    const sub = AppState.addEventListener('change', (status) => {
      if (status === 'active') {
        run();
      }
    });
    return () => sub.remove();
  }, [enabled, queryClient]);
}
