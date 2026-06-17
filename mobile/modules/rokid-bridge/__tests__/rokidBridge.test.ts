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
      },
    });
    await expect(bridge.openHiRokid()).resolves.toBe(false);
    expect(requireNativeModule).not.toHaveBeenCalled();
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
      },
    });
    await expect(bridge.openHiRokid()).resolves.toBe(true);
    expect(requireNativeModule).toHaveBeenCalledWith('RokidBridge');
    expect(native.getIntegrationStatus).toHaveBeenCalledTimes(1);
    expect(native.openHiRokid).toHaveBeenCalledTimes(1);
  });
});
