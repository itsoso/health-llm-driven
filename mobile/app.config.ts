/**
 * Expo dynamic config — variant 机制让同一个 iPhone 能同时装 production + dev-client.
 *
 * 靠 process.env.APP_VARIANT 切换 bundle ID + 显示名:
 *   - undefined / 'production' → 小气候         (life.executor.health)
 *   - 'development'            → 小气候 Dev     (life.executor.health.dev)
 *   - 'preview'                → 小气候 Preview (life.executor.health.preview)
 *
 * APP_VARIANT 在 eas.json 各 profile 的 env 里设置。
 *
 * app.json 仍在, 作为默认值;本文件只差量覆盖 variant 敏感字段。
 */
import { ExpoConfig, ConfigContext } from 'expo/config';

type AndroidIntentFilter = NonNullable<NonNullable<ExpoConfig['android']>['intentFilters']>[number];

const VARIANT = process.env.APP_VARIANT ?? 'production';
const IS_DEV = VARIANT === 'development';
const IS_PREVIEW = VARIANT === 'preview';
const IS_IOS_BUILD = process.env.EAS_BUILD_PLATFORM === 'ios';
const IS_ANDROID_INTERNAL = process.env.REVA_ANDROID_INTERNAL === '1';
const INCLUDE_ROKID = process.env.ROKID_IOS_SDK_ENABLED === '1';
const INCLUDE_WATCH = process.env.INCLUDE_WATCH_APP === '1';
const INCLUDE_SIRI = process.env.INCLUDE_SIRI_INTENTS === '1';
const IPAD_ENABLED = process.env.REVA_IPAD_ENABLED === '1';
const IPAD_ORIENTATIONS = [
  'UIInterfaceOrientationPortrait', 'UIInterfaceOrientationPortraitUpsideDown',
  'UIInterfaceOrientationLandscapeLeft', 'UIInterfaceOrientationLandscapeRight',
];
const IOS_BUILD_NUMBER = process.env.REVA_IOS_BUILD_NUMBER?.trim();
const LOCAL_UPDATES_CHANNEL = process.env.REVA_LOCAL_UPDATES_CHANNEL;
const DAILY_JOURNEY_RUNTIME = '1.3.6';
const DAILY_JOURNEY_ENABLED = process.env.REVA_DAILY_JOURNEY_ENABLED === '1';
const JOURNEY_LOCATION_USAGE = '用于查询天气、空气质量；你主动同意时单次查找餐厅或记录足迹；主动开启“记录今天行程”后记录路线与停留，可随时暂停、结束或删除';
const JOURNEY_BACKGROUND_USAGE = '仅在你主动开启“记录今天行程”后，在锁屏或切换应用时继续记录当天路线与停留；你可随时暂停、结束或删除，当天结束后不再保存新的位置';

const BUNDLE_ID_BASE = 'life.executor.health';
const APP_LINK_DOMAIN = 'health.executor.life';
const ASSOCIATED_DOMAIN = `applinks:${APP_LINK_DOMAIN}`;
const APP_OPEN_PATH_PREFIX = '/open/shared';
const REGISTRATION_INVITE_PATH = '/open/invite';
const ROKID_QUERY_SCHEMES = ['rokidai'];
const PHOTO_LIBRARY_USAGE_DESCRIPTION =
  '用于你主动选择健康相关图片或生活照片，生成记录草稿、健康分析或足迹回顾';
const PHOTO_LIBRARY_ADD_USAGE_DESCRIPTION = '用于你主动保存健康报告、截图或足迹分享图到照片图库';
const SHARED_LINK_INTENT_FILTER: AndroidIntentFilter = {
  action: 'VIEW',
  autoVerify: true,
  data: [
    {
      scheme: 'https',
      host: APP_LINK_DOMAIN,
      pathPrefix: APP_OPEN_PATH_PREFIX,
    },
  ],
  category: ['BROWSABLE', 'DEFAULT'],
};
const REGISTRATION_INVITE_INTENT_FILTER: AndroidIntentFilter = {
  action: 'VIEW',
  autoVerify: true,
  data: [
    {
      scheme: 'https',
      host: APP_LINK_DOMAIN,
      path: REGISTRATION_INVITE_PATH,
    },
  ],
  category: ['BROWSABLE', 'DEFAULT'],
};
const bundleId = IS_DEV
  ? `${BUNDLE_ID_BASE}.dev`
  : IS_PREVIEW
    ? `${BUNDLE_ID_BASE}.preview`
    : BUNDLE_ID_BASE;

