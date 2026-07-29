const { buildWatchInjectionEnv } = require('../plugins/withWatchApp');
const appJson = require('../app.json');

function configForVariant(variant?: string, env: Record<string, string | undefined> = {}) {
  const previous = process.env.APP_VARIANT;
  const optionalEnvKeys = [
    'REVA_IOS_BUILD_NUMBER',
    'ROKID_IOS_SDK_ENABLED',
    'ROKID_IOS_CALLBACK_SCHEME',
    'INCLUDE_WATCH_APP',
    'INCLUDE_SIRI_INTENTS',
  ];
  const previousEnv = new Map<string, string | undefined>();
  if (variant == null) {
    delete process.env.APP_VARIANT;
  } else {
    process.env.APP_VARIANT = variant;
  }
  optionalEnvKeys.forEach((key) => {
    previousEnv.set(key, process.env[key]);
    delete process.env[key];
  });
  Object.entries(env).forEach(([key, value]) => {
    if (!previousEnv.has(key)) previousEnv.set(key, process.env[key]);
    previousEnv.set(key, process.env[key]);
    if (value == null) {
      delete process.env[key];
    } else {
      process.env[key] = value;
    }
  });

  try {
    jest.resetModules();
    const buildConfig = require('../app.config').default;
    return buildConfig({
      config: JSON.parse(JSON.stringify(appJson.expo)),
    } as any);
  } finally {
    if (previous == null) {
      delete process.env.APP_VARIANT;
    } else {
      process.env.APP_VARIANT = previous;
    }
    previousEnv.forEach((value, key) => {
      if (value == null) {
        delete process.env[key];
      } else {
        process.env[key] = value;
      }
    });
  }
}

function configuredUrlSchemes(config: any) {
  return (config.ios?.infoPlist?.CFBundleURLTypes ?? [])
    .flatMap((entry: any) => entry.CFBundleURLSchemes ?? []);
}

function configuredPluginNames(config: any): string[] {
  return (config.plugins ?? []).map((plugin: any) => (
    Array.isArray(plugin) ? plugin[0] : plugin
  ));
}

