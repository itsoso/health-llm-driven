import * as SecureStore from 'expo-secure-store';
import api, { TOKEN_KEY } from './api';
import {
  saveTokenToSharedKeychain,
  deleteTokenFromSharedKeychain,
} from '../modules/shared-keychain';

export interface User {
  id: number;
  username: string;
  email?: string;
  nickname?: string;
  avatar_url?: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export async function login(
  username: string,
  password: string,
): Promise<LoginResponse> {
  const { data } = await api.post<LoginResponse>('/auth/login/json', {
    username,
    password,
  });
  await SecureStore.setItemAsync(TOKEN_KEY, data.access_token);
  saveTokenToSharedKeychain(data.access_token).catch(() => {});
  return data;
}

export async function logout(): Promise<void> {
  await SecureStore.deleteItemAsync(TOKEN_KEY);
  deleteTokenFromSharedKeychain().catch(() => {});
}

export async function getToken(): Promise<string | null> {
  try {
    return await SecureStore.getItemAsync(TOKEN_KEY);
  } catch {
    return null;
  }
}

export async function isLoggedIn(): Promise<boolean> {
  const token = await getToken();
  return token !== null;
}

export async function fetchCurrentUser(): Promise<User> {
  const { data } = await api.get<User>('/auth/me');
  return data;
}

// ── 记住用户名 / 密码 ─────────────────────────────────────────
// 凭据存 SecureStore (iOS Keychain), 与 token 同等安全级别, 绝不明文存 AsyncStorage.
// 仅在用户勾选"记住密码"时写入; 取消勾选 / 登录失败时清除.
const REMEMBER_USERNAME_KEY = 'remember_username';
const REMEMBER_PASSWORD_KEY = 'remember_password';

export interface SavedCredentials {
  username: string;
  password: string;
}

export async function saveCredentials(username: string, password: string): Promise<void> {
  try {
    await SecureStore.setItemAsync(REMEMBER_USERNAME_KEY, username);
    await SecureStore.setItemAsync(REMEMBER_PASSWORD_KEY, password);
  } catch {
    // SecureStore 不可用时静默放弃记忆 (不影响登录本身)
  }
}

export async function loadCredentials(): Promise<SavedCredentials | null> {
  try {
    const username = await SecureStore.getItemAsync(REMEMBER_USERNAME_KEY);
    const password = await SecureStore.getItemAsync(REMEMBER_PASSWORD_KEY);
    if (username && password) return { username, password };
    return null;
  } catch {
    return null;
  }
}

export async function clearCredentials(): Promise<void> {
  try {
    await SecureStore.deleteItemAsync(REMEMBER_USERNAME_KEY);
    await SecureStore.deleteItemAsync(REMEMBER_PASSWORD_KEY);
  } catch {
    // ignore
  }
}
