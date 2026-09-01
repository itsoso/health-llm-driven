describe('rokid-bridge JS facade', () => {
  afterEach(() => {
    jest.useRealTimers();
  });

  const loadModule = (platform: 'android' | 'ios' | 'web', nativeModule?: any) => {
    jest.resetModules();
    const requireNativeModule = jest.fn(() => {
      if (!nativeModule) {
        throw new Error('native module missing');
      }
      return nativeModule;
    });
    const EventEmitter = jest.fn().mockImplementation(() => ({
      addListener: jest.fn(),
    }));
    jest.doMock('expo-modules-core', () => ({
      Platform: { OS: platform },
      requireNativeModule,
      EventEmitter,
    }));
    return {
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      bridge: require('../index'),
      requireNativeModule,
      EventEmitter,
    };
  };

  it('returns a stable unavailable status when the native bridge is absent', async () => {
    const { bridge, requireNativeModule } = loadModule('ios');

    await expect(bridge.getRokidIntegrationStatus()).resolves.toMatchObject({
      platform: 'ios',
      bridgeAvailable: false,
      hiRokidInstalled: false,
      canOpenHiRokid: false,
      mode: 'unavailable',
      sdkArtifacts: {
        clientM: 'com.rokid.cxr:client-m:1.2.2',
        clientL: 'com.rokid.cxr:client-l:1.0.3',
        iosClient: 'RGCxrClient:1.0.1',
        iosClientCandidate: 'RGCxrClient:1.0.2',
        iosCore: 'RGCoreKit:0.0.2',
      },
    });
    await expect(bridge.openHiRokid()).resolves.toBe(false);
    expect(requireNativeModule).toHaveBeenCalledWith('RokidBridge');
  });

  it('delegates status probing and app launch to the Android native bridge', async () => {
    const native = {
      getIntegrationStatus: jest.fn().mockResolvedValue({
        platform: 'android',
        bridgeAvailable: true,
        hiRokidInstalled: true,
        canOpenHiRokid: true,
        mode: 'sdk_probe',
      }),
      openHiRokid: jest.fn().mockResolvedValue(true),
    };
    const { bridge, requireNativeModule } = loadModule('android', native);

    await expect(bridge.getRokidIntegrationStatus()).resolves.toMatchObject({
      platform: 'android',
      bridgeAvailable: true,
      hiRokidInstalled: true,
      canOpenHiRokid: true,
      mode: 'sdk_probe',
      sdkArtifacts: {
        clientM: 'com.rokid.cxr:client-m:1.2.2',
        clientL: 'com.rokid.cxr:client-l:1.0.3',
        iosClient: 'RGCxrClient:1.0.1',
        iosClientCandidate: 'RGCxrClient:1.0.2',
        iosCore: 'RGCoreKit:0.0.2',
      },
    });
    await expect(bridge.openHiRokid()).resolves.toBe(true);
    expect(requireNativeModule).toHaveBeenCalledWith('RokidBridge');
    expect(native.getIntegrationStatus).toHaveBeenCalledTimes(1);
    expect(native.openHiRokid).toHaveBeenCalledTimes(1);
  });

  it('delegates iOS SDK status and app launch probing to the native bridge', async () => {
    const native = {
      getIntegrationStatus: jest.fn().mockResolvedValue({
        platform: 'ios',
        bridgeAvailable: true,
        hiRokidInstalled: true,
        canOpenHiRokid: true,
        mode: 'sdk_probe',
        sdkLinked: true,
        iosSdkDependencyMode: 'linked',
        iosSdkCompatibility: 'compatible',
        callbackScheme: 'life.executor.health.rokid',
        querySchemes: ['rokidai'],
      }),
      openHiRokid: jest.fn().mockResolvedValue(true),
      requestAuthorization: jest.fn().mockResolvedValue({
        ok: true,
        tokenLength: 24,
        sessionId: 'session-1',
      }),
      openCustomView: jest.fn().mockResolvedValue({ ok: true }),
      updateCustomView: jest.fn().mockResolvedValue({ ok: true }),
      closeCustomView: jest.fn().mockResolvedValue({ ok: true }),
      takePhotoBase64: jest.fn().mockResolvedValue({
        ok: true,
        base64: 'jpeg-base64',
        mimeType: 'image/jpeg',
      }),
      prepareCustomAppSession: jest.fn().mockResolvedValue({ ok: true, cxrInitializationMode: 'customApp' }),
      queryApp: jest.fn().mockResolvedValue({ ok: true, installed: true }),
      installBundledApp: jest.fn().mockResolvedValue({ ok: true, installed: true }),
      installAppFileUri: jest.fn().mockResolvedValue({ ok: true, installed: true }),
      uninstallApp: jest.fn().mockResolvedValue({ ok: true, uninstalled: true }),
      openApp: jest.fn().mockResolvedValue({ ok: true, opened: true }),
      stopApp: jest.fn().mockResolvedValue({ ok: true, stopped: true }),
      startRecord: jest.fn().mockResolvedValue({ ok: true }),
      stopRecord: jest.fn().mockResolvedValue({ ok: true }),
      clearAuthorization: jest.fn().mockResolvedValue(true),
    };
    const { bridge, requireNativeModule } = loadModule('ios', native);

    await expect(bridge.getRokidIntegrationStatus()).resolves.toMatchObject({
      platform: 'ios',
      bridgeAvailable: true,
      hiRokidInstalled: true,
      canOpenHiRokid: true,
      mode: 'sdk_probe',
      sdkLinked: true,
      iosSdkDependencyMode: 'linked',
      iosSdkCompatibility: 'compatible',
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
    await expect(bridge.openHiRokid()).resolves.toBe(true);
    await expect(bridge.requestRokidAuthorization({
      scopes: ['device_control', 'audio_stream'],
      appName: 'Reva',
    })).resolves.toMatchObject({ ok: true, tokenLength: 24 });
    await expect(bridge.openRokidCustomView('{"type":"text","text":"喝水"}')).resolves.toEqual({ ok: true });
    await expect(bridge.updateRokidCustomView('{"type":"text","text":"稍后"}')).resolves.toEqual({ ok: true });
    await expect(bridge.closeRokidCustomView('{"id":"drink-water"}')).resolves.toEqual({ ok: true });
    await expect(bridge.takeRokidPhotoBase64({ width: 1024, height: 768, quality: 80 })).resolves.toMatchObject({
      ok: true,
      base64: 'jpeg-base64',
    });
    await expect(bridge.prepareRokidCustomAppSession('life.executor.health.rokid.pushup')).resolves.toEqual({
      ok: true,
      cxrInitializationMode: 'customApp',
    });
    await expect(bridge.queryRokidApp('life.executor.health.rokid.pushup')).resolves.toEqual({
      ok: true,
      installed: true,
    });
    await expect(bridge.installBundledRokidApp({
      resourceName: 'rokid-pushup-glasses',
      resourceExtension: 'apk',
      packageName: 'life.executor.health.rokid.pushup',
    })).resolves.toEqual({ ok: true, installed: true });
    await expect(bridge.installRokidAppFromFileUri({
      fileUri: 'file:///tmp/rokid-pushup-glasses.apk',
      packageName: 'life.executor.health.rokid.pushup',
    })).resolves.toEqual({ ok: true, installed: true });
    await expect(bridge.uninstallRokidApp('life.executor.health.rokid.pushup')).resolves.toEqual({
      ok: true,
      uninstalled: true,
    });
    await expect(bridge.openRokidApp({
      packageName: 'life.executor.health.rokid.pushup',
      activityName: '.MainActivity',
      url: 'reva://rokid/pushup?session_id=7',
    })).resolves.toEqual({ ok: true, opened: true });
    await expect(bridge.stopRokidApp('life.executor.health.rokid.pushup')).resolves.toEqual({
      ok: true,
      stopped: true,
    });
    await expect(bridge.startRokidRecord({ type: 'food_voice', codec: 'pcm', mode: 'rokidOmni' })).resolves.toEqual({ ok: true });
    await expect(bridge.stopRokidRecord('food_voice')).resolves.toEqual({ ok: true });
    await expect(bridge.clearRokidAuthorization()).resolves.toBe(true);
    expect(requireNativeModule).toHaveBeenCalledWith('RokidBridge');
    expect(native.getIntegrationStatus).toHaveBeenCalledTimes(1);
    expect(native.openHiRokid).toHaveBeenCalledTimes(1);
    expect(native.requestAuthorization).toHaveBeenCalledWith(['device_control', 'audio_stream'], 'Reva');
    expect(native.openCustomView).toHaveBeenCalledWith('{"type":"text","text":"喝水"}');
    expect(native.updateCustomView).toHaveBeenCalledWith('{"type":"text","text":"稍后"}');
    expect(native.closeCustomView).toHaveBeenCalledWith('{"id":"drink-water"}');
    expect(native.takePhotoBase64).toHaveBeenCalledWith(1024, 768, 80);
    expect(native.prepareCustomAppSession).toHaveBeenCalledWith('life.executor.health.rokid.pushup');
    expect(native.queryApp).toHaveBeenCalledWith('life.executor.health.rokid.pushup');
    expect(native.installBundledApp).toHaveBeenCalledWith(
      'rokid-pushup-glasses',
      'apk',
      'life.executor.health.rokid.pushup',
    );
    expect(native.installAppFileUri).toHaveBeenCalledWith(
      'file:///tmp/rokid-pushup-glasses.apk',
      'life.executor.health.rokid.pushup',
    );
    expect(native.uninstallApp).toHaveBeenCalledWith('life.executor.health.rokid.pushup');
    expect(native.openApp).toHaveBeenCalledWith(
      'life.executor.health.rokid.pushup',
      '.MainActivity',
      'reva://rokid/pushup?session_id=7',
    );
    expect(native.stopApp).toHaveBeenCalledWith('life.executor.health.rokid.pushup');
    expect(native.startRecord).toHaveBeenCalledWith('food_voice', 'pcm', 'rokidOmni');
    expect(native.stopRecord).toHaveBeenCalledWith('food_voice');
    expect(native.clearAuthorization).toHaveBeenCalledTimes(1);
  });

  it('settles long-running native CXR-L calls with structured timeout results', async () => {
    jest.useFakeTimers();
    const never = jest.fn(() => new Promise<Record<string, unknown>>(() => undefined));
    const native = {
      getIntegrationStatus: jest.fn().mockResolvedValue({ platform: 'ios', bridgeAvailable: true }),
      openHiRokid: jest.fn().mockResolvedValue(true),
      openCustomView: never,
      takePhotoBase64: never,
      queryApp: never,
      startRecord: never,
      installAppFileUri: never,
    };
    const { bridge } = loadModule('ios', native);

    const calls = [
      bridge.openRokidCustomView('{"type":"text","text":"喝水"}'),
      bridge.takeRokidPhotoBase64({ width: 1024, height: 768, quality: 80 }),
      bridge.queryRokidApp('life.executor.health.rokid.pushup'),
      bridge.startRokidRecord({ type: 'food_voice', codec: 'pcm', mode: 'rokidOmni' }),
      bridge.installRokidAppFromFileUri({
        fileUri: 'file:///tmp/rokid-pushup-glasses.apk',
        packageName: 'life.executor.health.rokid.pushup',
      }),
    ];
    const settled: boolean[] = calls.map(() => false);
    const observed = calls.map((call, index) => call.then((result: Record<string, unknown>) => {
      settled[index] = true;
      return result;
    }));

    await jest.runOnlyPendingTimersAsync();

    expect(settled).toEqual([true, true, true, true, true]);
    await expect(Promise.all(observed)).resolves.toEqual([
      expect.objectContaining({
        ok: false,
        operation: 'openCustomView',
        reason: 'rokid_native_call_timeout',
        timeoutMs: expect.any(Number),
      }),
      expect.objectContaining({
        ok: false,
        operation: 'takePhotoBase64',
        reason: 'rokid_native_call_timeout',
        timeoutMs: expect.any(Number),
      }),
      expect.objectContaining({
        ok: false,
        installed: false,
        operation: 'queryApp',
        reason: 'rokid_native_call_timeout',
        timeoutMs: expect.any(Number),
      }),
      expect.objectContaining({
        ok: false,
        operation: 'startRecord',
        reason: 'rokid_native_call_timeout',
        timeoutMs: expect.any(Number),
      }),
      expect.objectContaining({
        ok: false,
        installed: false,
        operation: 'installAppFileUri',
        reason: 'rokid_native_call_timeout',
        timeoutMs: expect.any(Number),
      }),
    ]);
    expect(native.openCustomView).toHaveBeenCalledWith('{"type":"text","text":"喝水"}');
    expect(native.takePhotoBase64).toHaveBeenCalledWith(1024, 768, 80);
    expect(native.queryApp).toHaveBeenCalledWith('life.executor.health.rokid.pushup');
    expect(native.startRecord).toHaveBeenCalledWith('food_voice', 'pcm', 'rokidOmni');
    expect(native.installAppFileUri).toHaveBeenCalledWith(
      'file:///tmp/rokid-pushup-glasses.apk',
      'life.executor.health.rokid.pushup',
    );
  });

  it('subscribes to native Rokid transcript events through the JS facade', () => {
    const remove = jest.fn();
    const addListener = jest.fn().mockReturnValue({ remove });
    const native = {
      getIntegrationStatus: jest.fn().mockResolvedValue({ platform: 'ios', bridgeAvailable: true }),
      openHiRokid: jest.fn().mockResolvedValue(true),
    };
    const { bridge, EventEmitter } = loadModule('ios', native);
    EventEmitter.mockImplementationOnce(() => ({ addListener }));
    const listener = jest.fn();

    const subscription = bridge.addRokidTranscriptListener(listener);
    subscription.remove();

    expect(EventEmitter).toHaveBeenCalledWith(native);
    expect(addListener).toHaveBeenCalledWith('onRokidTranscript', listener);
    expect(remove).toHaveBeenCalledTimes(1);
  });

  it('returns explicit unavailable results for CustomApp controls when native methods are absent', async () => {
    const native = {
      getIntegrationStatus: jest.fn().mockResolvedValue({ platform: 'ios', bridgeAvailable: true }),
      openHiRokid: jest.fn().mockResolvedValue(true),
    };
    const { bridge } = loadModule('ios', native);

    await expect(bridge.queryRokidApp('life.executor.health.rokid.pushup')).resolves.toEqual({
      ok: false,
      installed: false,
      reason: 'native_bridge_unavailable',
    });
    await expect(bridge.prepareRokidCustomAppSession('life.executor.health.rokid.pushup')).resolves.toEqual({
      ok: false,
      reason: 'native_bridge_unavailable',
    });
    await expect(bridge.installBundledRokidApp({
      resourceName: 'rokid-pushup-glasses',
      resourceExtension: 'apk',
      packageName: 'life.executor.health.rokid.pushup',
    })).resolves.toEqual({
      ok: false,
      installed: false,
      reason: 'native_bridge_unavailable',
    });
    await expect(bridge.installRokidAppFromFileUri({
      fileUri: 'file:///tmp/rokid-pushup-glasses.apk',
      packageName: 'life.executor.health.rokid.pushup',
    })).resolves.toEqual({
      ok: false,
      installed: false,
      reason: 'native_bridge_unavailable',
    });
    await expect(bridge.uninstallRokidApp('life.executor.health.rokid.pushup')).resolves.toEqual({
      ok: false,
      uninstalled: false,
      reason: 'native_bridge_unavailable',
    });
    await expect(bridge.openRokidApp({
      packageName: 'life.executor.health.rokid.pushup',
      activityName: '.MainActivity',
      url: 'reva://rokid/pushup?session_id=7',
    })).resolves.toEqual({ ok: false, opened: false, reason: 'native_bridge_unavailable' });
    await expect(bridge.stopRokidApp('life.executor.health.rokid.pushup')).resolves.toEqual({
      ok: false,
      stopped: false,
      reason: 'native_bridge_unavailable',
    });
  });

  it('opens a Reva customView layout before enabling iOS capture capabilities', async () => {
    const native = {
      getIntegrationStatus: jest.fn().mockResolvedValue({
        platform: 'ios',
        bridgeAvailable: true,
        hiRokidInstalled: true,
        canOpenHiRokid: true,
        mode: 'sdk_probe',
        sdkLinked: true,
        sessionMode: 'customView',
        authorizationState: 'authenticated',
        customViewRunning: false,
        capabilitiesReady: false,
      }),
      openCustomView: jest.fn().mockResolvedValue({
        ok: true,
        customViewRunning: true,
        capabilitiesReady: true,
      }),
    };
    const { bridge } = loadModule('ios', native);

    await expect(bridge.openRokidRevaCustomView({
      title: 'Reva',
      body: '午饭后步行 10 分钟',
      priority: 'P1',
    })).resolves.toMatchObject({
      ok: true,
      customViewRunning: true,
      capabilitiesReady: true,
    });

    expect(native.openCustomView).toHaveBeenCalledTimes(1);
    const view = JSON.parse(native.openCustomView.mock.calls[0][0]);
    expect(view.type).toBe('LinearLayout');
    expect(view.props).toMatchObject({
      layout_width: 'match_parent',
      layout_height: 'match_parent',
      orientation: 'vertical',
    });
    expect(JSON.stringify(view)).toContain('午饭后步行 10 分钟');
    expect(JSON.stringify(view)).toContain('P1');
  });

  it('builds an ordered on-device validation checklist from iOS Rokid status', () => {
    const { bridge } = loadModule('ios');

    const steps = bridge.getRokidDeviceValidationSteps({
      platform: 'ios',
      bridgeAvailable: true,
      hiRokidInstalled: true,
      canOpenHiRokid: true,
      mode: 'sdk_probe',
      sdkLinked: true,
      authorizationState: 'not_authenticated',
      sessionMode: 'customView',
      customViewRunning: false,
      capabilitiesReady: false,
      sdkArtifacts: {
        clientM: 'com.rokid.cxr:client-m:1.2.2',
        clientL: 'com.rokid.cxr:client-l:1.0.3',
        iosClient: 'RGCxrClient:1.0.1',
        iosClientCandidate: 'RGCxrClient:1.0.2',
        iosCore: 'RGCoreKit:0.0.2',
      },
    });

    expect(steps.map((step: any) => step.id)).toEqual([
      'ios_sdk_linked',
      'hi_rokid_ready',
      'rokid_authorized',
      'glasses_ble_connected',
      'custom_view_running',
      'capture_ready',
    ]);
    expect(steps.map((step: any) => step.status)).toEqual([
      'done',
      'done',
      'next',
      'pending',
      'pending',
      'pending',
    ]);
    expect(steps[2]).toMatchObject({
      actionLabel: '授权 Rokid',
      detail: '在小巴健康中完成 CXR-L 授权回调后继续。',
    });
  });

  it('flags iOS builds where CXR-L callback APIs are enabled but RGCxrClient is not imported', () => {
    const { bridge } = loadModule('ios');

    const steps = bridge.getRokidDeviceValidationSteps({
      platform: 'ios',
      bridgeAvailable: true,
      hiRokidInstalled: true,
      canOpenHiRokid: true,
      mode: 'sdk_probe',
      sdkLinked: false,
      iosSdkDependencyMode: 'requested_but_unlinked',
      sdkLinkedReason: 'sdk_requested_callback_macro_but_RGCxrClient_unavailable',
      cxrCallbackApiEnabled: true,
      cxrNotifySubscriptionMode: 'setNotifyEventListenCmds',
      authorizationState: 'not_authenticated',
      sessionMode: 'customView',
      customViewRunning: false,
      capabilitiesReady: false,
      sdkArtifacts: {
        clientM: 'com.rokid.cxr:client-m:1.2.2',
        clientL: 'com.rokid.cxr:client-l:1.0.3',
        iosClient: 'RGCxrClient:1.0.1',
        iosClientCandidate: 'RGCxrClient:1.0.2',
        iosCore: 'RGCoreKit:0.0.2',
      },
    });

    expect(steps[0]).toMatchObject({
      id: 'ios_sdk_linked',
      status: 'next',
      detail: 'Rokid SDK 编译开关已打开, 但 native 未导入 RGCxrClient: sdk_requested_callback_macro_but_RGCxrClient_unavailable。',
    });
    expect(steps[1]).toMatchObject({ id: 'hi_rokid_ready', status: 'done' });
  });

  it('points to the glasses BLE link before opening CustomView when CXR-L is authorized', () => {
    const { bridge } = loadModule('ios');

    const steps = bridge.getRokidDeviceValidationSteps({
      platform: 'ios',
      bridgeAvailable: true,
      hiRokidInstalled: true,
      canOpenHiRokid: true,
      mode: 'sdk_probe',
      sdkLinked: true,
      authorizationState: 'authenticated',
      iosBleConnected: false,
      iosBleDeviceName: 'Glasses_0077',
      sessionMode: 'customView',
      customViewRunning: false,
      capabilitiesReady: false,
      sdkArtifacts: {
        clientM: 'com.rokid.cxr:client-m:1.2.2',
        clientL: 'com.rokid.cxr:client-l:1.0.3',
        iosClient: 'RGCxrClient:1.0.1',
        iosClientCandidate: 'RGCxrClient:1.0.2',
        iosCore: 'RGCoreKit:0.0.2',
      },
    });

    expect(steps.map((step: any) => step.id)).toEqual([
      'ios_sdk_linked',
      'hi_rokid_ready',
      'rokid_authorized',
      'glasses_ble_connected',
      'custom_view_running',
      'capture_ready',
    ]);
    expect(steps.map((step: any) => step.status)).toEqual([
      'done',
      'done',
      'done',
      'next',
      'pending',
      'pending',
    ]);
    expect(steps[3]).toMatchObject({
      title: '眼镜蓝牙链路',
      detail: 'Rokid CXR-L 还未连接到眼镜蓝牙链路: Glasses_0077。授权完成后请「完全退出」Rokid AI / Hi Rokid(它会独占眼镜蓝牙, 一次只能一个 App 连眼镜), 再回小巴健康刷新。',
      actionLabel: '打开 Rokid AI / Hi Rokid',
    });
  });

  it('routes health features around a silent iOS CXR-L CustomView channel', () => {
    const { bridge } = loadModule('ios');

    const gateway = bridge.buildRokidCapabilityGateway({
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
      lastCustomViewOpenError: 'rokid_custom_view_open_callback_missing; running=false; rawNotify=none; iosBleConnected=true; device=Glasses_0077',
      sdkArtifacts: {
        clientM: 'com.rokid.cxr:client-m:1.2.2',
        clientL: 'com.rokid.cxr:client-l:1.0.3',
        iosClient: 'RGCxrClient:1.0.1',
        iosClientCandidate: 'RGCxrClient:1.0.2',
        iosCore: 'RGCoreKit:0.0.2',
      },
    });

    expect(gateway.recommendedPath).toBe('glasses_android_app');
    expect(gateway.summary).toMatchObject({
      native: 'ready',
      display: 'blocked',
      capture: 'degraded',
      voice: 'blocked',
      movement: 'ready',
    });
    expect(gateway.capabilities).toEqual(expect.arrayContaining([
      expect.objectContaining({
        id: 'custom_view',
        state: 'blocked',
        recommendedSurface: 'manual',
      }),
      expect.objectContaining({
        id: 'camera_capture',
        state: 'degraded',
        recommendedSurface: 'rokid_glasses',
      }),
      expect.objectContaining({
        id: 'custom_app_open',
        state: 'degraded',
        recommendedSurface: 'rokid_glasses',
      }),
      expect.objectContaining({
        id: 'mobile_fallback',
        state: 'ready',
        recommendedSurface: 'mobile',
      }),
    ]));
    expect(gateway.blockers).toEqual(expect.arrayContaining([
      'CXR-L CustomView 静默: openCustomView 未收到 callback/notify, 不应再阻塞运动和饮食主流程。',
    ]));
  });

  it('does not label a live typed notify channel as total CustomView silence', () => {
    const { bridge } = loadModule('ios');

    const gateway = bridge.buildRokidCapabilityGateway({
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
      lastCustomViewOpenError: 'rokid_custom_view_open_callback_missing; running=false; rawNotify=cmd=1; subCmd=Dev_BatteryChanged; status=0; reqId=7; iosBleConnected=true; device=Glasses_0077',
      lastCustomViewRawNotify: 'cmd=1; subCmd=Dev_BatteryChanged; status=0; reqId=7',
      sdkArtifacts: {
        clientM: 'com.rokid.cxr:client-m:1.2.2',
        clientL: 'com.rokid.cxr:client-l:1.0.3',
        iosClient: 'RGCxrClient:1.0.1',
        iosClientCandidate: 'RGCxrClient:1.0.2',
        iosCore: 'RGCoreKit:0.0.2',
      },
    });

    expect(gateway.recommendedPath).toBe('glasses_android_app');
    expect(gateway.summary).toMatchObject({
      native: 'ready',
      display: 'blocked',
      capture: 'degraded',
      voice: 'degraded',
      movement: 'ready',
    });
    expect(gateway.blockers).toEqual(expect.arrayContaining([
      'CXR-L notify 通道有响应，但 CustomView 未完成: 继续收集 typed notify/status 后再升级 Rokid。',
    ]));
    expect(gateway.blockers.join('\n')).not.toContain('未收到 callback/notify');
  });

  it('surfaces NoNetwork as a network precondition blocker', () => {
    const { bridge } = loadModule('ios');

    const gateway = bridge.buildRokidCapabilityGateway({
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

    expect(gateway.recommendedPath).toBe('mobile_fallback');
    expect(gateway.summary).toMatchObject({
      display: 'blocked',
      capture: 'blocked',
      voice: 'blocked',
      movement: 'degraded',
    });
    expect(gateway.blockers).toEqual(expect.arrayContaining([
      'Rokid 眼镜网络未就绪: 请确认眼镜已连 WiFi、手机和眼镜同网或 companion 已建立数据通道。',
    ]));
    expect(gateway.blockers.join('\n')).not.toContain('未收到 callback/notify');
  });

  it('keeps a queued CustomView retry degraded rather than blocked', () => {
    const { bridge } = loadModule('ios');

    const gateway = bridge.buildRokidCapabilityGateway({
      platform: 'ios',
      bridgeAvailable: true,
      hiRokidInstalled: true,
      canOpenHiRokid: true,
      mode: 'sdk_probe',
      sdkLinked: true,
      authorizationState: 'authenticated',
      iosBleConnected: false,
      iosBleDeviceName: 'Glasses_0077',
      customViewPendingRetry: true,
      customViewRunning: false,
      capabilitiesReady: false,
      sdkArtifacts: {
        clientM: 'com.rokid.cxr:client-m:1.2.2',
        clientL: 'com.rokid.cxr:client-l:1.0.3',
        iosClient: 'RGCxrClient:1.0.1',
        iosClientCandidate: 'RGCxrClient:1.0.2',
        iosCore: 'RGCoreKit:0.0.2',
      },
    });

    expect(gateway.summary.display).toBe('degraded');
    expect(gateway.capabilities).toEqual(expect.arrayContaining([
      expect.objectContaining({
        id: 'custom_view',
        state: 'degraded',
        detail: 'CustomView 已排队, 等待眼镜蓝牙链路恢复后重试。',
      }),
    ]));
    expect(gateway.blockers).not.toContain(
      'CXR-L CustomView 静默: openCustomView 未收到 callback/notify, 不应再阻塞运动和饮食主流程。',
    );
  });

  it('marks companion BLE central contention as a suspected first-class failure state', () => {
    const { bridge } = loadModule('ios');
    const status = {
      platform: 'ios',
      bridgeAvailable: true,
      hiRokidInstalled: true,
      canOpenHiRokid: true,
      mode: 'sdk_probe',
      sdkLinked: true,
      authorizationState: 'authenticated',
      iosBleConnected: false,
      iosBleDeviceName: 'Glasses_0077',
      customViewPendingRetry: true,
      customViewRunning: false,
      capabilitiesReady: false,
      lastOpenUrlFingerprint: 'rokidai://',
      lastOpenUrlAt: new Date().toISOString(),
      sdkArtifacts: {
        clientM: 'com.rokid.cxr:client-m:1.2.2',
        clientL: 'com.rokid.cxr:client-l:1.0.3',
        iosClient: 'RGCxrClient:1.0.1',
        iosClientCandidate: 'RGCxrClient:1.0.2',
        iosCore: 'RGCoreKit:0.0.2',
      },
    };

    expect(bridge.isRokidBleBlockedByCompanionSuspected(status)).toBe(true);

    const gateway = bridge.buildRokidCapabilityGateway(status);
    expect(gateway.blockers).toContain(
      'Rokid companion 疑似仍占用眼镜蓝牙: iOS 一次只能一个 central。请完全退出/划掉 Rokid AI / Hi Rokid 后回小巴健康刷新。',
    );
    expect(gateway.capabilities).toEqual(expect.arrayContaining([
      expect.objectContaining({
        id: 'glasses_ble',
        state: 'degraded',
        detail: '疑似 Rokid AI / Hi Rokid 仍占用眼镜蓝牙; 请完全退出 companion 后回小巴健康刷新。',
      }),
    ]));

    const steps = bridge.getRokidDeviceValidationSteps(status);
    expect(steps.find((step: any) => step.id === 'glasses_ble_connected')).toMatchObject({
      status: 'next',
      detail: '疑似 Rokid AI / Hi Rokid 仍占用眼镜蓝牙 central: Glasses_0077。请从系统后台完全划掉 Rokid AI / Hi Rokid, 再回小巴健康刷新。',
    });
  });

  it('keeps the mobile fallback ready when the native bridge is unavailable', () => {
    const { bridge } = loadModule('ios');

    const gateway = bridge.buildRokidCapabilityGateway({
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

    expect(gateway.recommendedPath).toBe('mobile_fallback');
    expect(gateway.summary.native).toBe('blocked');
    expect(gateway.capabilities).toEqual(expect.arrayContaining([
      expect.objectContaining({
        id: 'mobile_fallback',
        state: 'ready',
      }),
    ]));
    expect(gateway.blockers).toContain('Rokid native bridge 不可用: 当前只能走手机端兜底。');
  });
});
