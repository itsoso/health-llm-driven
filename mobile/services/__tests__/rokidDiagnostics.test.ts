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
      iosBleConnected: true,
      iosBleDeviceName: 'Glasses_0077',
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
        detail: 'lastRequestAt=2026-06-19T07:51:00+08:00; timeout=180s',
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
        detail: 'eventAt=2026-06-19T07:58:00+08:00',
      }),
    ]));
  });

  it('surfaces suspected companion BLE central contention as a copyable diagnostic row', () => {
    const check = buildRokidSelfCheck({
      platform: 'ios',
      bridgeAvailable: true,
      hiRokidInstalled: true,
      canOpenHiRokid: true,
      mode: 'sdk_probe',
      sdkLinked: true,
      authorizationState: 'authenticated',
      customViewRunning: false,
      capabilitiesReady: false,
      sessionMode: 'customView',
      iosBleConnected: false,
      iosBleDeviceName: 'Glasses_0077',
      customViewPendingRetry: true,
      companionAppName: 'Rokid AI / Hi Rokid',
      companionServerScheme: 'rokidai',
      companionServerHost: 'connect',
      lastOpenUrlFingerprint: 'rokidai://',
      lastOpenUrlAt: new Date().toISOString(),
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
        id: 'ble_companion_suspected',
        label: '眼镜蓝牙疑似占用',
        value: '疑似 Rokid AI / Hi Rokid 仍占用 BLE central',
        severity: 'warn',
        detail: 'device=Glasses_0077; action=完全退出/划掉 Rokid AI / Hi Rokid 后回 Reva 刷新',
      }),
    ]));
    expect(check.capabilityGateway.blockers).toContain(
      'Rokid companion 疑似仍占用眼镜蓝牙: iOS 一次只能一个 central。请完全退出/划掉 Rokid AI / Hi Rokid 后回小巴健康刷新。',
    );
  });

  it('surfaces the configured and accepted callback schemes used for Rokid auth routing', () => {
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
      callbackScheme: 'cxrl',
      callbackUrl: 'cxrl://auth/callback',
      callbackSchemeSource: 'info_plist',
      acceptedCallbackSchemes: ['cxrl', 'life.executor.health.rokid'],
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
        id: 'callback_schemes',
        label: 'Callback Schemes',
        value: 'cxrl, life.executor.health.rokid',
        detail: 'configured=cxrl; source=info_plist',
        severity: 'info',
      }),
      expect.objectContaining({
        id: 'authorization',
        detail: 'cxrl://auth/callback',
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
        detail: 'life.executor.health://auth/callback; at=2026-06-19T07:59:00+08:00; expected=life.executor.health.rokid://auth/callback',
      }),
    ]));
    expect(JSON.stringify(check.items)).not.toContain('code=');
    expect(JSON.stringify(check.items)).not.toContain('state=');
  });

  it('surfaces native authorization attempt timeline and SDK state transitions', () => {
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
      lastAuthorizationAttemptId: 'auth-7',
      authorizationAttemptCount: 7,
      lastAuthorizationPhase: 'authenticate_failed',
      lastAuthorizationDurationMs: 180123,
      lastAuthorizationStateBeforeReset: 'not_authenticated',
      lastAuthorizationStateAfterReset: 'not_authenticated',
      lastAuthorizationStateBeforeAuthenticate: 'not_authenticated',
      authorizationConfigSummary: 'server=rokidai://connect; callback=life.executor.health.rokid://auth/callback; timeout=180s',
      authDiagnosticTimeline: [
        '2026-06-18T23:59:00Z #auth-7 request_started appName=Reva; scopes=device_control,audio_stream',
        '2026-06-18T23:59:01Z #auth-7 config_refreshed server=rokidai://connect; callback=life.executor.health.rokid://auth/callback; timeout=180s',
        '2026-06-19T00:02:01Z #auth-7 authenticate_failed Error Domain=RGCxrClientAuthError Code=-1',
      ],
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
        id: 'auth_attempt',
        label: '授权 Attempt',
        value: 'auth-7 / #7 / authenticate_failed',
        detail: 'duration=180123ms',
        severity: 'warn',
      }),
      expect.objectContaining({
        id: 'auth_state_trace',
        label: 'SDK 状态轨迹',
        value: 'beforeReset=not_authenticated; afterReset=not_authenticated; beforeAuth=not_authenticated',
        detail: 'server=rokidai://connect; callback=life.executor.health.rokid://auth/callback; timeout=180s',
        severity: 'info',
      }),
      expect.objectContaining({
        id: 'auth_timeline',
        label: 'Native 授权时间线',
        value: '2026-06-19T07:59:00+08:00 #auth-7 request_started appName=Reva; scopes=device_control,audio_stream\n2026-06-19T07:59:01+08:00 #auth-7 config_refreshed server=rokidai://connect; callback=life.executor.health.rokid://auth/callback; timeout=180s\n2026-06-19T08:02:01+08:00 #auth-7 authenticate_failed Error Domain=RGCxrClientAuthError Code=-1',
        severity: 'warn',
      }),
    ]));
  });

  it('includes capability routing when CustomView is silent after authorization', () => {
    const check = buildRokidSelfCheck({
      platform: 'ios',
      bridgeAvailable: true,
      hiRokidInstalled: true,
      canOpenHiRokid: true,
      mode: 'sdk_probe',
      sdkLinked: true,
      authorizationState: 'authenticated',
      iosBleConnected: true,
      iosBleDeviceName: 'Glasses_0077',
      customAppSupported: true,
      customViewRunning: false,
      capabilitiesReady: false,
      sessionMode: 'customView',
      lastCustomViewOpenError: 'rokid_custom_view_open_callback_missing; running=false; rawNotify=none; iosBleConnected=true; device=Glasses_0077',
      sdkArtifacts: {
        clientM: 'com.rokid.cxr:client-m:1.2.2',
        clientL: 'com.rokid.cxr:client-l:1.0.3',
        iosClient: 'RGCxrClient:1.0.1',
        iosClientCandidate: 'RGCxrClient:1.0.2',
        iosCore: 'RGCoreKit:0.0.2',
      },
    });

    expect(check.capabilityGateway.summary).toMatchObject({
      display: 'blocked',
      movement: 'ready',
      capture: 'degraded',
    });
    expect(check.items).toEqual(expect.arrayContaining([
      expect.objectContaining({
        id: 'capability_route',
        label: '能力路由',
        value: '眼镜端 App 优先',
        severity: 'warn',
        detail: '显示=blocked; 采集=degraded; 运动=ready',
      }),
    ]));
    expect(check.capabilityGateway.blockers).toContain(
      'CXR-L CustomView 静默: openCustomView 未收到 callback/notify, 不应再阻塞运动和饮食主流程。',
    );
  });

  it('routes to mobile fallback when Rokid reports NoNetwork for the CXR data channel', () => {
    const check = buildRokidSelfCheck({
      platform: 'ios',
      bridgeAvailable: true,
      hiRokidInstalled: true,
      canOpenHiRokid: true,
      mode: 'sdk_probe',
      sdkLinked: true,
      authorizationState: 'authenticated',
      iosBleConnected: true,
      iosBleDeviceName: 'Glasses_0077',
      customAppSupported: true,
      customViewRunning: false,
      capabilitiesReady: false,
      sessionMode: 'customView',
      lastCustomViewOpenError: 'rokid_glasses_no_network; CXR 数据通道(TCP/WiFi)需眼镜联网; rawNotify=cmd=1; subCmd=NoNetwork; status=0; reqId=8; iosBleConnected=true; device=Glasses_0077',
      lastCustomViewRawNotify: 'cmd=1; subCmd=NoNetwork; status=0; reqId=8',
      sdkArtifacts: {
        clientM: 'com.rokid.cxr:client-m:1.2.2',
        clientL: 'com.rokid.cxr:client-l:1.0.3',
        iosClient: 'RGCxrClient:1.0.1',
        iosClientCandidate: 'RGCxrClient:1.0.2',
        iosCore: 'RGCoreKit:0.0.2',
      },
    });

    expect(check.capabilityGateway.recommendedPath).toBe('mobile_fallback');
    expect(check.capabilityGateway.blockers).toContain(
      'Rokid 眼镜网络未就绪: 请确认眼镜已连 WiFi、手机和眼镜同网或 companion 已建立数据通道。',
    );
    expect(check.items).toEqual(expect.arrayContaining([
      expect.objectContaining({
        id: 'capability_route',
        label: '能力路由',
        value: '手机兜底',
        severity: 'warn',
        detail: '显示=blocked; 采集=blocked; 运动=degraded',
      }),
    ]));
  });
});
