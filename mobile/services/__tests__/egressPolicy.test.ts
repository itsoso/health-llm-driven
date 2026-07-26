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

  it('allows only an explicit cloud-session bootstrap before login', async () => {
    setAppEgressMode(null);
    expect(() => assertAppEgressAllowed({ cloudSessionBootstrap: true })).not.toThrow();
    await expect(
      enforceAppEgressAllowed({ cloudSessionBootstrap: true }),
    ).resolves.toBeUndefined();
    await expect(
      enforceAppEgressAllowed({ explicitCloudAI: true }),
    ).rejects.toMatchObject({
      code: 'cloud_session_required',
    });
  });

  it('allows a persisted cloud credential to recover its session', async () => {
    setAppEgressMode(null);
    expect(() => assertAppEgressAllowed({ cloudCredentialPresent: true })).not.toThrow();
    await expect(
      enforceAppEgressAllowed({ cloudCredentialPresent: true }),
    ).resolves.toBeUndefined();
  });

  it('allows traffic after a cloud account session is active', async () => {
    setAppEgressMode('cloud_account');
    expect(() => assertAppEgressAllowed()).not.toThrow();
    await expect(enforceAppEgressAllowed()).resolves.toBeUndefined();
  });
});
