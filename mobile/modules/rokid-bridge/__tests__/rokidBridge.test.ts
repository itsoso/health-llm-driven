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
    expect(native.startRecord).toHaveBeenCalledWith('food_voice', 'pcm', 'rokidOmni');
    expect(native.stopRecord).toHaveBeenCalledWith('food_voice');
    expect(native.clearAuthorization).toHaveBeenCalledTimes(1);
  });
});
