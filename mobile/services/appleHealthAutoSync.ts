import {
  getHealthKitAuthorized,
  getHealthKitLastSync,
  persistHealthKitLastSync,
  syncRecentDays,
  type SyncCoverage,
} from './appleHealth';

export const HEALTHKIT_FOREGROUND_SYNC_COOLDOWN_MS = 3 * 60 * 60 * 1000;

export type HealthKitAutoSyncResult =
  | { status: 'skipped'; reason: 'not_authorized' | 'cooldown' }
  | { status: 'synced'; imported: number; errors: string[]; coverage: SyncCoverage }
  | { status: 'failed'; error: string };

interface HealthKitForegroundAutoSyncOptions {
  days?: number;
  cooldownMs?: number;
  nowMs?: number;
}

let inflight: Promise<HealthKitAutoSyncResult> | null = null;

function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return String(error || 'HealthKit sync failed');
}

export function runHealthKitForegroundAutoSync(
  options: HealthKitForegroundAutoSyncOptions = {},
): Promise<HealthKitAutoSyncResult> {
  if (inflight) return inflight;

  inflight = (async () => {
    const now = options.nowMs ?? Date.now();
    const authorized = await getHealthKitAuthorized();
    if (!authorized) {
      return { status: 'skipped', reason: 'not_authorized' };
    }

    const previous = await getHealthKitLastSync();
    const cooldown = options.cooldownMs ?? HEALTHKIT_FOREGROUND_SYNC_COOLDOWN_MS;
    if (previous != null && now - previous < cooldown) {
      return { status: 'skipped', reason: 'cooldown' };
    }

    try {
      const result = await syncRecentDays(options.days ?? 2);
      await persistHealthKitLastSync(now);
      return {
        status: 'synced',
        imported: result.totalImported,
        errors: result.errors,
        coverage: result.coverage,
      };
    } catch (error) {
      return { status: 'failed', error: errorMessage(error) };
    }
  })();

  return inflight.finally(() => {
    inflight = null;
  });
}
