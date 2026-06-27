import {
  getHealthKitAuthorized,
  getHealthKitLastSync,
  isHealthKitAvailable,
  persistHealthKitAuthorized,
  persistHealthKitLastSync,
  syncRecentDays,
  type SyncCoverage,
} from './appleHealth';

export const DEFAULT_HEALTHKIT_FOREGROUND_SYNC_DAYS = 2;
export const DEFAULT_HEALTHKIT_FOREGROUND_SYNC_COOLDOWN_MS = 30 * 60 * 1000;

export type HealthKitForegroundSyncStatus =
  | 'synced'
  | 'skipped_unavailable'
  | 'skipped_unauthorized'
  | 'skipped_cooldown'
  | 'skipped_in_flight'
  | 'failed';

export interface HealthKitForegroundSyncResult {
  status: HealthKitForegroundSyncStatus;
  totalImported?: number;
  errors?: string[];
  coverage?: SyncCoverage;
  error?: string;
}

export interface HealthKitForegroundSyncDeps {
  isHealthKitAvailable: () => boolean;
  getHealthKitAuthorized: () => Promise<boolean>;
  getHealthKitLastSync: () => Promise<number | null>;
  persistHealthKitAuthorized: () => Promise<void>;
  persistHealthKitLastSync: (ts: number) => Promise<void>;
  syncRecentDays: (days: number) => Promise<{
    totalImported: number;
    errors: string[];
    coverage: SyncCoverage;
  }>;
  now: () => number;
}

export interface HealthKitForegroundSyncOptions {
  days?: number;
  cooldownMs?: number;
  deps?: HealthKitForegroundSyncDeps;
}

const defaultDeps: HealthKitForegroundSyncDeps = {
  isHealthKitAvailable,
  getHealthKitAuthorized,
  getHealthKitLastSync,
  persistHealthKitAuthorized,
  persistHealthKitLastSync,
  syncRecentDays,
  now: () => Date.now(),
};

let foregroundSyncInFlight = false;

export async function maybeSyncHealthKitOnForeground(
  options: HealthKitForegroundSyncOptions = {},
): Promise<HealthKitForegroundSyncResult> {
  const deps = options.deps ?? defaultDeps;
  const days = options.days ?? DEFAULT_HEALTHKIT_FOREGROUND_SYNC_DAYS;
  const cooldownMs = options.cooldownMs ?? DEFAULT_HEALTHKIT_FOREGROUND_SYNC_COOLDOWN_MS;

  if (!deps.isHealthKitAvailable()) {
    return { status: 'skipped_unavailable' };
  }
  if (foregroundSyncInFlight) {
    return { status: 'skipped_in_flight' };
  }

  foregroundSyncInFlight = true;
  try {
    const authorized = await deps.getHealthKitAuthorized();
    if (!authorized) {
      return { status: 'skipped_unauthorized' };
    }

    const now = deps.now();
    const lastSync = await deps.getHealthKitLastSync();
    if (Number.isFinite(lastSync) && lastSync !== null && now - lastSync < cooldownMs) {
      return { status: 'skipped_cooldown' };
    }

    const result = await deps.syncRecentDays(days);
    const finishedAt = deps.now();
    await deps.persistHealthKitAuthorized();
    await deps.persistHealthKitLastSync(finishedAt);
    return {
      status: 'synced',
      totalImported: result.totalImported,
      errors: result.errors,
      coverage: result.coverage,
    };
  } catch (e: any) {
    return {
      status: 'failed',
      error: e?.message ?? String(e),
    };
  } finally {
    foregroundSyncInFlight = false;
  }
}

export function resetHealthKitForegroundSyncForTests(): void {
  foregroundSyncInFlight = false;
}
