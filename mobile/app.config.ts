/**
 * Expo dynamic config — variant 机制让同一个 iPhone 能同时装 production + dev-client.
 *
 * 靠 process.env.APP_VARIANT 切换 bundle ID + 显示名:
 *   - undefined / 'production' → 小巴健康         (life.executor.health)
 *   - 'development'            → 小巴健康 Dev     (life.executor.health.dev)
 *   - 'preview'                → 小巴健康 Preview (life.executor.health.preview)
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
const INCLUDE_ROKID = process.env.ROKID_IOS_SDK_ENABLED === '1';
const INCLUDE_WATCH = process.env.INCLUDE_WATCH_APP === '1';
const INCLUDE_SIRI = process.env.INCLUDE_SIRI_INTENTS === '1';
const IOS_BUILD_NUMBER = process.env.REVA_IOS_BUILD_NUMBER?.trim();

const BUNDLE_ID_BASE = 'life.executor.health';
const APP_LINK_DOMAIN = 'health.executor.life';
const ASSOCIATED_DOMAIN = `applinks:${APP_LINK_DOMAIN}`;
const APP_OPEN_PATH_PREFIX = '/open/shared';
const ROKID_QUERY_SCHEMES = ['rokidai'];
const PHOTO_LIBRARY_USAGE_DESCRIPTION =
  '用于你主动选择餐盘、补剂标签、检查报告或健康相关图片，生成记录草稿和健康分析';
const PHOTO_LIBRARY_ADD_USAGE_DESCRIPTION = '用于你主动保存健康报告、截图或导出图片到照片图库';
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
const bundleId = IS_DEV
  ? `${BUNDLE_ID_BASE}.dev`
  : IS_PREVIEW
    ? `${BUNDLE_ID_BASE}.preview`
    : BUNDLE_ID_BASE;

const displayName = IS_DEV
  ? '小巴健康 Dev'
  : IS_PREVIEW
    ? '小巴健康 Preview'
    : '小巴健康';

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
  const basePlugins = withoutOptionalNativePlugins(config.plugins);
  const baseInfoPlist = removeKeys((config.ios?.infoPlist ?? {}) as Record<string, any>, [
    'UISupportedInterfaceOrientations~ipad',
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
  name: config.name ?? '小巴健康',
  slug: config.slug ?? 'health-pilot',
  plugins,
  ios: {
    ...(config.ios ?? {}),
    ...(IOS_BUILD_NUMBER ? { buildNumber: IOS_BUILD_NUMBER } : {}),
    supportsTablet: false,
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
        UIBackgroundModes: ['bluetooth-central'],
        NSBluetoothAlwaysUsageDescription:
          '用于连接 Rokid Glasses 并接收用户主动触发的语音、照片和短提示事件',
        NSBluetoothPeripheralUsageDescription:
          '用于连接 Rokid Glasses 并接收用户主动触发的语音、照片和短提示事件',
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
    ],
  },
  extra: {
    ...baseExtra,
    release: {
      variant: VARIANT,
      capabilities: {
        advancedSettings: IS_DEV || IS_PREVIEW,
        backgroundLocation: IS_DEV || IS_PREVIEW,
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
