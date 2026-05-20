/**
 * Expo Config Plugin — withHealthKitCleanup
 *
 * react-native-health 的 expo 插件即便 `isClinicalDataEnabled: false` 也会在
 * entitlements 里塞 `com.apple.developer.healthkit.access = []`。空数组对
 * Apple 来说仍是请求 "HealthKit Access (Verifiable Health Records)" 这个独立
 * capability,provisioning profile 必须为该 App ID 单独勾选,否则 build
 * 直接 fail。我们只读基础 HealthKit 数据,不碰临床记录,把这个空 entitlement
 * 删掉即可,只保留 `com.apple.developer.healthkit`。
 *
 * Why: 2026-05-20 EAS dev / production 双双 ERRORED 在
 * "Provisioning profile doesn't include com.apple.developer.healthkit.access"
 *
 * Usage in app.json (放在 react-native-health 之后):
 *   "plugins": [
 *     ["react-native-health", { "isClinicalDataEnabled": false, ... }],
 *     "./plugins/withHealthKitCleanup"
 *   ]
 */
const { withEntitlementsPlist } = require('@expo/config-plugins');

function withHealthKitCleanup(config) {
  return withEntitlementsPlist(config, (mod) => {
    if ('com.apple.developer.healthkit.access' in mod.modResults) {
      delete mod.modResults['com.apple.developer.healthkit.access'];
    }
    return mod;
  });
}

module.exports = withHealthKitCleanup;
