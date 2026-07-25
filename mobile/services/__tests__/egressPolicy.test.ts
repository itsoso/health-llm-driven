import {
  AppEgressBlockedError,
  assertAppEgressAllowed,
  enforceAppEgressAllowed,
  setAppEgressMode,
} from '../egressPolicy';

describe('cloud-only app egress policy', () => {
  afterEach(() => setAppEgressMode(null));

  it('fails closed before a cloud account session is active', async () => {
    setAppEgressMode(null);
    expect(() => assertAppEgressAllowed()).toThrow(AppEgressBlockedError);
    await expect(enforceAppEgressAllowed()).rejects.toMatchObject({
      code: 'cloud_session_required',
    });
  });

  it('allows traffic after a cloud account session is active', async () => {
    setAppEgressMode('cloud_account');
    expect(() => assertAppEgressAllowed()).not.toThrow();
    await expect(enforceAppEgressAllowed()).resolves.toBeUndefined();
  });
});
