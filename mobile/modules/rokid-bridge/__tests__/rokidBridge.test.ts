describe('rokid-bridge JS facade', () => {
  const loadModule = (platform: 'android' | 'ios' | 'web', nativeModule?: any) => {
    jest.resetModules();
    const requireNativeModule = jest.fn(() => {
      if (!nativeModule) {
        throw new Error('native module missing');
      }
      return nativeModule;
    });
    jest.doMock('expo-modules-core', () => ({
      Platform: { OS: platform },
      requireNativeModule,
    }));
    return {
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      bridge: require('../index'),
      requireNativeModule,
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
      detail: '在 Reva 中完成 CXR-L 授权回调后继续。',
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
      detail: 'Rokid CXR-L 还未连接到眼镜蓝牙链路: Glasses_0077。请在 Rokid AI / Hi Rokid 中确认眼镜在线, 返回 Reva 后刷新。',
      actionLabel: '打开 Rokid AI / Hi Rokid',
    });
  });
});
