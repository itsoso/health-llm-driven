import { buildRokidSelfCheck } from '../rokidDiagnostics';

describe('rokid diagnostics', () => {
  it('turns a ready iOS status into passed self-check rows', () => {
    const check = buildRokidSelfCheck({
      platform: 'ios',
      bridgeAvailable: true,
      hiRokidInstalled: true,
      canOpenHiRokid: true,
      mode: 'sdk_probe',
      sdkLinked: true,
      authorizationState: 'authenticated',
      customViewRunning: true,
      capabilitiesReady: true,
      sessionMode: 'customView',
      callbackScheme: 'life.executor.health.rokid',
      querySchemes: ['rokidai'],
      sdkArtifacts: {
        clientM: 'com.rokid.cxr:client-m:1.2.2',
        clientL: 'com.rokid.cxr:client-l:1.0.3',
        iosClient: 'RGCxrClient:1.0.1',
        iosClientCandidate: 'RGCxrClient:1.0.2',
        iosCore: 'RGCoreKit:0.0.2',
      },
    });

    expect(check.summary).toEqual({
      bridge: 'ready',
      sdk: 'linked',
      companion: 'ready',
      authorization: 'authenticated',
      session: 'ready',
    });
    expect(check.items.every((item) => item.severity === 'pass')).toBe(true);
    expect(check.validationSteps.map((step) => step.status)).toEqual([
      'done',
      'done',
      'done',
      'done',
      'done',
    ]);
  });

  it('points to the next blocked step when the native bridge is missing', () => {
    const check = buildRokidSelfCheck({
      platform: 'ios',
      bridgeAvailable: false,
      hiRokidInstalled: false,
      canOpenHiRokid: false,
      mode: 'unavailable',
      reason: 'native_bridge_unavailable',
      sdkArtifacts: {
        clientM: 'com.rokid.cxr:client-m:1.2.2',
        clientL: 'com.rokid.cxr:client-l:1.0.3',
        iosClient: 'RGCxrClient:1.0.1',
        iosClientCandidate: 'RGCxrClient:1.0.2',
        iosCore: 'RGCoreKit:0.0.2',
      },
    });

    expect(check.summary.bridge).toBe('missing');
    expect(check.summary.sdk).toBe('not_linked');
    expect(check.items[0]).toMatchObject({
      id: 'bridge',
      severity: 'block',
      value: 'Bridge 未就绪',
    });
    expect(check.validationSteps[0]).toMatchObject({
      id: 'ios_sdk_linked',
      status: 'blocked',
    });
  });
});
