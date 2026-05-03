import { Platform } from 'expo-modules-core';

// TODO(cross-platform): Android has no native implementation. The noop below
// means widget / app-extension token sharing silently does nothing on Android,
// so any feature that relies on the shared keychain (Siri shortcuts, home
// screen widget) will degrade. When Android is a real release target, mirror
// the iOS SharedKeychainModule with EncryptedSharedPreferences.
const noop = {
  saveToken: async (_token: string) => 0,
  deleteToken: async () => {},
};

let SharedKeychain = noop;
if (Platform.OS === 'ios') {
  try {
    const { requireNativeModule } = require('expo-modules-core');
    SharedKeychain = requireNativeModule('SharedKeychain');
  } catch {
    // Native module not available (no Siri/Widget extension built)
  }
}

// Returns OSStatus. 0 = success. Non-zero = error code.
// Notable codes:
//   -34018 errSecMissingEntitlement — keychain-access-groups entitlement 缺失或未生效
//   -25300 errSecItemNotFound        — 删除不存在的条目（delete 前 add 场景忽略即可）
//   -25299 errSecDuplicateItem       — 同名条目已存在（delete-then-add 流程已规避）
export async function saveTokenToSharedKeychain(token: string): Promise<number> {
  return SharedKeychain.saveToken(token);
}

export async function deleteTokenFromSharedKeychain(): Promise<void> {
  return SharedKeychain.deleteToken();
}
