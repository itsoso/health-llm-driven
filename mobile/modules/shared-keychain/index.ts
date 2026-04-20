import { requireNativeModule, Platform } from 'expo-modules-core';

const noop = {
  saveToken: async (_token: string) => false,
  deleteToken: async () => {},
};

const SharedKeychain =
  Platform.OS === 'ios' ? requireNativeModule('SharedKeychain') : noop;

export async function saveTokenToSharedKeychain(token: string): Promise<boolean> {
  return SharedKeychain.saveToken(token);
}

export async function deleteTokenFromSharedKeychain(): Promise<void> {
  return SharedKeychain.deleteToken();
}
