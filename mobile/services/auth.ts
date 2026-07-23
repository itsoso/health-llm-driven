import * as SecureStore from 'expo-secure-store';
import api, {
  TOKEN_KEY,
  isUsableNativeAuthToken,
  setRuntimeAuthToken,
} from './api';
import {
  saveTokenToSharedKeychain,
  deleteTokenFromSharedKeychain,
  readTokenFromSharedKeychain,
} from '../modules/shared-keychain';

export interface User {
  id: number;
  username?: string;
  email?: string;
  phone?: string;
  phone_verified_at?: string;
  has_password?: boolean;
  nickname?: string;
  avatar_url?: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface PhoneCodeResponse {
  message: string;
  phone: string;
  expires_in_seconds: number;
  dev_code?: string | null;
}

export interface PhoneLoginResponse extends LoginResponse {
  is_new_user: boolean;
}

export interface AccountDeletionRequestResponse {
  status: 'none' | 'requested' | 'processing' | 'completed' | 'rejected';
  user_id: number;
  request_id?: number;
  audit_id?: number | null;
  requested_at?: string;
  completed_at?: string | null;
  due_at?: string | null;
  estimated_completion_days?: number;
  existing?: boolean;
  message?: string;
}

/**
 * 持久化登录 token。永不 throw:后端登录已成功时,存储层瞬时故障
 * (iOS 更新窗口 SecureStore 可能短暂不可用)不应让登录"失败"——
 * 双写 SecureStore + 共享 keychain,全挂也保留内存态并 warn。
 */
async function persistToken(token: string): Promise<void> {
  if (!isUsableNativeAuthToken(token)) {
    setRuntimeAuthToken(null);
    throw new Error('登录服务返回了无效的原生访问凭证');
  }

  // Install synchronously before touching either native store. The
  // authenticated UI can mount immediately after this function resolves, and
  // all of its first requests must already have a reliable bearer token.
  setRuntimeAuthToken(token);

  let secureStoreOk = false;
  try {
    await SecureStore.setItemAsync(TOKEN_KEY, token);
    secureStoreOk = true;
  } catch (e) {
    console.warn('[auth] SecureStore write failed, relying on shared keychain:', e);
  }
  try {
    await saveTokenToSharedKeychain(token);
  } catch (e) {
    if (!secureStoreOk) {
      console.warn('[auth] shared keychain write also failed — 登录态仅存内存,冷启动需重登:', e);
    }
  }
}

export async function login(
  username: string,
  password: string,
): Promise<LoginResponse> {
  const { data } = await api.post<LoginResponse>('/auth/login/json', {
    username,
    password,
  });
  await persistToken(data.access_token);
  return data;
}

export async function requestPhoneCode(
  phone: string,
  purpose: 'login' = 'login',
): Promise<PhoneCodeResponse> {
  const { data } = await api.post<PhoneCodeResponse>('/auth/phone/code', {
    phone,
    purpose,
  });
  return data;
}

export async function loginByPhoneCode(
  phone: string,
  code: string,
): Promise<PhoneLoginResponse> {
  const { data } = await api.post<PhoneLoginResponse>('/auth/phone/login', {
    phone,
    code,
  });
  await persistToken(data.access_token);
  return data;
}

export async function setPassword(newPassword: string): Promise<{ message: string }> {
  const { data } = await api.post<{ message: string }>('/auth/password/set', {
    new_password: newPassword,
  });
  return data;
}

export async function changePassword(
  oldPassword: string,
  newPassword: string,
): Promise<{ message: string }> {
  const { data } = await api.post<{ message: string }>('/auth/password/change', {
    old_password: oldPassword,
    new_password: newPassword,
  });
  return data;
}

export async function logout(): Promise<void> {
  setRuntimeAuthToken(null);
  try {
    await SecureStore.deleteItemAsync(TOKEN_KEY);
  } catch (e) {
    console.warn('[auth] SecureStore token deletion failed:', e);
  }
  try {
    await deleteTokenFromSharedKeychain();
  } catch (e) {
    console.warn('[auth] shared keychain token deletion failed:', e);
  }
}

export async function getToken(): Promise<string | null> {
  try {
    const token = await SecureStore.getItemAsync(TOKEN_KEY);
    if (isUsableNativeAuthToken(token)) {
      setRuntimeAuthToken(token);
      return token;
    }
  } catch {
    // Fall through to the shared native store. iOS updates can transiently
    // fail SecureStore reads while App Group storage still has the token.
  }

  try {
    const sharedToken = await readTokenFromSharedKeychain();
    if (!isUsableNativeAuthToken(sharedToken)) return null;

    setRuntimeAuthToken(sharedToken);
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

export async function requestAccountDeletion(): Promise<AccountDeletionRequestResponse> {
  const { data } = await api.post<AccountDeletionRequestResponse>('/auth/me/deletion-request');
  return data;
}

export async function getAccountDeletionRequest(): Promise<AccountDeletionRequestResponse> {
  const { data } = await api.get<AccountDeletionRequestResponse>('/auth/me/deletion-request');
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
