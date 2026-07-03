import { APP_DISPLAY_NAME } from '../../../constants/brand';

/**
 * Brand-copy gate for the rokid-bridge PRODUCER functions.
 *
 * The legacy product name "Reva" must never appear in user-visible copy
 * produced at runtime (validation steps, capability gateway, CustomView
 * defaults, authorization appName default). Internal identifiers such as
 * `createRokidRevaCustomViewLayout` or layout node ids (`reva_root`) are
 * intentionally out of scope — this gate asserts on PRODUCER OUTPUT, not on
 * source text.
 */
const LEGACY_BRAND_PATTERN = /Reva/i;

describe('rokid-bridge producer brand copy gate', () => {
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

  const iosNotLinked = {
    platform: 'ios',
    bridgeAvailable: true,
    sdkLinked: false,
    hiRokidInstalled: false,
    canOpenHiRokid: false,
    authorizationState: 'not_authenticated',
    customViewRunning: false,
    capabilitiesReady: false,
  };

  const iosRequestedButUnlinked = {
    ...iosNotLinked,
    iosSdkDependencyMode: 'requested_but_unlinked',
    sdkLinkedReason: 'sdk_requested_callback_macro_but_RGCxrClient_unavailable',
    cxrCallbackApiEnabled: true,
  };

  const iosCompanionBleSuspected = {
    platform: 'ios',
    bridgeAvailable: true,
    sdkLinked: true,
    hiRokidInstalled: true,
    canOpenHiRokid: true,
    authorizationState: 'authenticated',
    iosBleConnected: false,
    iosBleDeviceName: 'Glasses_0077',
    customViewPendingRetry: true,
    customViewRunning: false,
    capabilitiesReady: false,
    lastOpenUrlFingerprint: 'rokidai://',
    lastOpenUrlAt: new Date().toISOString(),
  };

  const iosAllReady = {
    platform: 'ios',
    bridgeAvailable: true,
    sdkLinked: true,
    hiRokidInstalled: true,
    canOpenHiRokid: true,
    authorizationState: 'authenticated',
    iosBleConnected: true,
    iosBleDeviceName: 'Glasses_0077',
    customAppSupported: true,
    customViewRunning: true,
    capabilitiesReady: true,
  };

  const iosNoNetwork = {
    ...iosAllReady,
    customViewRunning: false,
    capabilitiesReady: false,
    lastCustomViewOpenError: 'rokid_glasses_no_network; rawNotify=cmd=1; subCmd=NoNetwork; status=0',
    lastCustomViewRawNotify: 'cmd=1; subCmd=NoNetwork; status=0',
  };

  const androidBridgeReady = {
    platform: 'android',
    bridgeAvailable: true,
    hiRokidInstalled: true,
    canOpenHiRokid: true,
    authorizationState: 'not_authenticated',
    customViewRunning: false,
    capabilitiesReady: false,
  };

  const bridgeUnavailable = {
    platform: 'ios',
    bridgeAvailable: false,
    hiRokidInstalled: false,
    canOpenHiRokid: false,
  };

  const stepStatuses = [
    iosNotLinked,
    iosRequestedButUnlinked,
    iosCompanionBleSuspected,
    iosAllReady,
    androidBridgeReady,
    bridgeUnavailable,
  ];

  it('emits no legacy brand copy from getRokidDeviceValidationSteps across step branches', () => {
    const { bridge } = loadModule('ios');

    for (const status of stepStatuses) {
      const steps = bridge.getRokidDeviceValidationSteps(status);
      expect(steps.length).toBeGreaterThan(0);
      for (const step of steps) {
        for (const field of [step.title, step.detail, step.actionLabel]) {
          expect(field ?? '').not.toMatch(LEGACY_BRAND_PATTERN);
        }
      }
      expect(JSON.stringify(steps)).not.toMatch(LEGACY_BRAND_PATTERN);
    }

    // Positive anchors: the brand constant is actually wired in, not just "Reva" deleted.
    const steps = bridge.getRokidDeviceValidationSteps(iosNotLinked);
    expect(steps.find((step: any) => step.id === 'ios_sdk_linked')).toMatchObject({
      actionLabel: `安装 Rokid 版${APP_DISPLAY_NAME}`,
    });
    expect(steps.find((step: any) => step.id === 'custom_view_running')).toMatchObject({
      title: `${APP_DISPLAY_NAME}眼镜视图`,
      actionLabel: `打开${APP_DISPLAY_NAME}眼镜视图`,
    });
    expect(steps.find((step: any) => step.id === 'rokid_authorized')?.detail)
      .toBe(`在${APP_DISPLAY_NAME}中完成 CXR-L 授权回调后继续。`);
  });

  it('emits no legacy brand copy from the capability gateway builder (blockers + capabilities)', () => {
    const { bridge } = loadModule('ios');

    for (const status of [
      iosNotLinked,
      iosCompanionBleSuspected,
      iosAllReady,
      iosNoNetwork,
      bridgeUnavailable,
    ]) {
      const gateway = bridge.buildRokidCapabilityGateway(status);
      expect(gateway.capabilities.length).toBeGreaterThan(0);
      expect(JSON.stringify(gateway)).not.toMatch(LEGACY_BRAND_PATTERN);
    }

    // Positive anchor on the companion-contention blocker branch.
    const gateway = bridge.buildRokidCapabilityGateway(iosCompanionBleSuspected);
    expect(gateway.blockers).toContain(
      `Rokid companion 疑似仍占用眼镜蓝牙: iOS 一次只能一个 central。请完全退出/划掉 Rokid AI / Hi Rokid 后回${APP_DISPLAY_NAME}刷新。`,
    );
  });

  it('defaults the CustomView layout copy to the brand name', () => {
    const { bridge } = loadModule('ios');

    const layout = bridge.createRokidRevaCustomViewLayout();
    const parsed = JSON.parse(layout);
    const texts: string[] = [];
    const walk = (node: any) => {
      if (!node) {
        return;
      }
      if (node.props?.text) {
        texts.push(String(node.props.text));
      }
      (node.children ?? []).forEach(walk);
    };
    walk(parsed);

    expect(texts.length).toBeGreaterThan(0);
    for (const text of texts) {
      expect(text).not.toMatch(LEGACY_BRAND_PATTERN);
    }
    expect(texts).toContain(APP_DISPLAY_NAME);
    expect(texts).toContain(`等待${APP_DISPLAY_NAME}投递下一条健康行动`);
    // Layout node ids (reva_root/…) are internal identifiers, so only the
    // brand-cased legacy name is banned on the raw payload.
    expect(layout).not.toMatch(/Reva/);
  });

  it('defaults requestAuthorization appName to the brand name', async () => {
    const native = {
      requestAuthorization: jest.fn().mockResolvedValue({ ok: true }),
    };
    const { bridge } = loadModule('ios', native);

    await expect(bridge.requestRokidAuthorization()).resolves.toMatchObject({ ok: true });
    expect(native.requestAuthorization).toHaveBeenCalledWith(
      ['device_control', 'audio_stream'],
      APP_DISPLAY_NAME,
    );
    expect(String(native.requestAuthorization.mock.calls[0][1])).not.toMatch(LEGACY_BRAND_PATTERN);
  });
});
