import { Platform } from 'expo-modules-core';

// TODO(cross-platform): Android has no native implementation. The noop below
// means widget / app-extension token sharing silently does nothing on Android,
// so any feature that relies on the shared keychain (Siri shortcuts, home
// screen widget) will degrade. When Android is a real release target, mirror
// the iOS SharedKeychainModule with EncryptedSharedPreferences.
const noop = {
  saveToken: async (_token: string) => false,
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

export async function saveTokenToSharedKeychain(token: string): Promise<boolean> {
  return SharedKeychain.saveToken(token);
}

export async function deleteTokenFromSharedKeychain(): Promise<void> {
  return SharedKeychain.deleteToken();
}
