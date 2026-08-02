import * as SecureStore from 'expo-secure-store';
import type { components as ApiComponents } from '../types/api.generated';
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
import {
  clearPersistedSessionMarker,
  markPersistedSession,
} from './authSessionMarker';
import {
  clearPendingRegistration,
  createPendingRegistration,
  loadPendingRegistration,
  type PendingRegistration,
} from './registrationInviteStorage';

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

export type PhoneVerificationAuthenticated =
  Omit<ApiComponents['schemas']['PhoneVerificationAuthenticated'], 'user'> & {
    user: User;
  };

export type PhoneVerificationInvitationRequired =
  ApiComponents['schemas']['PhoneVerificationInvitationRequired'];

export type PhoneVerificationOutcome =
  | PhoneVerificationAuthenticated
  | PhoneVerificationInvitationRequired;

export type InvitationCredential =
  | { manualCode: string; linkToken?: never }
  | { manualCode?: never; linkToken: string };

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

export interface AuthOperationOptions {
  isCurrent?: () => boolean;
}

class AuthOperationSuperseded extends Error {
  constructor() {
    super('auth operation superseded');
    this.name = 'AuthOperationSuperseded';
  }
}

export function isAuthOperationSuperseded(error: unknown): boolean {
  return error instanceof AuthOperationSuperseded
    || (error as { name?: string } | null)?.name === 'AuthOperationSuperseded';
}

function assertOperationCurrent(options?: AuthOperationOptions): void {
  if (options?.isCurrent && !options.isCurrent()) {
    throw new AuthOperationSuperseded();
  }
}

let authStorageMutation: Promise<unknown> = Promise.resolve();

function serializeAuthStorageMutation<T>(operation: () => Promise<T>): Promise<T> {
  const next = authStorageMutation.then(operation, operation);
  authStorageMutation = next.then(() => undefined, () => undefined);
  return next;
}

async function cleanupCandidateToken(token: string): Promise<void> {
  try {
    if ((await SecureStore.getItemAsync(TOKEN_KEY)) === token) {
      await SecureStore.deleteItemAsync(TOKEN_KEY);
    }
  } catch {
    console.warn('[auth] stale SecureStore token cleanup failed');
  }
  try {
    if ((await readTokenFromSharedKeychain()) === token) {
      await deleteTokenFromSharedKeychain();
    }
  } catch {
    console.warn('[auth] stale shared token cleanup failed');
  }

  let secureRemaining: string | null | undefined;
  let sharedRemaining: string | null | undefined;
  try {
    secureRemaining = await SecureStore.getItemAsync(TOKEN_KEY);
  } catch {
    secureRemaining = undefined;
  }
  try {
    sharedRemaining = await readTokenFromSharedKeychain();
  } catch {
    sharedRemaining = undefined;
  }
  if (
    secureRemaining !== undefined
    && sharedRemaining !== undefined
    && !isUsableNativeAuthToken(secureRemaining)
    && !isUsableNativeAuthToken(sharedRemaining)
  ) {
    await clearPersistedSessionMarker();
  }
}

async function bestEffortClearPendingRegistration(
  options?: AuthOperationOptions,
): Promise<void> {
  if (options?.isCurrent && !options.isCurrent()) return;
  try {
    await clearPendingRegistration();
  } catch {
    console.warn('[auth] pending registration cleanup failed');
  }
}

/**
 * Persist a login token only after at least one native store can read the
 * exact value back. A memory-only login looks successful but disappears on
 * the next process launch, which is worse than an actionable login error.
 */
async function persistTokenWithinMutation(
  token: string,
  options?: AuthOperationOptions,
): Promise<void> {
  if (!isUsableNativeAuthToken(token)) {
    throw new Error('登录服务返回了无效的原生访问凭证');
  }
  assertOperationCurrent(options);
  let durable = false;

  try {
    assertOperationCurrent(options);
    await SecureStore.setItemAsync(TOKEN_KEY, token);
    assertOperationCurrent(options);
    durable = (await SecureStore.getItemAsync(TOKEN_KEY)) === token;
    assertOperationCurrent(options);
    if (!durable) console.warn('[auth] SecureStore token verification failed');
  } catch (error) {
    if (isAuthOperationSuperseded(error)) {
      await cleanupCandidateToken(token);
      throw error;
    }
    console.warn('[auth] SecureStore token persistence failed');
  }

  try {
    assertOperationCurrent(options);
    await saveTokenToSharedKeychain(token);
    assertOperationCurrent(options);
    const sharedToken = await readTokenFromSharedKeychain();
    assertOperationCurrent(options);
    durable = durable || sharedToken === token;
  } catch (error) {
    if (isAuthOperationSuperseded(error)) {
      await cleanupCandidateToken(token);
      throw error;
    }
    if (!durable) console.warn('[auth] shared token persistence failed');
  }

  if (!durable) {
    await cleanupCandidateToken(token);
    throw new Error('登录状态无法安全保存，请解锁设备后重试');
  }

  assertOperationCurrent(options);
  await markPersistedSession();
  assertOperationCurrent(options);
}

async function applyAuthenticatedToken(
  token: string,
  options?: AuthOperationOptions,
): Promise<void> {
  await serializeAuthStorageMutation(async () => {
    try {
      assertOperationCurrent(options);
      await persistTokenWithinMutation(token, options);
      await bestEffortClearPendingRegistration(options);
      assertOperationCurrent(options);
      setRuntimeAuthToken(token);
    } catch (error) {
      if (isAuthOperationSuperseded(error)) {
        await cleanupCandidateToken(token);
      }
      throw error;
    }
  });
}

