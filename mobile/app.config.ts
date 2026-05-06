/**
 * Expo dynamic config — variant 机制让同一个 iPhone 能同时装 production + dev-client.
 *
 * 靠 process.env.APP_VARIANT 切换 bundle ID + 显示名:
 *   - undefined / 'production' → 健康助理    (life.executor.health)
 *   - 'development'            → 健康助理 Dev (life.executor.health.dev)
 *   - 'preview'                → 健康助理 Preview (life.executor.health.preview)
 *
 * APP_VARIANT 在 eas.json 各 profile 的 env 里设置。
 *
 * app.json 仍在, 作为默认值;本文件只差量覆盖 variant 敏感字段。
 */
import { ExpoConfig, ConfigContext } from 'expo/config';

const VARIANT = process.env.APP_VARIANT ?? 'production';
const IS_DEV = VARIANT === 'development';
const IS_PREVIEW = VARIANT === 'preview';

const BUNDLE_ID_BASE = 'life.executor.health';
const bundleId = IS_DEV
  ? `${BUNDLE_ID_BASE}.dev`
  : IS_PREVIEW
    ? `${BUNDLE_ID_BASE}.preview`
    : BUNDLE_ID_BASE;

const displayName = IS_DEV
  ? '健康助理 Dev'
  : IS_PREVIEW
    ? '健康助理 Preview'
    : '健康助理';

const androidPackage = bundleId;

export default ({ config }: ConfigContext): ExpoConfig => ({
  ...config,
  name: config.name ?? 'HealthPilot',
  slug: config.slug ?? 'health-pilot',
  ios: {
    ...(config.ios ?? {}),
    bundleIdentifier: bundleId,
    entitlements: {
      ...((config.ios as any)?.entitlements ?? {}),
      // dev-client 用 ad-hoc provisioning, APNs 走 development token
      'aps-environment': IS_DEV ? 'development' : 'production',
    },
    infoPlist: {
      ...((config.ios as any)?.infoPlist ?? {}),
      CFBundleDisplayName: displayName,
    },
  },
  android: {
    ...(config.android ?? {}),
    package: androidPackage,
  },
});