describe('app.config app links', () => {
  it('uses 小巴 as the user-visible production app name', () => {
    const config = configForVariant('production');

    expect(config.name).toBe('小巴');
    expect(config.ios?.infoPlist?.CFBundleDisplayName).toBe('小巴');
  });

  it('keeps user-visible variant names aligned with 小巴', () => {
    expect(configForVariant('development').ios?.infoPlist?.CFBundleDisplayName).toBe('小巴 Dev');
    expect(configForVariant('preview').ios?.infoPlist?.CFBundleDisplayName).toBe('小巴 Preview');
  });

  it('uses an explicit native build number for reproducible local release builds', () => {
    const config = configForVariant('production', { REVA_IOS_BUILD_NUMBER: '237' });

    expect(config.ios?.buildNumber).toBe('237');
  });

  it('adds the health share universal link domain to iOS builds', () => {
    const config = configForVariant();

    expect(config.ios?.associatedDomains).toContain('applinks:health.executor.life');
  });

  it('adds an Android verified app link for app-open shared pages', () => {
    const config = configForVariant();

    expect(config.android?.intentFilters).toContainEqual({
      action: 'VIEW',
      autoVerify: true,
      data: [
        {
          scheme: 'https',
          host: 'health.executor.life',
          pathPrefix: '/open/shared',
        },
      ],
      category: ['BROWSABLE', 'DEFAULT'],
    });
  });

  it('passes Expo app version to the watch target injector', () => {
    const env = buildWatchInjectionEnv({ version: '1.3.0' }, { PATH: '/usr/bin' });

    expect(env.REVA_MARKETING_VERSION).toBe('1.3.0');
    expect(env.PATH).toBe('/usr/bin');
    expect(env.LANG).toBe('en_US.UTF-8');
  });

  it('keeps the App Store production binary iPhone-only and portrait-only', () => {
    const config = configForVariant('production');

    expect(config.ios?.supportsTablet).toBe(false);
    expect(config.ios?.infoPlist?.UISupportedInterfaceOrientations).toEqual([
      'UIInterfaceOrientationPortrait',
    ]);
    expect(config.ios?.infoPlist?.['UISupportedInterfaceOrientations~ipad']).toBeUndefined();
  });

  it('excludes unverified wearable, glasses, Siri, and background capabilities by default', () => {
    const config = configForVariant('production');
    const plugins = configuredPluginNames(config);
    const infoPlist = config.ios?.infoPlist ?? {};

    expect(plugins).not.toContain('./plugins/withWatchApp');
    expect(plugins).not.toContain('./plugins/withRokidIosPods');
    expect(plugins).not.toContain('./plugins/withRokidIosAuthCallback');
    expect(plugins).not.toContain('./plugins/withRokidPushupApk');
    expect(plugins).not.toContain('./plugins/withIntentsExtension');
    expect(config.extra?.eas?.build?.experimental?.ios?.appExtensions).toBeUndefined();
    expect(infoPlist.UIBackgroundModes).toBeUndefined();
    expect(infoPlist.NSLocationAlwaysAndWhenInUseUsageDescription).toBeUndefined();
    expect(infoPlist.NSBluetoothAlwaysUsageDescription).toBeUndefined();
    expect(infoPlist.NSSiriUsageDescription).toBeUndefined();
    expect(infoPlist.RokidCXRAuthCallbackScheme).toBeUndefined();
    expect(configuredUrlSchemes(config)).not.toEqual(expect.arrayContaining([
      expect.stringContaining('rokid'),
    ]));
  });

  it('keeps location permission foreground-only in the App Store binary', () => {
    const config = configForVariant('production');
    const locationPlugin = (config.plugins ?? []).find((plugin: any) => (
      Array.isArray(plugin) && plugin[0] === 'expo-location'
    ));

    expect(locationPlugin?.[1]).toEqual(expect.objectContaining({
      locationWhenInUsePermission: expect.stringContaining('天气'),
      locationAlwaysPermission: false,
      locationAlwaysAndWhenInUsePermission: false,
      isIosBackgroundLocationEnabled: false,
    }));
  });

  it('does not declare background audio for the App Store production binary', () => {
    const config = configForVariant('production');
    const audioPlugin = (config.plugins ?? []).find((plugin: any) => (
      Array.isArray(plugin) && plugin[0] === 'expo-audio'
    ));

    expect(audioPlugin?.[1]).toEqual(expect.objectContaining({
      enableBackgroundPlayback: false,
      enableBackgroundRecording: false,
    }));
  });

  it('uses variant-specific Rokid callback schemes only for explicit Rokid builds', () => {
    const rokidEnv = { ROKID_IOS_SDK_ENABLED: '1' };
    const productionSchemes = configuredUrlSchemes(configForVariant('production', rokidEnv));
    const previewSchemes = configuredUrlSchemes(configForVariant('preview', rokidEnv));
    const developmentSchemes = configuredUrlSchemes(configForVariant('development', rokidEnv));

    expect(productionSchemes).toContain('life.executor.health.rokid');
    expect(previewSchemes).toContain('life.executor.health.preview.rokid');
    expect(developmentSchemes).toContain('life.executor.health.dev.rokid');
    expect(new Set([
      productionSchemes.find((scheme: string) => scheme.includes('.rokid')),
      previewSchemes.find((scheme: string) => scheme.includes('.rokid')),
      developmentSchemes.find((scheme: string) => scheme.includes('.rokid')),
    ]).size).toBe(3);
  });

  it('allows Rokid CXR-L builds to request the SDK default cxrl callback while keeping the bundle-specific fallback registered', () => {
    const config = configForVariant('production', {
      ROKID_IOS_SDK_ENABLED: '1',
      ROKID_IOS_CALLBACK_SCHEME: 'cxrl',
    });
    const schemes = configuredUrlSchemes(config);

    expect(config.ios?.infoPlist?.RokidCXRAuthCallbackScheme).toBe('cxrl');
    expect(schemes).toEqual(expect.arrayContaining([
      'cxrl',
      'life.executor.health.rokid',
    ]));
  });

  it('adds Watch and Siri native targets only for explicit feature builds', () => {
    const config = configForVariant('production', {
      INCLUDE_WATCH_APP: '1',
      INCLUDE_SIRI_INTENTS: '1',
    });
    const plugins = configuredPluginNames(config);

    expect(plugins).toContain('./plugins/withWatchApp');
    expect(plugins).toContain('./plugins/withIntentsExtension');
    expect(config.extra?.eas?.build?.experimental?.ios?.appExtensions).toHaveLength(2);
    expect(config.ios?.infoPlist?.NSSiriUsageDescription).toContain('Siri');
  });

  it('declares native voice permissions for both hold-to-talk and realtime dictation', () => {
    const plugins = appJson.expo.plugins;

    expect(plugins).toContainEqual([
      'expo-audio',
      expect.objectContaining({
        enableBackgroundPlayback: false,
        enableBackgroundRecording: false,
      }),
    ]);
    expect(plugins).toContainEqual([
      '@react-native-voice/voice',
      expect.objectContaining({
        microphonePermission: expect.stringContaining('语音输入'),
        speechRecognitionPermission: expect.stringContaining('识别你的语音'),
      }),
    ]);
  });

  it('declares the collected data categories used by the App Store production binary', () => {
    const config = configForVariant('production');
    const privacy = config.ios?.privacyManifests;
    const collected = privacy?.NSPrivacyCollectedDataTypes ?? [];
    const collectedTypes = collected.map((entry: any) => entry.NSPrivacyCollectedDataType);

    expect(privacy?.NSPrivacyTracking).toBe(false);
    expect(privacy?.NSPrivacyTrackingDomains).toEqual([]);
    expect(collectedTypes).toEqual(expect.arrayContaining([
      'NSPrivacyCollectedDataTypeHealth',
      'NSPrivacyCollectedDataTypeFitness',
      'NSPrivacyCollectedDataTypeEmailAddress',
      'NSPrivacyCollectedDataTypeUserID',
      'NSPrivacyCollectedDataTypeOtherUserContent',
      'NSPrivacyCollectedDataTypePhotosorVideos',
      'NSPrivacyCollectedDataTypePreciseLocation',
      'NSPrivacyCollectedDataTypeCrashData',
      'NSPrivacyCollectedDataTypePerformanceData',
    ]));
    expect(collected.every((entry: any) => entry.NSPrivacyCollectedDataTypeTracking === false)).toBe(true);
  });

  it('enables Expo privacy manifest aggregation for native dependencies', () => {
    const config = configForVariant('production');
    const buildProperties = (config.plugins ?? []).find((plugin: any) => (
      Array.isArray(plugin) && plugin[0] === 'expo-build-properties'
    ));

    expect(buildProperties?.[1]?.ios?.privacyManifestAggregationEnabled).toBe(true);
  });
});
