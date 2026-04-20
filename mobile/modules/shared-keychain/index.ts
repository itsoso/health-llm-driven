import { Platform } from 'expo-modules-core';

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
