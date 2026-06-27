jest.mock('../appleHealthAutoSync', () => ({
  runHealthKitForegroundAutoSync: jest.fn(),
}));

import { runHealthKitForegroundAutoSync } from '../appleHealthAutoSync';
import {
  HEALTHKIT_FOREGROUND_INVALIDATION_KEYS,
  runHealthKitForegroundRefresh,
} from '../healthKitForegroundRefresh';

const autoSync = runHealthKitForegroundAutoSync as jest.MockedFunction<typeof runHealthKitForegroundAutoSync>;

describe('runHealthKitForegroundRefresh', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  function queryClient() {
    return {
      invalidateQueries: jest.fn().mockResolvedValue(undefined),
    };
  }

  it('invalidates runtime queries after a successful foreground sync', async () => {
    const qc = queryClient();
    autoSync.mockResolvedValue({
      status: 'synced',
      imported: 4,
      errors: [],
      coverage: { days: 2, steps: 2, hr: 2, hrv: 2, spo2: 1, sleep: 1, unknownSources: [] },
    });

    const result = await runHealthKitForegroundRefresh(qc);

    expect(autoSync).toHaveBeenCalledWith({ days: 2 });
    expect(result.status).toBe('synced');
    expect(qc.invalidateQueries).toHaveBeenCalledTimes(HEALTHKIT_FOREGROUND_INVALIDATION_KEYS.length);
    for (const queryKey of HEALTHKIT_FOREGROUND_INVALIDATION_KEYS) {
      expect(qc.invalidateQueries).toHaveBeenCalledWith({ queryKey });
    }
  });

  it('does not invalidate runtime queries when sync is skipped or failed', async () => {
    const qc = queryClient();
    autoSync.mockResolvedValue({ status: 'skipped', reason: 'cooldown' });

    await expect(runHealthKitForegroundRefresh(qc)).resolves.toEqual({ status: 'skipped', reason: 'cooldown' });

    expect(qc.invalidateQueries).not.toHaveBeenCalled();
  });
});
