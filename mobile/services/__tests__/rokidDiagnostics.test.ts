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
      lastOpenUrlFingerprint: 'life.executor.health.rokid://auth/callback',
      lastOpenUrlExpectedAuthCallback: true,
      lastOpenUrlAt: '2026-06-18T23:59:00Z',
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

  it('surfaces iOS auth callback routing diagnostics', () => {
    const check = buildRokidSelfCheck({
      platform: 'ios',
      bridgeAvailable: true,
      hiRokidInstalled: true,
      canOpenHiRokid: true,
      mode: 'sdk_probe',
      sdkLinked: true,
      authorizationState: 'not_authenticated',
      customViewRunning: false,
      capabilitiesReady: false,
      sessionMode: 'customView',
      callbackScheme: 'life.executor.health.rokid',
      callbackUrl: 'life.executor.health.rokid://auth/callback',
      lastCallbackUrl: 'life.executor.health.rokid://auth/callback?code=abc',
      lastCallbackHandled: true,
      sdkArtifacts: {
        clientM: 'com.rokid.cxr:client-m:1.2.2',
        clientL: 'com.rokid.cxr:client-l:1.0.3',
        iosClient: 'RGCxrClient:1.0.1',
        iosClientCandidate: 'RGCxrClient:1.0.2',
        iosCore: 'RGCoreKit:0.0.2',
      },
    });

    expect(check.items).toEqual(expect.arrayContaining([
      expect.objectContaining({
        id: 'auth_callback',
        severity: 'pass',
        value: '最近回调已进入 Reva',
        detail: 'life.executor.health.rokid://auth/callback?<redacted>',
      }),
    ]));
    expect(check.items.find((item) => item.id === 'authorization')).toMatchObject({
      detail: 'life.executor.health.rokid://auth/callback',
    });
  });

  it('surfaces iOS authorization timeout without leaking callback query data', () => {
    const check = buildRokidSelfCheck({
      platform: 'ios',
      bridgeAvailable: true,
      hiRokidInstalled: true,
      canOpenHiRokid: true,
      mode: 'sdk_probe',
      sdkLinked: true,
      authorizationState: 'authenticating',
      customViewRunning: false,
      capabilitiesReady: false,
      sessionMode: 'customView',
      callbackScheme: 'life.executor.health.rokid',
      callbackUrl: 'life.executor.health.rokid://auth/callback',
      lastCallbackUrl: 'life.executor.health.rokid://auth/callback?code=abc&state=secret',
      lastCallbackHandled: false,
      lastAuthorizationError: 'Error Domain=RGCxrClientAuthError Code=-1 "鉴权请求超时"',
      lastAuthorizationRequestAt: '2026-06-18T23:51:00Z',
      authorizationRequestTimeoutSeconds: 180,
      sdkArtifacts: {
        clientM: 'com.rokid.cxr:client-m:1.2.2',
        clientL: 'com.rokid.cxr:client-l:1.0.3',
        iosClient: 'RGCxrClient:1.0.1',
        iosClientCandidate: 'RGCxrClient:1.0.2',
        iosCore: 'RGCoreKit:0.0.2',
      },
    });

    expect(check.items).toEqual(expect.arrayContaining([
      expect.objectContaining({
        id: 'auth_callback',
        value: '回调进入 Reva, SDK 未确认',
        detail: 'life.executor.health.rokid://auth/callback?<redacted>',
      }),
      expect.objectContaining({
        id: 'auth_error',
        severity: 'warn',
        value: '鉴权请求超时',
        detail: 'lastRequestAt=2026-06-18T23:51:00Z; timeout=180s',
      }),
    ]));
    expect(JSON.stringify(check.items)).not.toContain('code=abc');
    expect(JSON.stringify(check.items)).not.toContain('state=secret');
  });

  it('surfaces companion routing and native auth event diagnostics', () => {
    const check = buildRokidSelfCheck({
      platform: 'ios',
      bridgeAvailable: true,
      hiRokidInstalled: true,
      canOpenHiRokid: true,
      mode: 'sdk_probe',
      sdkLinked: true,
      authorizationState: 'not_authenticated',
      customViewRunning: false,
      capabilitiesReady: false,
      sessionMode: 'customView',
      callbackScheme: 'life.executor.health.rokid',
      callbackUrl: 'life.executor.health.rokid://auth/callback',
      companionAppName: 'Rokid AI / Hi Rokid',
      companionServerScheme: 'rokidai',
      companionServerHost: 'connect',
      lastAuthorizationEvent: 'authenticationFailed: user_cancelled',
      lastAuthorizationEventAt: '2026-06-18T23:58:00Z',
      currentDeviceName: 'Rokid Glasses',
      sdkArtifacts: {
        clientM: 'com.rokid.cxr:client-m:1.2.2',
        clientL: 'com.rokid.cxr:client-l:1.0.3',
        iosClient: 'RGCxrClient:1.0.1',
        iosClientCandidate: 'RGCxrClient:1.0.2',
        iosCore: 'RGCoreKit:0.0.2',
      },
    });

    expect(check.items).toEqual(expect.arrayContaining([
      expect.objectContaining({
        id: 'companion',
        label: 'Rokid AI / Hi Rokid',
        value: 'Rokid companion 可用',
        detail: 'server=rokidai://connect; device=Rokid Glasses',
      }),
      expect.objectContaining({
        id: 'auth_event',
        label: 'SDK 授权事件',
        value: 'authenticationFailed: user_cancelled',
        severity: 'warn',
        detail: 'eventAt=2026-06-18T23:58:00Z',
      }),
    ]));
  });

  it('surfaces query-free iOS openURL fingerprints for callback mismatch diagnosis', () => {
    const check = buildRokidSelfCheck({
      platform: 'ios',
      bridgeAvailable: true,
      hiRokidInstalled: true,
      canOpenHiRokid: true,
      mode: 'sdk_probe',
      sdkLinked: true,
      authorizationState: 'not_authenticated',
      customViewRunning: false,
      capabilitiesReady: false,
      sessionMode: 'customView',
      callbackScheme: 'life.executor.health.rokid',
      callbackUrl: 'life.executor.health.rokid://auth/callback',
      lastOpenUrlFingerprint: 'life.executor.health://auth/callback',
      lastOpenUrlAt: '2026-06-18T23:59:00Z',
      lastOpenUrlExpectedAuthCallback: false,
      sdkArtifacts: {
        clientM: 'com.rokid.cxr:client-m:1.2.2',
        clientL: 'com.rokid.cxr:client-l:1.0.3',
        iosClient: 'RGCxrClient:1.0.1',
        iosClientCandidate: 'RGCxrClient:1.0.2',
        iosCore: 'RGCoreKit:0.0.2',
      },
    });

    expect(check.items).toEqual(expect.arrayContaining([
      expect.objectContaining({
        id: 'ios_open_url',
        label: 'iOS 回跳',
        value: '最近回跳不是授权 scheme',
        severity: 'warn',
        detail: 'life.executor.health://auth/callback; at=2026-06-18T23:59:00Z; expected=life.executor.health.rokid://auth/callback',
      }),
    ]));
    expect(JSON.stringify(check.items)).not.toContain('code=');
    expect(JSON.stringify(check.items)).not.toContain('state=');
  });
});
