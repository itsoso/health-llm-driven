/**
 * Expo dynamic config — variant 机制让同一个 iPhone 能同时装 production + dev-client.
 *
 * 靠 process.env.APP_VARIANT 切换 bundle ID + 显示名:
 *   - undefined / 'production' → 小巴         (life.executor.health)
 *   - 'development'            → 小巴 Dev     (life.executor.health.dev)
 *   - 'preview'                → 小巴 Preview (life.executor.health.preview)
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
  ? '小巴 Dev'
  : IS_PREVIEW
    ? '小巴 Preview'
    : '小巴';

const androidPackage = bundleId;
const BUNDLE_ROKID_CALLBACK_SCHEME = `${bundleId}.rokid`;
const CONFIGURED_ROKID_CALLBACK_SCHEME = process.env.ROKID_IOS_CALLBACK_SCHEME?.trim();
const ROKID_CALLBACK_SCHEME = CONFIGURED_ROKID_CALLBACK_SCHEME || BUNDLE_ROKID_CALLBACK_SCHEME;
const ROKID_CALLBACK_SCHEMES = Array.from(new Set([
  ROKID_CALLBACK_SCHEME,
  BUNDLE_ROKID_CALLBACK_SCHEME,
]));

export default ({ config }: ConfigContext): ExpoConfig => ({
  ...config,
  name: config.name ?? '小巴',
  slug: config.slug ?? 'health-pilot',
  plugins: [
    ...(config.plugins ?? []),
    ...((config.plugins ?? []).some((plugin) => (
      Array.isArray(plugin) ? plugin[0] === 'expo-sharing' : plugin === 'expo-sharing'
    )) ? [] : ['expo-sharing'] as const),
  ],
  ios: {
    ...(config.ios ?? {}),
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
      ...((config.ios as any)?.infoPlist ?? {}),
      CFBundleDisplayName: displayName,
      LSApplicationQueriesSchemes: Array.from(new Set([
        ...((((config.ios as any)?.infoPlist ?? {}) as any).LSApplicationQueriesSchemes ?? []),
        ...ROKID_QUERY_SCHEMES,
      ])),
      CFBundleURLTypes: [
        ...(((((config.ios as any)?.infoPlist ?? {}) as any).CFBundleURLTypes ?? []) as any[]),
        {
          CFBundleURLName: 'Rokid CXR Auth Callback',
          CFBundleURLSchemes: ROKID_CALLBACK_SCHEMES,
        },
      ],
      RokidCXRAuthCallbackScheme: ROKID_CALLBACK_SCHEME,
      UIBackgroundModes: Array.from(new Set([
        ...(((((config.ios as any)?.infoPlist ?? {}) as any).UIBackgroundModes ?? []) as string[]),
        'bluetooth-central',
      ])),
      NSBluetoothAlwaysUsageDescription:
        '用于连接 Rokid Glasses 并接收用户主动触发的语音、照片和短提示事件',
      NSBluetoothPeripheralUsageDescription:
        '用于连接 Rokid Glasses 并接收用户主动触发的语音、照片和短提示事件',
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
});
