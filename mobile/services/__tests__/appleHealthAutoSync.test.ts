jest.mock('../appleHealth', () => ({
  getHealthKitAuthorized: jest.fn(),
  getHealthKitLastSync: jest.fn(),
  persistHealthKitLastSync: jest.fn(),
  syncRecentDays: jest.fn(),
}));

import {
  getHealthKitAuthorized,
  getHealthKitLastSync,
  persistHealthKitLastSync,
  syncRecentDays,
} from '../appleHealth';
import {
  HEALTHKIT_FOREGROUND_SYNC_COOLDOWN_MS,
  runHealthKitForegroundAutoSync,
} from '../appleHealthAutoSync';

const authorized = getHealthKitAuthorized as jest.MockedFunction<typeof getHealthKitAuthorized>;
const lastSync = getHealthKitLastSync as jest.MockedFunction<typeof getHealthKitLastSync>;
const persistLastSync = persistHealthKitLastSync as jest.MockedFunction<typeof persistHealthKitLastSync>;
const sync = syncRecentDays as jest.MockedFunction<typeof syncRecentDays>;

describe('runHealthKitForegroundAutoSync', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.spyOn(Date, 'now').mockReturnValue(1_800_000_000_000);
    sync.mockResolvedValue({
      totalImported: 3,
      errors: [],
      coverage: { days: 2, steps: 2, hr: 1, hrv: 1, spo2: 0, sleep: 1, unknownSources: [] },
    });
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('skips without touching HealthKit when the user has not authorized it', async () => {
    authorized.mockResolvedValue(false);

    const result = await runHealthKitForegroundAutoSync();

    expect(result).toEqual({ status: 'skipped', reason: 'not_authorized' });
    expect(lastSync).not.toHaveBeenCalled();
    expect(sync).not.toHaveBeenCalled();
    expect(persistLastSync).not.toHaveBeenCalled();
  });

  it('skips inside the foreground cooldown window', async () => {
    authorized.mockResolvedValue(true);
    lastSync.mockResolvedValue(Date.now() - HEALTHKIT_FOREGROUND_SYNC_COOLDOWN_MS + 1_000);

    const result = await runHealthKitForegroundAutoSync({ days: 2 });

    expect(result).toEqual({ status: 'skipped', reason: 'cooldown' });
    expect(sync).not.toHaveBeenCalled();
    expect(persistLastSync).not.toHaveBeenCalled();
  });

  it('syncs recent days and persists last-sync timestamp after success', async () => {
    authorized.mockResolvedValue(true);
    lastSync.mockResolvedValue(Date.now() - HEALTHKIT_FOREGROUND_SYNC_COOLDOWN_MS - 1_000);

    const result = await runHealthKitForegroundAutoSync({ days: 2 });

    expect(sync).toHaveBeenCalledWith(2);
    expect(persistLastSync).toHaveBeenCalledWith(Date.now());
    expect(result).toEqual({
      status: 'synced',
      imported: 3,
      errors: [],
      coverage: { days: 2, steps: 2, hr: 1, hrv: 1, spo2: 0, sleep: 1, unknownSources: [] },
    });
  });

  it('shares an in-flight foreground sync instead of starting a duplicate import', async () => {
    authorized.mockResolvedValue(true);
    lastSync.mockResolvedValue(null);
    let resolveSync: (value: Awaited<ReturnType<typeof syncRecentDays>>) => void = () => {};
    sync.mockImplementation(() => new Promise((resolve) => { resolveSync = resolve; }));

    const first = runHealthKitForegroundAutoSync({ days: 2 });
    const second = runHealthKitForegroundAutoSync({ days: 2 });
    await Promise.resolve();
    await Promise.resolve();
    expect(sync).toHaveBeenCalledTimes(1);
    resolveSync({
      totalImported: 1,
      errors: [],
      coverage: { days: 1, steps: 1, hr: 0, hrv: 0, spo2: 0, sleep: 0, unknownSources: [] },
    });

    const results = await Promise.all([first, second]);

    expect(sync).toHaveBeenCalledTimes(1);
    expect(results[0]).toEqual(results[1]);
    expect(results[0].status).toBe('synced');
  });

  it('returns failed without throwing when foreground sync errors', async () => {
    authorized.mockResolvedValue(true);
    lastSync.mockResolvedValue(null);
    sync.mockRejectedValue(new Error('native unavailable'));

    const result = await runHealthKitForegroundAutoSync({ days: 2 });

    expect(result).toEqual({ status: 'failed', error: 'native unavailable' });
    expect(persistLastSync).not.toHaveBeenCalled();
  });
});