const displayName = IS_DEV
  ? '小气候 Dev'
  : IS_PREVIEW
    ? '小气候 Preview'
    : '小气候';

const androidPackage = bundleId;
const BUNDLE_ROKID_CALLBACK_SCHEME = `${bundleId}.rokid`;
const CONFIGURED_ROKID_CALLBACK_SCHEME = process.env.ROKID_IOS_CALLBACK_SCHEME?.trim();
const ROKID_CALLBACK_SCHEME = CONFIGURED_ROKID_CALLBACK_SCHEME || BUNDLE_ROKID_CALLBACK_SCHEME;
const ROKID_CALLBACK_SCHEMES = Array.from(new Set([
  ROKID_CALLBACK_SCHEME,
  BUNDLE_ROKID_CALLBACK_SCHEME,
]));

const OPTIONAL_NATIVE_PLUGINS = new Set([
  './plugins/withRokidIosPods',
  './plugins/withRokidIosAuthCallback',
  './plugins/withRokidPushupApk',
  './plugins/withWatchApp',
  './plugins/withIntentsExtension',
]);

const WATCH_EXTENSIONS = [
  {
    targetName: 'RevaWatch',
    bundleIdentifier: 'life.executor.health.watchkitapp',
    entitlements: {
      'com.apple.security.application-groups': ['group.life.executor.health'],
    },
  },
  {
    targetName: 'RevaComplication',
    bundleIdentifier: 'life.executor.health.watchkitapp.watchkitextension',
    parentBundleIdentifier: 'life.executor.health.watchkitapp',
    entitlements: {
      'com.apple.security.application-groups': ['group.life.executor.health'],
    },
  },
];

function pluginName(plugin: NonNullable<ExpoConfig['plugins']>[number]): string {
  const name = Array.isArray(plugin) ? plugin[0] : plugin;
  return typeof name === 'string' ? name : '';
}

function withoutOptionalNativePlugins(plugins: ExpoConfig['plugins'] = []) {
  return plugins.filter((plugin) => !OPTIONAL_NATIVE_PLUGINS.has(pluginName(plugin)));
}

function removeKeys<T extends Record<string, any>>(value: T, keys: string[]): T {
  const next = { ...value };
  keys.forEach((key) => delete next[key]);
  return next;
}

