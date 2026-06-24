import * as SecureStore from 'expo-secure-store';
import api, { TOKEN_KEY } from './api';
import {
  saveTokenToSharedKeychain,
  deleteTokenFromSharedKeychain,
  readTokenFromSharedKeychain,
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
    const token = await SecureStore.getItemAsync(TOKEN_KEY);
    if (token) return token;
  } catch {
    // Fall through to the shared native store. iOS updates can transiently
    // fail SecureStore reads while App Group storage still has the token.
  }

  try {
    const sharedToken = await readTokenFromSharedKeychain();
    if (!sharedToken) return null;

    try {
      await SecureStore.setItemAsync(TOKEN_KEY, sharedToken);
    } catch {
      // Returning the shared token is still better than forcing a logout.
    }
    return sharedToken;
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
// 两层记忆,解耦:
//   - LAST_USERNAME: 每次登录成功**都**记(记住"最后登录的用户"),与"记住密码"无关。
//   - REMEMBER_PASSWORD: 仅勾选"记住密码"时记;取消勾选只清密码,不清用户名。
const LAST_USERNAME_KEY = 'last_username';
const REMEMBER_PASSWORD_KEY = 'remember_password';
const REMEMBER_USERNAME_KEY = 'remember_username'; // 旧键, 仅用于读时迁移兜底

export interface SavedCredentials {
  username: string;
  password: string; // 没记密码时为空串
}

/**
 * 登录成功后持久化。username 总是记(最后登录用户),password 仅 remember=true 时记。
 * 失败不再静默吞(Rule#1):console.warn 暴露,便于排查"记不住"。
 */
export async function saveCredentials(
  username: string,
  password: string,
  remember: boolean,
): Promise<void> {
  try {
    await SecureStore.setItemAsync(LAST_USERNAME_KEY, username);
    if (remember) {
      await SecureStore.setItemAsync(REMEMBER_PASSWORD_KEY, password);
    } else {
      await SecureStore.deleteItemAsync(REMEMBER_PASSWORD_KEY);
    }
  } catch (e) {
    console.warn('[auth] saveCredentials failed (记忆未落盘):', e);
  }
}

export async function loadCredentials(): Promise<SavedCredentials | null> {
  try {
    const username =
      (await SecureStore.getItemAsync(LAST_USERNAME_KEY)) ||
      (await SecureStore.getItemAsync(REMEMBER_USERNAME_KEY)); // 旧版本迁移兜底
    const password = await SecureStore.getItemAsync(REMEMBER_PASSWORD_KEY);
    if (!username && !password) return null;
    return { username: username || '', password: password || '' };
  } catch (e) {
    console.warn('[auth] loadCredentials failed:', e);
    return null;
  }
}

/** 取消"记住密码"时调用:只清密码,保留最后登录用户名。 */
export async function clearCredentials(): Promise<void> {
  try {
    await SecureStore.deleteItemAsync(REMEMBER_PASSWORD_KEY);
  } catch (e) {
    console.warn('[auth] clearCredentials failed:', e);
  }
}
