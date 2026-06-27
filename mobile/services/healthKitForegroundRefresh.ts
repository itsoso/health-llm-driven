import type { QueryClient } from '@tanstack/react-query';

import {
  runHealthKitForegroundAutoSync,
  type HealthKitAutoSyncResult,
} from './appleHealthAutoSync';

export const HEALTHKIT_FOREGROUND_INVALIDATION_KEYS = [
  ['healthkit', 'lastSync'],
  ['dashboard'],
  ['twin', 'me'],
  ['timeline', 'today'],
  ['agenda', 'today'],
] as const;

type QueryInvalidator = Pick<QueryClient, 'invalidateQueries'>;

export async function runHealthKitForegroundRefresh(
  queryClient: QueryInvalidator,
): Promise<HealthKitAutoSyncResult> {
  const result = await runHealthKitForegroundAutoSync({ days: 2 });
  if (result.status !== 'synced') return result;

  await Promise.all(
    HEALTHKIT_FOREGROUND_INVALIDATION_KEYS.map((queryKey) => (
      queryClient.invalidateQueries({ queryKey })
    )),
  );
  return result;
}