export default ({ config }: ConfigContext): ExpoConfig => {
  // Internal APKs are fixed, separately identified candidates, never store/iOS builds.
  if (IS_ANDROID_INTERNAL && (
    !IS_PREVIEW
    || (process.env.EAS_BUILD_PLATFORM !== undefined && process.env.EAS_BUILD_PLATFORM !== 'android')
    || INCLUDE_ROKID || INCLUDE_WATCH || INCLUDE_SIRI
  )) {
    throw new Error('Android internal builds require preview identity and no optional native capabilities');
  }
  if (IPAD_ENABLED && (VARIANT !== 'production' || process.env.EAS_BUILD_PLATFORM === 'android')) {
    throw new Error('iPad internal distribution requires a production iOS identity');
  }
  // EAS injects its channel itself; only the local QR build needs this input.
  const expectedLocalChannel = IS_DEV
    ? 'development'
    : `${INCLUDE_ROKID ? 'rokid-' : ''}${IS_PREVIEW ? 'preview' : 'production'}`;
  if (LOCAL_UPDATES_CHANNEL !== undefined && (
    !['production', 'preview', 'development'].includes(VARIANT)
    || LOCAL_UPDATES_CHANNEL !== expectedLocalChannel
  )) {
    throw new Error('Local updates channel does not match the native app variant/capabilities');
  }
  const dailyJourney = DAILY_JOURNEY_ENABLED && (IS_DEV || IS_PREVIEW)
    && config.version === DAILY_JOURNEY_RUNTIME
    && !IS_ANDROID_INTERNAL && IS_IOS_BUILD;
  const basePlugins = withoutOptionalNativePlugins(config.plugins).map((plugin) => {
    if (pluginName(plugin) !== 'expo-location') return plugin;
    const options = Array.isArray(plugin) ? plugin[1] ?? {} : {};
    return ['expo-location', {
      ...options,
      ...(dailyJourney ? { locationWhenInUsePermission: JOURNEY_LOCATION_USAGE } : {}),
      locationAlwaysPermission: false,
      locationAlwaysAndWhenInUsePermission: dailyJourney ? JOURNEY_BACKGROUND_USAGE : false,
      isIosBackgroundLocationEnabled: dailyJourney,
      isAndroidBackgroundLocationEnabled: false,
      isAndroidForegroundServiceEnabled: false,
    }] as [string, Record<string, unknown>];
  });
  const baseInfoPlist = removeKeys((config.ios?.infoPlist ?? {}) as Record<string, any>, [
    'UISupportedInterfaceOrientations~ipad',
    'UISupportedInterfaceOrientations~pad',
    'UIBackgroundModes',
    'NSLocationAlwaysUsageDescription',
    'NSLocationAlwaysAndWhenInUseUsageDescription',
    'NSBluetoothAlwaysUsageDescription',
    'NSBluetoothPeripheralUsageDescription',
    'NSSiriUsageDescription',
    'LSApplicationQueriesSchemes',
    'RokidCXRAuthCallbackScheme',
  ]);
  const baseUrlTypes = ((baseInfoPlist.CFBundleURLTypes ?? []) as any[]).filter((entry) => (
    entry?.CFBundleURLName !== 'Rokid CXR Auth Callback'
  ));
  const baseExtra = config.extra ?? {};
  const baseEas = (baseExtra.eas ?? {}) as Record<string, any>;

  const plugins: NonNullable<ExpoConfig['plugins']> = [
    ...basePlugins,
    ...(INCLUDE_ROKID ? [
      './plugins/withRokidIosPods',
      './plugins/withRokidIosAuthCallback',
      './plugins/withRokidPushupApk',
    ] : []),
    ...(INCLUDE_WATCH ? ['./plugins/withWatchApp'] : []),
    ...(INCLUDE_SIRI ? ['./plugins/withIntentsExtension'] : []),
  ];
  if (!plugins.some((plugin) => pluginName(plugin) === 'expo-sharing')) {
    plugins.push('expo-sharing');
  }
  if (!plugins.some((plugin) => pluginName(plugin) === 'expo-media-library')) {
    plugins.push([
      'expo-media-library',
      {
        photosPermission: PHOTO_LIBRARY_USAGE_DESCRIPTION,
        savePhotosPermission: PHOTO_LIBRARY_ADD_USAGE_DESCRIPTION,
        granularPermissions: ['photo'],
      },
    ]);
  }

  return {
  ...config,
  ...(LOCAL_UPDATES_CHANNEL !== undefined ? {
    updates: {
      ...config.updates,
      requestHeaders: {
        ...config.updates?.requestHeaders,
        'expo-channel-name': LOCAL_UPDATES_CHANNEL,
      },
    },
  } : {}),
  ...(IS_ANDROID_INTERNAL ? {
    updates: { ...config.updates, enabled: false },
  } : {}),
  name: IS_ANDROID_INTERNAL ? displayName : config.name ?? '小气候',
  slug: config.slug ?? 'health-pilot',
  plugins,
  ios: {
    ...(config.ios ?? {}),
    ...(IOS_BUILD_NUMBER ? { buildNumber: IOS_BUILD_NUMBER } : {}),
    supportsTablet: IPAD_ENABLED,
    bundleIdentifier: bundleId,
    associatedDomains: Array.from(new Set([
      ...(((config.ios as any)?.associatedDomains ?? []) as string[]),
      ASSOCIATED_DOMAIN,
    ])),
    entitlements: {
      ...((config.ios as any)?.entitlements ?? {}),
      // dev-client 用 ad-hoc provisioning, APNs 走 development token
      'aps-environment': IS_DEV ? 'development' : 'production',
      // HealthKit 在所有 variant 都开 — dev/preview/prod 真机都需要读 HealthKit 验证
      'com.apple.developer.healthkit': true,
    },
    infoPlist: {
      ...baseInfoPlist,
      CFBundleDisplayName: displayName,
      UISupportedInterfaceOrientations: ['UIInterfaceOrientationPortrait'],
      ...(IPAD_ENABLED ? {
        'UISupportedInterfaceOrientations~ipad': IPAD_ORIENTATIONS,
        // Expo's current delegate reads ~pad; UIKit reads the standard ~ipad key.
        'UISupportedInterfaceOrientations~pad': IPAD_ORIENTATIONS,
        UIRequiresFullScreen: false,
      } : {}),
      CFBundleURLTypes: [
        ...baseUrlTypes,
        ...(INCLUDE_ROKID ? [{
          CFBundleURLName: 'Rokid CXR Auth Callback',
          CFBundleURLSchemes: ROKID_CALLBACK_SCHEMES,
        }] : []),
      ],
      ...(INCLUDE_ROKID ? {
        LSApplicationQueriesSchemes: ROKID_QUERY_SCHEMES,
        RokidCXRAuthCallbackScheme: ROKID_CALLBACK_SCHEME,
        NSBluetoothAlwaysUsageDescription:
          '用于连接 Rokid Glasses 并接收用户主动触发的语音、照片和短提示事件',
        NSBluetoothPeripheralUsageDescription:
          '用于连接 Rokid Glasses 并接收用户主动触发的语音、照片和短提示事件',
      } : {}),
      ...((dailyJourney || INCLUDE_ROKID) ? {
        UIBackgroundModes: [...(dailyJourney ? ['location'] : []), ...(INCLUDE_ROKID ? ['bluetooth-central'] : [])],
      } : {}),
      ...(dailyJourney ? {
        NSLocationWhenInUseUsageDescription: JOURNEY_LOCATION_USAGE,
        NSLocationAlwaysAndWhenInUseUsageDescription: JOURNEY_BACKGROUND_USAGE,
      } : {}),
      ...(INCLUDE_SIRI ? {
        NSSiriUsageDescription: '使用 Siri 语音快速记录或分析健康数据',
      } : {}),
      NSPhotoLibraryUsageDescription: PHOTO_LIBRARY_USAGE_DESCRIPTION,
      NSPhotoLibraryAddUsageDescription: PHOTO_LIBRARY_ADD_USAGE_DESCRIPTION,
    },
  },
  android: {
    ...(config.android ?? {}),
    package: androidPackage,
    intentFilters: [
      ...(((config.android as any)?.intentFilters ?? []) as AndroidIntentFilter[]),
      SHARED_LINK_INTENT_FILTER,
      REGISTRATION_INVITE_INTENT_FILTER,
    ],
  },
  extra: {
    ...baseExtra,
    release: {
      variant: VARIANT,
      capabilities: {
        advancedSettings: IS_DEV || IS_PREVIEW,
        // android.config is filtered from Expo's public manifest. Export only
        // the native configuration's presence, never the Maps key itself.
        androidGoogleMapsConfigured: typeof config.android?.config?.googleMaps?.apiKey === 'string'
          && config.android.config.googleMaps.apiKey.trim().length > 0,
        // Legacy automatic city refresh stays disabled in production. The new
        // dailyJourney capability is consumed only by explicit recording sessions.
        backgroundLocation: !IS_ANDROID_INTERNAL && IS_IOS_BUILD && (IS_DEV || IS_PREVIEW),
        dailyJourney,
        rokid: INCLUDE_ROKID,
        siri: INCLUDE_SIRI,
        watch: INCLUDE_WATCH,
      },
    },
    eas: {
      ...baseEas,
      ...(INCLUDE_WATCH ? {
        build: {
          experimental: {
            ios: { appExtensions: WATCH_EXTENSIONS },
          },
        },
      } : {}),
    },
  },
  };
};
