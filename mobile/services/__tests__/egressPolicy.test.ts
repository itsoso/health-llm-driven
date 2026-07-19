import {
  AppEgressBlockedError,
  assertAppEgressAllowed,
  enforceAppEgressAllowed,
  setAppEgressAuditSink,
  setAppEgressMode,
} from '../egressPolicy';

describe('app egress policy', () => {
  afterEach(() => {
    setAppEgressMode(null);
    setAppEgressAuditSink(null);
  });

  it('blocks all requests before the persisted mode is known', () => {
    setAppEgressMode(null);
    expect(() => assertAppEgressAllowed()).toThrow(AppEgressBlockedError);
  });

  it('blocks every request in strict local mode', () => {
    setAppEgressMode('strict_local');
    expect(() => assertAppEgressAllowed()).toThrow('strict_local_egress_blocked');
    expect(() => assertAppEgressAllowed({ explicitCloudAI: true })).toThrow(
      'strict_local_egress_blocked',
    );
  });

  it('allows only an explicit cloud AI request in local-first mode', () => {
    setAppEgressMode('local_first');
    expect(() => assertAppEgressAllowed()).toThrow('local_first_egress_requires_explicit_ai');
    expect(() => assertAppEgressAllowed({ explicitCloudAI: true })).not.toThrow();
  });

  it('keeps existing cloud-account requests unchanged', () => {
    setAppEgressMode('cloud_account');
    expect(() => assertAppEgressAllowed()).not.toThrow();
  });

  it('audits a blocked client request without receiving its payload', async () => {
    const sink = jest.fn().mockResolvedValue(undefined);
    setAppEgressAuditSink(sink);
    setAppEgressMode('strict_local');

    await expect(enforceAppEgressAllowed()).rejects.toMatchObject({
      code: 'strict_local_egress_blocked',
    });
    expect(sink).toHaveBeenCalledWith('strict_local_egress_blocked');
  });
});
