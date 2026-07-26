import {
  applyDownloadedUpdate,
  downloadAvailableUpdate,
  getNativeVersionLabel,
  type AppUpdateAdapter,
  type AppUpdatePhase,
} from '../appUpdate';

function createAdapter(overrides: Partial<AppUpdateAdapter> = {}): AppUpdateAdapter {
  return {
    isEnabled: true,
    checkForUpdateAsync: jest.fn().mockResolvedValue({ isAvailable: false }),
    fetchUpdateAsync: jest.fn().mockResolvedValue({ isNew: true }),
    reloadAsync: jest.fn().mockResolvedValue(undefined),
    ...overrides,
  };
}

describe('appUpdate', () => {
  it('does not contact the update service when updates are disabled', async () => {
    const adapter = createAdapter({ isEnabled: false });

    await expect(downloadAvailableUpdate(adapter)).resolves.toBe('disabled');
    expect(adapter.checkForUpdateAsync).not.toHaveBeenCalled();
    expect(adapter.fetchUpdateAsync).not.toHaveBeenCalled();
  });

  it('reports current without downloading when no update is available', async () => {
    const adapter = createAdapter();
    const phases: AppUpdatePhase[] = [];

    await expect(downloadAvailableUpdate(adapter, (phase) => phases.push(phase))).resolves.toBe('current');
    expect(phases).toEqual(['checking']);
    expect(adapter.fetchUpdateAsync).not.toHaveBeenCalled();
  });

  it('downloads an available update and reports ready', async () => {
    const adapter = createAdapter({
      checkForUpdateAsync: jest.fn().mockResolvedValue({ isAvailable: true }),
    });
    const phases: AppUpdatePhase[] = [];

    await expect(downloadAvailableUpdate(adapter, (phase) => phases.push(phase))).resolves.toBe('ready');
    expect(phases).toEqual(['checking', 'downloading']);
    expect(adapter.fetchUpdateAsync).toHaveBeenCalledTimes(1);
  });

  it('does not hide update-service failures', async () => {
    const failure = new Error('network unavailable');
    const adapter = createAdapter({
      checkForUpdateAsync: jest.fn().mockRejectedValue(failure),
    });

    await expect(downloadAvailableUpdate(adapter)).rejects.toBe(failure);
  });

  it('reloads only after the caller explicitly applies the update', async () => {
    const adapter = createAdapter();

    await applyDownloadedUpdate(adapter);

    expect(adapter.reloadAsync).toHaveBeenCalledTimes(1);
  });

  it('formats the native version and build without a hardcoded fallback', () => {
    expect(getNativeVersionLabel({ nativeAppVersion: '1.4.0', nativeBuildVersion: '231' })).toBe('1.4.0 (231)');
    expect(getNativeVersionLabel({ nativeAppVersion: '1.4.0', nativeBuildVersion: null })).toBe('1.4.0');
    expect(getNativeVersionLabel({ nativeAppVersion: null, nativeBuildVersion: null })).toBe('未知版本');
  });

  it('falls back to embedded Expo config when native constants are unavailable', () => {
    expect(getNativeVersionLabel({
      nativeAppVersion: null,
      nativeBuildVersion: null,
      expoAppVersion: '1.3.2',
      expoBuildVersion: '237',
    })).toBe('1.3.2 (237)');
  });
});
