import {
  getReleasePolicyRolloutBucket,
  getNativeUpdateRequirement,
  isOfficialNativeUpdateUrl,
  isReleasePolicyEligible,
  SAFE_RELEASE_POLICY,
  loadReleasePolicy,
  type ReleasePolicy,
} from '../remoteConfig';

const validPolicy: ReleasePolicy = {
  config_version: 3,
  platform: 'ios',
  channel: 'production',
  ota_enabled: false,
  rollout_percent: 25,
  minimum_native_build: '227',
  recommended_native_build: '228',
  native_update_url: 'https://apps.apple.com/app/id123456789',
  forced_update: false,
  kill_switches: { dynamic_cards: true },
  rollback_update_id: '019f-good-update',
  expires_at: '2030-01-01T00:00:00.000Z',
  source: 'remote',
};

function storage(initial: string | null = null) {
  let value = initial;
  return {
    getItem: jest.fn(async () => value),
    setItem: jest.fn(async (_key: string, next: string) => { value = next; }),
  };
}

function client(data: unknown) {
  return { get: jest.fn(async () => ({ data })) };
}

describe('loadReleasePolicy', () => {
  it('returns and caches a valid remote policy', async () => {
    const store = storage();
    const http = client(validPolicy);

    const result = await loadReleasePolicy({
      client: http,
      store,
      platform: 'ios',
      channel: 'production',
      now: () => Date.parse('2026-07-16T00:00:00.000Z'),
    });

    expect(result).toEqual(validPolicy);
    expect(http.get).toHaveBeenCalledWith('/app-release-policy', {
      params: { platform: 'ios', channel: 'production' },
    });
    expect(store.setItem).toHaveBeenCalledTimes(1);
  });

  it('uses an unexpired cached policy when the server is unavailable', async () => {
    const store = storage(JSON.stringify(validPolicy));
    const http = { get: jest.fn(async () => { throw new Error('offline'); }) };

    const result = await loadReleasePolicy({
      client: http,
      store,
      platform: 'ios',
      channel: 'production',
      now: () => Date.parse('2026-07-16T00:00:00.000Z'),
    });

    expect(result).toEqual(validPolicy);
  });

  it('rejects malformed remote data and falls back to safe defaults', async () => {
    const store = storage();

    const result = await loadReleasePolicy({
      client: client({ config_version: '3' }),
      store,
      platform: 'ios',
      channel: 'production',
      now: () => Date.parse('2026-07-16T00:00:00.000Z'),
    });

    expect(result).toEqual({ ...SAFE_RELEASE_POLICY, platform: 'ios', channel: 'production' });
    expect(store.setItem).not.toHaveBeenCalled();
  });

  it('does not use an expired cached policy', async () => {
    const store = storage(JSON.stringify({
      ...validPolicy,
      expires_at: '2020-01-01T00:00:00.000Z',
    }));
    const http = { get: jest.fn(async () => { throw new Error('offline'); }) };

    const result = await loadReleasePolicy({
      client: http,
      store,
      platform: 'ios',
      channel: 'production',
      now: () => Date.parse('2026-07-16T00:00:00.000Z'),
    });

    expect(result).toEqual({ ...SAFE_RELEASE_POLICY, platform: 'ios', channel: 'production' });
  });
});

describe('release policy controls', () => {
  it.each([
    ['190', 'required'],
    ['227', 'recommended'],
    ['228', 'none'],
    ['not-a-build', 'required'],
  ])('classifies native update requirement for build %s', (nativeBuild, expected) => {
    expect(getNativeUpdateRequirement(validPolicy, nativeBuild)).toBe(expected);
  });

  it.each([
    ['https://apps.apple.com/app/id123456789', true],
    ['https://play.google.com/store/apps/details?id=life.executor.health', true],
    ['https://example.com/update', false],
    ['itms-apps://itunes.apple.com/app/id123456789', false],
  ])('validates official native update URL %s', (url, expected) => {
    expect(isOfficialNativeUpdateUrl(url)).toBe(expected);
  });

  it('persists a stable rollout bucket without using health or account data', async () => {
    const store = storage();

    await expect(getReleasePolicyRolloutBucket({ store, random: () => 0.42 })).resolves.toBe(42);
    await expect(getReleasePolicyRolloutBucket({ store, random: () => 0.99 })).resolves.toBe(42);
    expect(store.setItem).toHaveBeenCalledWith('xiaoba.release_cohort.v1', '42');
  });

  it.each([
    [validPolicy, '190', 10, false],
    [{ ...validPolicy, ota_enabled: true }, '226', 10, false],
    [{ ...validPolicy, ota_enabled: true, minimum_native_build: null }, '227', 24, true],
    [{ ...validPolicy, ota_enabled: true, minimum_native_build: null }, '227', 25, false],
    [{ ...validPolicy, ota_enabled: true, minimum_native_build: null, rollout_percent: 100 }, '227', 99, true],
  ])('applies ota, native build and rollout guards', (policy, nativeBuild, bucket, expected) => {
    expect(isReleasePolicyEligible(policy, nativeBuild, bucket)).toBe(expected);
  });
});
