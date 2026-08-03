import AsyncStorage from '@react-native-async-storage/async-storage';

export const AUTH_LOGOUT_TOMBSTONE_KEY = 'auth:logout_tombstone:v1';
const TOMBSTONE_VALUE = '1';

export async function hasAuthLogoutTombstone(): Promise<boolean> {
  try {
    return await AsyncStorage.getItem(AUTH_LOGOUT_TOMBSTONE_KEY) === TOMBSTONE_VALUE;
  } catch {
    throw new Error('无法确认本地登出状态，请稍后重试');
  }
}

export async function writeAuthLogoutTombstone(): Promise<void> {
  try {
    await AsyncStorage.setItem(AUTH_LOGOUT_TOMBSTONE_KEY, TOMBSTONE_VALUE);
    if (await AsyncStorage.getItem(AUTH_LOGOUT_TOMBSTONE_KEY) !== TOMBSTONE_VALUE) {
      throw new Error('readback failed');
    }
  } catch {
    throw new Error('无法安全保存本地登出状态，请稍后重试');
  }
}

export async function clearAuthLogoutTombstone(): Promise<void> {
  try {
    await AsyncStorage.removeItem(AUTH_LOGOUT_TOMBSTONE_KEY);
    if (await AsyncStorage.getItem(AUTH_LOGOUT_TOMBSTONE_KEY) !== null) {
      throw new Error('readback failed');
    }
  } catch {
    throw new Error('无法安全解除本地登出状态，请稍后重试');
  }
}