export async function login(
  username: string,
  password: string,
  options?: AuthOperationOptions,
): Promise<LoginResponse> {
  const { data } = await api.post<LoginResponse>('/auth/login/json', {
    username,
    password,
  });
  assertOperationCurrent(options);
  await applyAuthenticatedToken(data.access_token, options);
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
  options?: AuthOperationOptions,
): Promise<PhoneLoginResponse> {
  const { data } = await api.post<PhoneLoginResponse>('/auth/phone/login', {
    phone,
    code,
  });
  assertOperationCurrent(options);
  await applyAuthenticatedToken(data.access_token, options);
  return data;
}

function isAuthenticatedPhoneOutcome(
  value: PhoneVerificationOutcome,
): value is PhoneVerificationAuthenticated {
  return value.outcome === 'authenticated';
}

export async function verifyPhoneCode(
  phone: string,
  code: string,
  options?: AuthOperationOptions,
): Promise<PhoneVerificationOutcome> {
  const { data } = await api.post<PhoneVerificationOutcome>('/auth/phone/verify', {
    phone,
    code,
  });
  assertOperationCurrent(options);
  if (isAuthenticatedPhoneOutcome(data)) {
    await applyAuthenticatedToken(data.access_token, options);
    return data;
  }
  if (data.outcome !== 'invitation_required') {
    throw new Error('登录服务返回了无法识别的手机号验证结果');
  }
  await serializeAuthStorageMutation(async () => {
    assertOperationCurrent(options);
    await createPendingRegistration({
      verifiedPhoneTicket: data.verified_phone_ticket,
      expiresInSeconds: data.expires_in_seconds,
    });
    try {
      assertOperationCurrent(options);
    } catch (error) {
      await bestEffortClearPendingRegistration();
      throw error;
    }
  });
  return data;
}

function authErrorCode(error: unknown): string | null {
  const code = (
    error as { response?: { data?: { detail?: { code?: unknown } } } } | null
  )?.response?.data?.detail?.code;
  return typeof code === 'string' ? code : null;
}

export async function completeInvitedRegistration(
  credential: InvitationCredential,
  options?: AuthOperationOptions,
): Promise<PhoneLoginResponse> {
  assertOperationCurrent(options);
  const pending = await loadPendingRegistration();
  assertOperationCurrent(options);
  if (!pending) throw new Error('手机号验证已失效，请重新验证');

  const invitation = credential.manualCode !== undefined
    ? { manual_code: credential.manualCode.trim().toUpperCase() }
    : { link_token: credential.linkToken.trim() };
  try {
    const { data } = await api.post<PhoneLoginResponse>('/auth/invited-registration', {
      verified_phone_ticket: pending.verifiedPhoneTicket,
      idempotency_key: pending.idempotencyKey,
      ...invitation,
    });
    assertOperationCurrent(options);
    await applyAuthenticatedToken(data.access_token, options);
    return data;
  } catch (error) {
    if (options?.isCurrent && !options.isCurrent()) {
      throw new AuthOperationSuperseded();
    }
    if (authErrorCode(error) === 'VERIFIED_PHONE_TICKET_EXPIRED') {
      await serializeAuthStorageMutation(async () => {
        await bestEffortClearPendingRegistration(options);
      });
    }
    throw error;
  }
}

export { loadPendingRegistration, type PendingRegistration };

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
  await serializeAuthStorageMutation(async () => {
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
    await clearPersistedSessionMarker();
    await bestEffortClearPendingRegistration();
  });
}

async function hydrateAuthSessionWithinMutation(
  options?: AuthOperationOptions,
): Promise<string | null> {
  let candidate: string | null = null;
  let secureToken: string | null = null;
  try {
    assertOperationCurrent(options);
    secureToken = await SecureStore.getItemAsync(TOKEN_KEY);
    assertOperationCurrent(options);
  } catch (error) {
    if (isAuthOperationSuperseded(error)) throw error;
  }

  if (isUsableNativeAuthToken(secureToken)) {
    candidate = secureToken;
    try {
      assertOperationCurrent(options);
      await saveTokenToSharedKeychain(secureToken);
      assertOperationCurrent(options);
      await readTokenFromSharedKeychain();
      assertOperationCurrent(options);
    } catch (error) {
      if (isAuthOperationSuperseded(error)) throw error;
      console.warn('[auth] shared token hydration failed');
    }
  } else {
    let sharedToken: string | null = null;
    try {
      assertOperationCurrent(options);
      sharedToken = await readTokenFromSharedKeychain();
      assertOperationCurrent(options);
    } catch (error) {
      if (isAuthOperationSuperseded(error)) throw error;
      return null;
    }
    if (!isUsableNativeAuthToken(sharedToken)) return null;
    candidate = sharedToken;
    try {
      assertOperationCurrent(options);
      await SecureStore.setItemAsync(TOKEN_KEY, sharedToken);
      assertOperationCurrent(options);
      await SecureStore.getItemAsync(TOKEN_KEY);
      assertOperationCurrent(options);
    } catch (error) {
      if (isAuthOperationSuperseded(error)) throw error;
      console.warn('[auth] SecureStore token hydration failed');
    }
  }

  assertOperationCurrent(options);
  await markPersistedSession();
  assertOperationCurrent(options);
  setRuntimeAuthToken(candidate);
  return candidate;
}

export async function getToken(
  options?: AuthOperationOptions,
): Promise<string | null> {
  return serializeAuthStorageMutation(
    () => hydrateAuthSessionWithinMutation(options),
  );
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
