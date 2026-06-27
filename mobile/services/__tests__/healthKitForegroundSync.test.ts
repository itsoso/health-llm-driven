import {
  DEFAULT_HEALTHKIT_FOREGROUND_SYNC_COOLDOWN_MS,
  DEFAULT_HEALTHKIT_FOREGROUND_SYNC_DAYS,
  maybeSyncHealthKitOnForeground,
  resetHealthKitForegroundSyncForTests,
  type HealthKitForegroundSyncDeps,
} from '../healthKitForegroundSync';

function makeDeps(overrides: Partial<HealthKitForegroundSyncDeps> = {}): jest.Mocked<HealthKitForegroundSyncDeps> {
  return {
    isHealthKitAvailable: jest.fn(() => true),
    getHealthKitAuthorized: jest.fn(async () => true),
    getHealthKitLastSync: jest.fn(async () => null),
    persistHealthKitAuthorized: jest.fn(async () => undefined),
    persistHealthKitLastSync: jest.fn(async () => undefined),
    syncRecentDays: jest.fn(async () => ({
      totalImported: 2,
      errors: [],
      coverage: {
        days: 2,
        steps: 2,
        hr: 1,
        hrv: 1,
        spo2: 0,
        sleep: 1,
        unknownSources: [],
      },
    })),
    now: jest.fn(() => 1_000_000),
    ...overrides,
  } as jest.Mocked<HealthKitForegroundSyncDeps>;
}

describe('maybeSyncHealthKitOnForeground', () => {
  beforeEach(() => {
    resetHealthKitForegroundSyncForTests();
    jest.clearAllMocks();
  });

  it('syncs recent 2 days when HealthKit is authorized and cooldown expired', async () => {
    const deps = makeDeps();

    const result = await maybeSyncHealthKitOnForeground({ deps });

    expect(result.status).toBe('synced');
    expect(deps.syncRecentDays).toHaveBeenCalledWith(DEFAULT_HEALTHKIT_FOREGROUND_SYNC_DAYS);
    expect(deps.persistHealthKitLastSync).toHaveBeenCalledWith(1_000_000);
    expect(deps.persistHealthKitAuthorized).toHaveBeenCalled();
  });

  it('skips silently when HealthKit is unavailable or not authorized', async () => {
    const unavailable = makeDeps({ isHealthKitAvailable: jest.fn(() => false) });
    await expect(maybeSyncHealthKitOnForeground({ deps: unavailable })).resolves.toMatchObject({
      status: 'skipped_unavailable',
    });
    expect(unavailable.syncRecentDays).not.toHaveBeenCalled();

    resetHealthKitForegroundSyncForTests();
    const unauthorized = makeDeps({ getHealthKitAuthorized: jest.fn(async () => false) });
    await expect(maybeSyncHealthKitOnForeground({ deps: unauthorized })).resolves.toMatchObject({
      status: 'skipped_unauthorized',
    });
    expect(unauthorized.syncRecentDays).not.toHaveBeenCalled();
  });

  it('uses the persisted last sync timestamp as a cooldown gate', async () => {
    const deps = makeDeps({
      getHealthKitLastSync: jest.fn(async () => 1_000_000 - DEFAULT_HEALTHKIT_FOREGROUND_SYNC_COOLDOWN_MS + 1),
    });

    const result = await maybeSyncHealthKitOnForeground({ deps });

    expect(result.status).toBe('skipped_cooldown');
    expect(deps.syncRecentDays).not.toHaveBeenCalled();
  });

  it('deduplicates overlapping foreground events', async () => {
    let resolveSync!: () => void;
    const syncPromise = new Promise<void>((resolve) => { resolveSync = resolve; });
    const deps = makeDeps({
      syncRecentDays: jest.fn(async () => {
        await syncPromise;
        return {
          totalImported: 1,
          errors: [],
          coverage: { days: 1, steps: 1, hr: 0, hrv: 0, spo2: 0, sleep: 0, unknownSources: [] },
        };
      }),
    });

    const first = maybeSyncHealthKitOnForeground({ deps });
    const second = await maybeSyncHealthKitOnForeground({ deps });
    resolveSync();
    const firstResult = await first;

    expect(second.status).toBe('skipped_in_flight');
    expect(firstResult.status).toBe('synced');
    expect(deps.syncRecentDays).toHaveBeenCalledTimes(1);
  });

  it('returns failed without throwing or moving last sync when sync fails', async () => {
    const deps = makeDeps({
      syncRecentDays: jest.fn(async () => {
        throw new Error('network down');
      }),
    });

    const result = await maybeSyncHealthKitOnForeground({ deps });

    expect(result.status).toBe('failed');
    expect(result.error).toBe('network down');
    expect(deps.persistHealthKitLastSync).not.toHaveBeenCalled();
  });
});
