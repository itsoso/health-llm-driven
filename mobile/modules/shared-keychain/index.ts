import { Platform } from 'expo-modules-core';

const noop = {
  saveToken: async (_token: string) => 0,
  deleteToken: async () => {},
  readToken: async () => null as string | null,
  readDiagnostic: async () => 'native-unavailable',
};

let SharedKeychain = noop;
if (Platform.OS === 'ios') {
  try {
    const { requireNativeModule } = require('expo-modules-core');
    SharedKeychain = requireNativeModule('SharedKeychain');
  } catch {
    // Native module not available
  }
}

export async function saveTokenToSharedKeychain(token: string): Promise<number> {
  const status = await SharedKeychain.saveToken(token);
  if (typeof status === 'number' && status !== 0) {
    throw new Error(`Shared keychain rejected token write (OSStatus ${status})`);
  }
  return status;
}

export async function deleteTokenFromSharedKeychain(): Promise<void> {
  return SharedKeychain.deleteToken();
}

export async function readTokenFromSharedKeychain(): Promise<string | null> {
  const token = await SharedKeychain.readToken();
  return typeof token === 'string' && token.length > 0 ? token : null;
}

/**
 * 主 App 自检: 读回主 App 自己刚写到 App Group 的 marker 和 token。
 * 返回字符串形如 "UD open, marker=..., token=147ch, KC=0"
 * 用来和 Siri extension 的同样读取做对比, 定位跨进程共享是否失效。
 */
export async function readSharedKeychainDiagnostic(): Promise<string> {
  return SharedKeychain.readDiagnostic();
}
