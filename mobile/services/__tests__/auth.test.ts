/* eslint-disable import/first */
/**
 * services/auth.ts unit tests.
 *
 * Why this file matters: every authenticated API call depends on the token
 * stored by `login()`. Breaking any of these breaks everything downstream
 * (dashboard, chat, alerts, records). Covered here as the auth primitives
 * were untested before Phase 5.
 */

// Mock api with an explicit factory — auto-mock evaluates the real axios
// module, which crashes under jest+expo-streams at import time.
jest.mock('../api', () => ({
  __esModule: true,
  default: {
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
    delete: jest.fn(),
  },
  TOKEN_KEY: 'auth_token',
  setOnUnauthorized: jest.fn(),
  setRuntimeAuthToken: jest.fn(),
  isUsableNativeAuthToken: (token: string | null | undefined) => (
    Boolean(token && token !== '__web_cookie_session__')
  ),
}));

jest.mock('../../modules/shared-keychain', () => ({
  saveTokenToSharedKeychain: jest.fn().mockResolvedValue(0),
  deleteTokenFromSharedKeychain: jest.fn().mockResolvedValue(undefined),
  readTokenFromSharedKeychain: jest.fn().mockResolvedValue(null),
}));

import {
  login, logout, getToken, isLoggedIn, fetchCurrentUser,
  requestPhoneCode, loginByPhoneCode, setPassword, changePassword,
  verifyPhoneCode, completeInvitedRegistration,
  saveCredentials, loadCredentials, clearCredentials,
  type PhoneLoginResponse,
} from '../auth';
import api, { TOKEN_KEY, setRuntimeAuthToken } from '../api';
import * as SecureStore from 'expo-secure-store';
import AsyncStorage from '@react-native-async-storage/async-storage';
import {
  hasPersistedSessionMarker,
  markPersistedSession,
} from '../authSessionMarker';
import {
  saveTokenToSharedKeychain,
  deleteTokenFromSharedKeychain,
  readTokenFromSharedKeychain,
} from '../../modules/shared-keychain';

const mockedApi = api as jest.Mocked<typeof api>;
const mockedSave = saveTokenToSharedKeychain as jest.MockedFunction<typeof saveTokenToSharedKeychain>;
const mockedDelete = deleteTokenFromSharedKeychain as jest.MockedFunction<typeof deleteTokenFromSharedKeychain>;
const mockedReadShared = readTokenFromSharedKeychain as jest.MockedFunction<typeof readTokenFromSharedKeychain>;
const mockedSetRuntimeToken = setRuntimeAuthToken as jest.MockedFunction<typeof setRuntimeAuthToken>;

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

async function waitForApiPost(): Promise<void> {
  for (let attempt = 0; attempt < 10; attempt += 1) {
    if (mockedApi.post.mock.calls.length > 0) return;
    await Promise.resolve();
  }
  throw new Error('API post was not called');
}

describe('services/auth', () => {
  let secureItems: Record<string, string>;

  beforeEach(async () => {
    jest.clearAllMocks();
    await AsyncStorage.clear();
    secureItems = {};
    (SecureStore.setItemAsync as jest.Mock).mockImplementation(
      async (key: string, value: string) => {
        secureItems[key] = value;
      },
    );
    (SecureStore.getItemAsync as jest.Mock).mockImplementation(
      async (key: string) => secureItems[key] ?? null,
    );
    (SecureStore.deleteItemAsync as jest.Mock).mockImplementation(
      async (key: string) => {
        delete secureItems[key];
      },
    );
    mockedSave.mockResolvedValue(0);
    mockedDelete.mockResolvedValue(undefined);
    mockedReadShared.mockResolvedValue(null);
  });

  describe('login', () => {
    it('stores token in SecureStore and forwards to shared keychain on success', async () => {
      secureItems.pending_invited_registration_v1 = JSON.stringify({ version: 1 });
      mockedApi.post.mockResolvedValueOnce({
        data: {
          access_token: 'tok_abc',
          token_type: 'bearer',
          user: { id: 7, username: 'alice' },
        },
      } as never);

      const result = await login('alice', 'hunter2');

      expect(mockedApi.post).toHaveBeenCalledWith('/auth/login/json', {
        username: 'alice',
        password: 'hunter2',
      });
      expect(SecureStore.setItemAsync).toHaveBeenCalledWith(TOKEN_KEY, 'tok_abc');
      expect(mockedSave).toHaveBeenCalledWith('tok_abc');
      expect(mockedSetRuntimeToken).toHaveBeenCalledWith('tok_abc');
      expect((SecureStore.getItemAsync as jest.Mock).mock.invocationCallOrder[0])
        .toBeLessThan(mockedSetRuntimeToken.mock.invocationCallOrder[0]);
      expect(mockedReadShared.mock.invocationCallOrder[0])
        .toBeLessThan(mockedSetRuntimeToken.mock.invocationCallOrder[0]);
      expect(result.user.username).toBe('alice');
      expect(secureItems.pending_invited_registration_v1).toBeUndefined();
    });

    it('propagates API errors without touching storage', async () => {
      mockedApi.post.mockRejectedValueOnce(new Error('401 Unauthorized'));

      await expect(login('alice', 'wrong')).rejects.toThrow('401 Unauthorized');
      expect(SecureStore.setItemAsync).not.toHaveBeenCalled();
      expect(mockedSave).not.toHaveBeenCalled();
    });

    it('ignores shared-keychain failure silently (iOS-only module)', async () => {
      mockedApi.post.mockResolvedValueOnce({
        data: {
          access_token: 'tok_abc',
          token_type: 'bearer',
          user: { id: 7, username: 'alice' },
        },
      } as never);
      mockedSave.mockRejectedValueOnce(new Error('native module missing'));

      await expect(login('alice', 'hunter2')).resolves.toBeDefined();
      expect(mockedSetRuntimeToken).toHaveBeenCalledWith('tok_abc');
      expect(SecureStore.setItemAsync).toHaveBeenCalled();
    });

    it('登录仍成功当 SecureStore 写失败 — 降级共享 keychain,存储故障不否定已成功的登录', async () => {
      mockedApi.post.mockResolvedValueOnce({
        data: {
          access_token: 'tok_fallback',
          token_type: 'bearer',
          user: { id: 7, username: 'alice' },
        },
      } as never);
      (SecureStore.setItemAsync as jest.Mock).mockRejectedValueOnce(
        new Error('keychain transiently locked'),
      );
      mockedReadShared.mockResolvedValue('tok_fallback');

      await expect(login('alice', 'hunter2')).resolves.toBeDefined();
      expect(mockedSetRuntimeToken).toHaveBeenCalledWith('tok_fallback');
      expect(mockedSave).toHaveBeenCalledWith('tok_fallback');
    });

    it('rejects false login success when neither secure store can read the token back', async () => {
      mockedApi.post.mockResolvedValueOnce({
        data: {
          access_token: 'tok_memory_only',
          token_type: 'bearer',
          user: { id: 7, username: 'alice' },
        },
      } as never);
      (SecureStore.setItemAsync as jest.Mock).mockRejectedValueOnce(new Error('locked'));
      mockedSave.mockRejectedValueOnce(new Error('no module'));

      await expect(login('alice', 'hunter2')).rejects.toThrow('登录状态无法安全保存');
      expect(mockedSetRuntimeToken).not.toHaveBeenCalledWith('tok_memory_only');
    });

    it('does not accept a resolved shared-keychain write until the same token is readable', async () => {
      mockedApi.post.mockResolvedValueOnce({
        data: {
          access_token: 'tok_unreadable',
          token_type: 'bearer',
          user: { id: 7, username: 'alice' },
        },
      } as never);
      (SecureStore.setItemAsync as jest.Mock).mockRejectedValue(new Error('locked'));
      mockedSave.mockResolvedValue(0);
      mockedReadShared.mockResolvedValue(null);

      await expect(login('alice', 'hunter2')).rejects.toThrow('登录状态无法安全保存');
    });

    it('keeps pending registration when token persistence fails', async () => {
      const pending = JSON.stringify({
        version: 1,
        verifiedPhoneTicket: 'T'.repeat(32),
        expiresAt: Date.now() + 300_000,
        idempotencyKey: 'registration-1234567890abcdef',
      });
      secureItems.pending_invited_registration_v1 = pending;
      mockedApi.post.mockResolvedValueOnce({
        data: {
          access_token: 'tok_failed',
          token_type: 'bearer',
          user: { id: 7, username: 'alice' },
        },
      } as never);
      (SecureStore.setItemAsync as jest.Mock).mockRejectedValueOnce(new Error('locked'));
      mockedSave.mockRejectedValueOnce(new Error('shared unavailable'));

      await expect(login('alice', 'hunter2')).rejects.toThrow('登录状态无法安全保存');
      expect(secureItems.pending_invited_registration_v1).toBe(pending);
    });

    it('authenticates when pending cleanup fails after durable token persistence', async () => {
      secureItems.pending_invited_registration_v1 = JSON.stringify({ version: 1 });
      mockedApi.post.mockResolvedValueOnce({
        data: {
          access_token: 'tok_cleanup_retry',
          token_type: 'bearer',
          user: { id: 7, username: 'alice' },
        },
      } as never);
      (SecureStore.deleteItemAsync as jest.Mock).mockRejectedValueOnce(new Error('locked'));

      await expect(login('alice', 'hunter2')).resolves.toBeDefined();
      expect(secureItems.auth_token).toBe('tok_cleanup_retry');
      expect(mockedSetRuntimeToken).toHaveBeenCalledWith('tok_cleanup_retry');
    });
  });

  describe('phone auth', () => {
    it('requests a phone login code', async () => {
      mockedApi.post.mockResolvedValueOnce({
        data: {
          message: '验证码已发送',
          phone: '+8613800138000',
          expires_in_seconds: 300,
          dev_code: '123456',
        },
      } as never);

      const result = await requestPhoneCode('13800138000');

      expect(mockedApi.post).toHaveBeenCalledWith('/auth/phone/code', {
        phone: '13800138000',
        purpose: 'login',
      });
      expect(result.dev_code).toBe('123456');
    });

    it('logs in by phone code and stores the returned token', async () => {
      mockedApi.post.mockResolvedValueOnce({
        data: {
          access_token: 'tok_phone',
          token_type: 'bearer',
          is_new_user: true,
          user: { id: 8, username: 'phone_8', phone: '+8613800138000' },
        },
      } as never);

      const result = await loginByPhoneCode('13800138000', '123456');

      expect(mockedApi.post).toHaveBeenCalledWith('/auth/phone/login', {
        phone: '13800138000',
        code: '123456',
      });
      expect(SecureStore.setItemAsync).toHaveBeenCalledWith(TOKEN_KEY, 'tok_phone');
      expect(mockedSave).toHaveBeenCalledWith('tok_phone');
      expect(mockedSetRuntimeToken).toHaveBeenCalledWith('tok_phone');
      expect(result.is_new_user).toBe(true);
    });

    it('returns an authenticated outcome only after its token is durable', async () => {
      mockedApi.post.mockResolvedValueOnce({
        data: {
          outcome: 'authenticated',
          access_token: 'tok_verified',
          token_type: 'bearer',
          is_new_user: false,
          user: { id: 8, username: 'phone_8' },
        },
      } as never);

      const result = await verifyPhoneCode('13800138000', '123456');

      expect(mockedApi.post).toHaveBeenCalledWith('/auth/phone/verify', {
        phone: '13800138000',
        code: '123456',
      });
      expect(result.outcome).toBe('authenticated');
      expect(SecureStore.setItemAsync).toHaveBeenCalledWith(TOKEN_KEY, 'tok_verified');
      expect(mockedSetRuntimeToken).toHaveBeenLastCalledWith('tok_verified');
    });

    it('creates only a secure pending registration for an unknown verified phone', async () => {
      mockedApi.post.mockResolvedValueOnce({
        data: {
          outcome: 'invitation_required',
          verified_phone_ticket: 'T'.repeat(32),
          expires_in_seconds: 300,
        },
      } as never);

      const result = await verifyPhoneCode('13800138000', '123456');

      expect(result.outcome).toBe('invitation_required');
      expect(secureItems.auth_token).toBeUndefined();
      expect(mockedSave).not.toHaveBeenCalled();
      const stored = JSON.parse(secureItems.pending_invited_registration_v1);
      expect(stored.verifiedPhoneTicket).toBe('T'.repeat(32));
      expect(stored.idempotencyKey).toMatch(/^registration-/);
    });

    it('does not report invitation-required when pending state cannot be persisted', async () => {
      mockedApi.post.mockResolvedValueOnce({
        data: {
          outcome: 'invitation_required',
          verified_phone_ticket: 'T'.repeat(32),
          expires_in_seconds: 300,
        },
      } as never);
      (SecureStore.getItemAsync as jest.Mock).mockResolvedValue(null);

      await expect(verifyPhoneCode('13800138000', '123456'))
        .rejects.toThrow('待注册状态无法安全保存');
      expect(mockedSetRuntimeToken).not.toHaveBeenCalledWith(expect.any(String));
    });

    it('completes invited registration without persisting the invitation credential', async () => {
      secureItems.pending_invited_registration_v1 = JSON.stringify({
        version: 1,
        verifiedPhoneTicket: 'T'.repeat(32),
        expiresAt: Date.now() + 300_000,
        idempotencyKey: 'registration-1234567890abcdef',
      });
      mockedApi.post.mockResolvedValueOnce({
        data: {
          access_token: 'tok_invited',
          token_type: 'bearer',
          is_new_user: true,
          user: { id: 9, username: 'phone_9' },
        },
      } as never);

      const result = await completeInvitedRegistration({ manualCode: 'ABCD1234' });

      expect(mockedApi.post).toHaveBeenCalledWith('/auth/invited-registration', {
        verified_phone_ticket: 'T'.repeat(32),
        idempotency_key: 'registration-1234567890abcdef',
        manual_code: 'ABCD1234',
      });
      expect(result.access_token).toBe('tok_invited');
      expect(secureItems.auth_token).toBe('tok_invited');
      expect(secureItems.pending_invited_registration_v1).toBeUndefined();
      expect(JSON.stringify(secureItems)).not.toContain('ABCD1234');
    });

    it('keeps pending state for a correctable invitation error', async () => {
      const pending = JSON.stringify({
        version: 1,
        verifiedPhoneTicket: 'T'.repeat(32),
        expiresAt: Date.now() + 300_000,
        idempotencyKey: 'registration-1234567890abcdef',
      });
      secureItems.pending_invited_registration_v1 = pending;
      mockedApi.post.mockRejectedValueOnce({
        response: { data: { detail: { code: 'INVITATION_PHONE_MISMATCH' } } },
      });

      await expect(completeInvitedRegistration({ linkToken: 'L'.repeat(32) })).rejects.toBeDefined();
      expect(secureItems.pending_invited_registration_v1).toBe(pending);
    });

    it('clears pending state when the verified phone ticket has expired', async () => {
      secureItems.pending_invited_registration_v1 = JSON.stringify({
        version: 1,
        verifiedPhoneTicket: 'T'.repeat(32),
        expiresAt: Date.now() + 300_000,
        idempotencyKey: 'registration-1234567890abcdef',
      });
      mockedApi.post.mockRejectedValueOnce({
        response: { data: { detail: { code: 'VERIFIED_PHONE_TICKET_EXPIRED' } } },
      });

      await expect(completeInvitedRegistration({ manualCode: 'ABCD1234' })).rejects.toBeDefined();
      expect(secureItems.pending_invited_registration_v1).toBeUndefined();
    });

    it('does not apply a stale invitation-required response after logout supersedes it', async () => {
      const response = deferred<{ data: {
        outcome: 'invitation_required';
        verified_phone_ticket: string;
        expires_in_seconds: number;
      } }>();
      let current = true;
      mockedApi.post.mockReturnValueOnce(response.promise as never);

      const verification = verifyPhoneCode(
        '13800138000',
        '123456',
        { isCurrent: () => current },
      );
      current = false;
      response.resolve({
        data: {
          outcome: 'invitation_required',
          verified_phone_ticket: 'T'.repeat(32),
          expires_in_seconds: 300,
        },
      });

      await expect(verification).rejects.toMatchObject({ name: 'AuthOperationSuperseded' });
      expect(secureItems.pending_invited_registration_v1).toBeUndefined();
      expect(secureItems.auth_token).toBeUndefined();
    });

    it('cleans a stale token write without exposing it to runtime auth', async () => {
      let current = true;
      const writeStarted = deferred<void>();
      const releaseWrite = deferred<void>();
      mockedApi.post.mockResolvedValueOnce({
        data: {
          outcome: 'authenticated',
          access_token: 'tok_stale',
          token_type: 'bearer',
          is_new_user: false,
          user: { id: 8, username: 'phone_8' },
        },
      } as never);
      (SecureStore.setItemAsync as jest.Mock).mockImplementationOnce(async (key, value) => {
        secureItems[key] = value;
        writeStarted.resolve();
        await releaseWrite.promise;
      });

      const verification = verifyPhoneCode(
        '13800138000',
        '123456',
        { isCurrent: () => current },
      );
      await writeStarted.promise;
      current = false;
      releaseWrite.resolve();

      await expect(verification).rejects.toMatchObject({ name: 'AuthOperationSuperseded' });
      expect(secureItems.auth_token).toBeUndefined();
      expect(mockedSetRuntimeToken).not.toHaveBeenCalledWith('tok_stale');
    });

    it('does not apply a stale invited-registration success after logout supersedes it', async () => {
      secureItems.pending_invited_registration_v1 = JSON.stringify({
        version: 1,
        verifiedPhoneTicket: 'T'.repeat(32),
        expiresAt: Date.now() + 300_000,
        idempotencyKey: 'registration-1234567890abcdef',
      });
      const response = deferred<{ data: PhoneLoginResponse }>();
      let current = true;
      mockedApi.post.mockReturnValueOnce(response.promise as never);

      const completion = completeInvitedRegistration(
        { manualCode: 'ABCD2345' },
        { isCurrent: () => current },
      );
      await waitForApiPost();
      current = false;
      response.resolve({
        data: {
          access_token: 'tok_stale_complete',
          token_type: 'bearer',
          is_new_user: true,
          user: { id: 9, username: 'phone_9' },
        },
      });

      await expect(completion).rejects.toMatchObject({ name: 'AuthOperationSuperseded' });
      expect(secureItems.auth_token).toBeUndefined();
      expect(secureItems.pending_invited_registration_v1).toBeDefined();
    });

    it.each(['legacy_phone', 'verified_phone', 'invited_completion'] as const)(
      '%s preserves pending registration when durable token persistence fails',
      async (flow) => {
        const pending = JSON.stringify({
          version: 1,
          verifiedPhoneTicket: 'T'.repeat(32),
          expiresAt: Date.now() + 300_000,
          idempotencyKey: 'registration-1234567890abcdef',
        });
        secureItems.pending_invited_registration_v1 = pending;
        const base = {
          access_token: `tok_failed_${flow}`,
          token_type: 'bearer',
          is_new_user: flow === 'invited_completion',
          user: { id: 11, username: 'phone_11' },
        };
        mockedApi.post.mockResolvedValueOnce({
          data: flow === 'verified_phone'
            ? { ...base, outcome: 'authenticated' }
            : base,
        } as never);
        (SecureStore.setItemAsync as jest.Mock).mockRejectedValueOnce(new Error('locked'));
        mockedSave.mockRejectedValueOnce(new Error('shared unavailable'));

        const operation = flow === 'legacy_phone'
          ? loginByPhoneCode('13800138000', '123456')
          : flow === 'verified_phone'
            ? verifyPhoneCode('13800138000', '123456')
            : completeInvitedRegistration({ manualCode: 'ABCD2345' });

        await expect(operation).rejects.toThrow('登录状态无法安全保存');
        expect(secureItems.pending_invited_registration_v1).toBe(pending);
      },
    );

    it.each(['legacy_phone', 'verified_phone', 'invited_completion'] as const)(
      '%s authenticates after durable token even when pending cleanup must retry',
      async (flow) => {
        secureItems.pending_invited_registration_v1 = JSON.stringify({
          version: 1,
          verifiedPhoneTicket: 'T'.repeat(32),
          expiresAt: Date.now() + 300_000,
          idempotencyKey: 'registration-1234567890abcdef',
        });
        const token = `tok_cleanup_${flow}`;
        const base = {
          access_token: token,
          token_type: 'bearer',
          is_new_user: flow === 'invited_completion',
          user: { id: 12, username: 'phone_12' },
        };
        mockedApi.post.mockResolvedValueOnce({
          data: flow === 'verified_phone'
            ? { ...base, outcome: 'authenticated' }
            : base,
        } as never);
        (SecureStore.deleteItemAsync as jest.Mock).mockRejectedValueOnce(new Error('locked'));

        const operation = flow === 'legacy_phone'
          ? loginByPhoneCode('13800138000', '123456')
          : flow === 'verified_phone'
            ? verifyPhoneCode('13800138000', '123456')
            : completeInvitedRegistration({ manualCode: 'ABCD2345' });

        await expect(operation).resolves.toBeDefined();
        expect(secureItems.auth_token).toBe(token);
        expect(mockedSetRuntimeToken).toHaveBeenCalledWith(token);
        const tokenReadIndex = (SecureStore.getItemAsync as jest.Mock).mock.calls
          .findIndex(([key]) => key === TOKEN_KEY);
        expect(tokenReadIndex).toBeGreaterThanOrEqual(0);
        expect((SecureStore.getItemAsync as jest.Mock).mock.invocationCallOrder[tokenReadIndex])
          .toBeLessThan((SecureStore.deleteItemAsync as jest.Mock).mock.invocationCallOrder[0]);
      },
    );
  });

  describe('password management', () => {
    it('sets an initial password for phone-first accounts', async () => {
      mockedApi.post.mockResolvedValueOnce({ data: { message: '密码设置成功' } } as never);

      await expect(setPassword('new-passphrase')).resolves.toEqual({ message: '密码设置成功' });
      expect(mockedApi.post).toHaveBeenCalledWith('/auth/password/set', { new_password: 'new-passphrase' });
    });

    it('changes an existing password', async () => {
      mockedApi.post.mockResolvedValueOnce({ data: { message: '密码修改成功' } } as never);

      await expect(changePassword('old-passphrase', 'new-passphrase')).resolves.toEqual({ message: '密码修改成功' });
      expect(mockedApi.post).toHaveBeenCalledWith('/auth/password/change', {
        old_password: 'old-passphrase',
        new_password: 'new-passphrase',
      });
    });
  });

  describe('logout', () => {
    it('clears SecureStore and shared keychain', async () => {
      secureItems.pending_invited_registration_v1 = '{"version":1}';
      await logout();
      expect(mockedSetRuntimeToken).toHaveBeenCalledWith(null);
      expect(SecureStore.deleteItemAsync).toHaveBeenCalledWith(TOKEN_KEY);
      expect(mockedDelete).toHaveBeenCalled();
      expect(secureItems.pending_invited_registration_v1).toBeUndefined();
    });

    it('ignores keychain clearing failure', async () => {
      mockedDelete.mockRejectedValueOnce(new Error('no module'));
      await expect(logout()).resolves.toBeUndefined();
    });

    it('serializes token storage so an old logout cannot erase a newer login', async () => {
      const deleteGate: { release?: () => void } = {};
      let storedToken: string | null = 'tok_old';
      (SecureStore.deleteItemAsync as jest.Mock).mockImplementationOnce(
        () => new Promise<void>((resolve) => {
          deleteGate.release = () => {
            storedToken = null;
            resolve();
          };
        }),
      );
      (SecureStore.setItemAsync as jest.Mock).mockImplementation(
        async (_key: string, value: string) => {
          storedToken = value;
        },
      );
      (SecureStore.getItemAsync as jest.Mock).mockImplementation(
        async () => storedToken,
      );
      mockedApi.post.mockResolvedValueOnce({
        data: {
          access_token: 'tok_new',
          token_type: 'bearer',
          user: { id: 8, username: 'new-user' },
        },
      } as never);

      const logoutPromise = logout();
      await Promise.resolve();
      expect(deleteGate.release).toBeDefined();

      const loginPromise = login('new-user', 'hunter2');
      await Promise.resolve();
      deleteGate.release?.();
      await Promise.all([logoutPromise, loginPromise]);

      expect(storedToken).toBe('tok_new');
    });
  });

  describe('getToken / isLoggedIn', () => {
    it('returns the stored token', async () => {
      (SecureStore.getItemAsync as jest.Mock).mockResolvedValueOnce('tok_xyz');
      await expect(getToken()).resolves.toBe('tok_xyz');
      expect(mockedSetRuntimeToken).toHaveBeenCalledWith('tok_xyz');
    });

    it('returns null when SecureStore throws', async () => {
      (SecureStore.getItemAsync as jest.Mock).mockRejectedValueOnce(
        new Error('SecureStore unavailable'),
      );
      await expect(getToken()).resolves.toBeNull();
    });

    it('does not restore the web cookie session sentinel as a native bearer token', async () => {
      (SecureStore.getItemAsync as jest.Mock).mockResolvedValueOnce('__web_cookie_session__');
      mockedReadShared.mockResolvedValueOnce(null);

      await expect(getToken()).resolves.toBeNull();
      expect(mockedSetRuntimeToken).not.toHaveBeenCalledWith('__web_cookie_session__');
    });

    it('falls back to shared keychain and rehydrates SecureStore when token is missing', async () => {
      (SecureStore.getItemAsync as jest.Mock).mockResolvedValueOnce(null);
      mockedReadShared.mockResolvedValueOnce('tok_shared');

      await expect(getToken()).resolves.toBe('tok_shared');

      expect(mockedReadShared).toHaveBeenCalledTimes(1);
      expect(mockedSetRuntimeToken).toHaveBeenCalledWith('tok_shared');
      expect(SecureStore.setItemAsync).toHaveBeenCalledWith(TOKEN_KEY, 'tok_shared');
    });

    it('falls back to shared keychain when SecureStore read throws', async () => {
      (SecureStore.getItemAsync as jest.Mock).mockRejectedValueOnce(
        new Error('SecureStore unavailable during update'),
      );
      mockedReadShared.mockResolvedValueOnce('tok_shared_after_error');

      await expect(getToken()).resolves.toBe('tok_shared_after_error');

      expect(mockedReadShared).toHaveBeenCalledTimes(1);
      expect(SecureStore.setItemAsync).toHaveBeenCalledWith(TOKEN_KEY, 'tok_shared_after_error');
    });

    it('isLoggedIn reflects token presence', async () => {
      (SecureStore.getItemAsync as jest.Mock).mockResolvedValueOnce('tok');
      await expect(isLoggedIn()).resolves.toBe(true);

      (SecureStore.getItemAsync as jest.Mock).mockResolvedValueOnce(null);
      await expect(isLoggedIn()).resolves.toBe(false);
    });

    it('queues a newer login behind stale candidate cleanup and preserves the new marker', async () => {
      let current = true;
      const writeStarted = deferred<void>();
      const releaseWrite = deferred<void>();
      const cleanupReadStarted = deferred<void>();
      const releaseCleanupRead = deferred<void>();
      let setCalls = 0;
      let getCalls = 0;
      (SecureStore.setItemAsync as jest.Mock).mockImplementation(async (key, value) => {
        secureItems[key] = value;
        setCalls += 1;
        if (setCalls === 1) {
          writeStarted.resolve();
          await releaseWrite.promise;
        }
      });
      (SecureStore.getItemAsync as jest.Mock).mockImplementation(async (key) => {
        getCalls += 1;
        if (getCalls === 1) {
          cleanupReadStarted.resolve();
          await releaseCleanupRead.promise;
        }
        return secureItems[key] ?? null;
      });
      mockedApi.post
        .mockResolvedValueOnce({
          data: {
            outcome: 'authenticated',
            access_token: 'tok_A',
            token_type: 'bearer',
            is_new_user: false,
            user: { id: 21, username: 'old' },
          },
        } as never)
        .mockResolvedValueOnce({
          data: {
            access_token: 'tok_B',
            token_type: 'bearer',
            user: { id: 22, username: 'new' },
          },
        } as never);

      const stale = verifyPhoneCode('13800138000', '123456', {
        isCurrent: () => current,
      });
      await writeStarted.promise;
      current = false;
      releaseWrite.resolve();
      await cleanupReadStarted.promise;
      const newer = login('new', 'hunter2');
      releaseCleanupRead.resolve();

      await expect(stale).rejects.toMatchObject({ name: 'AuthOperationSuperseded' });
      await expect(newer).resolves.toBeDefined();
      expect(secureItems[TOKEN_KEY]).toBe('tok_B');
      expect(await hasPersistedSessionMarker()).toBe(true);
      expect(mockedSetRuntimeToken).toHaveBeenLastCalledWith('tok_B');
    });

    it('does not let an old SecureStore hydration revive auth after logout', async () => {
      secureItems[TOKEN_KEY] = 'tok_old_hydration';
      let sharedToken: string | null = null;
      let current = true;
      const sharedSaveStarted = deferred<void>();
      const releaseSharedSave = deferred<void>();
      mockedSave.mockImplementation(async (token) => {
        sharedToken = token;
        sharedSaveStarted.resolve();
        await releaseSharedSave.promise;
        return 0;
      });
      mockedReadShared.mockImplementation(async () => sharedToken);
      mockedDelete.mockImplementation(async () => {
        sharedToken = null;
      });

      const hydration = getToken({ isCurrent: () => current });
      await sharedSaveStarted.promise;
      expect(mockedSave).toHaveBeenCalledWith('tok_old_hydration');
      current = false;
      const loggingOut = logout();
      releaseSharedSave.resolve();

      await expect(hydration).rejects.toMatchObject({ name: 'AuthOperationSuperseded' });
      await loggingOut;
      expect(secureItems[TOKEN_KEY]).toBeUndefined();
      expect(sharedToken).toBeNull();
      expect(await hasPersistedSessionMarker()).toBe(false);
      expect(mockedSetRuntimeToken).toHaveBeenLastCalledWith(null);
    });

    it('serializes shared-to-SecureStore self-heal with logout', async () => {
      let sharedToken: string | null = 'tok_shared_old';
      let current = true;
      const secureWriteStarted = deferred<void>();
      const releaseSecureWrite = deferred<void>();
      mockedReadShared.mockImplementation(async () => sharedToken);
      mockedDelete.mockImplementation(async () => {
        sharedToken = null;
      });
      (SecureStore.setItemAsync as jest.Mock).mockImplementationOnce(async (key, value) => {
        secureItems[key] = value;
        secureWriteStarted.resolve();
        await releaseSecureWrite.promise;
      });

      const hydration = getToken({ isCurrent: () => current });
      await secureWriteStarted.promise;
      current = false;
      const loggingOut = logout();
      releaseSecureWrite.resolve();

      await expect(hydration).rejects.toMatchObject({ name: 'AuthOperationSuperseded' });
      await loggingOut;
      expect(secureItems[TOKEN_KEY]).toBeUndefined();
      expect(sharedToken).toBeNull();
      expect(await hasPersistedSessionMarker()).toBe(false);
      expect(mockedSetRuntimeToken).toHaveBeenLastCalledWith(null);
    });

    it('preserves an existing durable session when a superseding login fails', async () => {
      secureItems[TOKEN_KEY] = 'tok_existing';
      await markPersistedSession();
      let sharedToken: string | null = null;
      let current = true;
      const mirrorStarted = deferred<void>();
      const releaseMirror = deferred<void>();
      mockedSave.mockImplementation(async (token) => {
        sharedToken = token;
        mirrorStarted.resolve();
        await releaseMirror.promise;
        return 0;
      });
      mockedReadShared.mockImplementation(async () => sharedToken);
      mockedDelete.mockImplementation(async () => {
        sharedToken = null;
      });

      const hydration = getToken({ isCurrent: () => current });
      await mirrorStarted.promise;
      current = false;
      mockedApi.post.mockRejectedValueOnce(new Error('new login failed'));
      await expect(login('new-user', 'wrong')).rejects.toThrow('new login failed');
      releaseMirror.resolve();

      await expect(hydration).rejects.toMatchObject({ name: 'AuthOperationSuperseded' });
      expect(secureItems[TOKEN_KEY]).toBe('tok_existing');
      expect(sharedToken).toBe('tok_existing');
      expect(await hasPersistedSessionMarker()).toBe(true);
      expect(mockedSetRuntimeToken).not.toHaveBeenCalledWith('tok_existing');
    });

    it('preserves the original shared token when its SecureStore mirror becomes stale', async () => {
      let sharedToken: string | null = 'tok_shared_source';
      await markPersistedSession();
      let current = true;
      const mirrorStarted = deferred<void>();
      const releaseMirror = deferred<void>();
      mockedReadShared.mockImplementation(async () => sharedToken);
      mockedDelete.mockImplementation(async () => {
        sharedToken = null;
      });
      (SecureStore.setItemAsync as jest.Mock).mockImplementationOnce(async (key, value) => {
        secureItems[key] = value;
        mirrorStarted.resolve();
        await releaseMirror.promise;
      });

      const hydration = getToken({ isCurrent: () => current });
      await mirrorStarted.promise;
      current = false;
      releaseMirror.resolve();

      await expect(hydration).rejects.toMatchObject({ name: 'AuthOperationSuperseded' });
      expect(sharedToken).toBe('tok_shared_source');
      expect(await hasPersistedSessionMarker()).toBe(true);
      expect(mockedSetRuntimeToken).not.toHaveBeenCalledWith('tok_shared_source');
    });
  });

  describe('fetchCurrentUser', () => {
    it('returns the /auth/me response body', async () => {
      mockedApi.get.mockResolvedValueOnce({
        data: { id: 3, username: 'bob' },
      } as never);

      await expect(fetchCurrentUser()).resolves.toEqual({ id: 3, username: 'bob' });
      expect(mockedApi.get).toHaveBeenCalledWith('/auth/me');
    });
  });

  describe('remember credentials', () => {
    it('remember=true: 记最后登录用户名 + 密码', async () => {
      await saveCredentials('alice', 'hunter2', true);
      expect(SecureStore.setItemAsync).toHaveBeenCalledWith('last_username', 'alice');
      expect(SecureStore.setItemAsync).toHaveBeenCalledWith('remember_password', 'hunter2');
    });

    it('remember=false: 仍记用户名, 但删除密码', async () => {
      await saveCredentials('alice', 'hunter2', false);
      expect(SecureStore.setItemAsync).toHaveBeenCalledWith('last_username', 'alice');
      expect(SecureStore.deleteItemAsync).toHaveBeenCalledWith('remember_password');
    });

    it('loadCredentials 用户名+密码都在 → 返回 pair', async () => {
      (SecureStore.getItemAsync as jest.Mock)
        .mockResolvedValueOnce('alice')     // last_username
        .mockResolvedValueOnce('hunter2');  // remember_password
      await expect(loadCredentials()).resolves.toEqual({ username: 'alice', password: 'hunter2' });
    });

    it('loadCredentials 只有用户名(没记密码)→ 用户名 + 空密码(不再 null)', async () => {
      (SecureStore.getItemAsync as jest.Mock)
        .mockResolvedValueOnce('alice') // last_username
        .mockResolvedValueOnce(null);   // remember_password
      await expect(loadCredentials()).resolves.toEqual({ username: 'alice', password: '' });
    });

    it('loadCredentials 旧键迁移兜底(无 last_username, 有 remember_username)', async () => {
      (SecureStore.getItemAsync as jest.Mock)
        .mockResolvedValueOnce(null)     // last_username 空
        .mockResolvedValueOnce('legacy') // remember_username 旧键
        .mockResolvedValueOnce('pw');    // remember_password
      await expect(loadCredentials()).resolves.toEqual({ username: 'legacy', password: 'pw' });
    });

    it('loadCredentials 全空 → null', async () => {
      (SecureStore.getItemAsync as jest.Mock)
        .mockResolvedValueOnce(null)
        .mockResolvedValueOnce(null)
        .mockResolvedValueOnce(null);
      await expect(loadCredentials()).resolves.toBeNull();
    });

    it('loadCredentials SecureStore 抛错 → null', async () => {
      (SecureStore.getItemAsync as jest.Mock).mockRejectedValueOnce(new Error('no keychain'));
      await expect(loadCredentials()).resolves.toBeNull();
    });

    it('clearCredentials 只删密码(保留最后登录用户名)', async () => {
      await clearCredentials();
      expect(SecureStore.deleteItemAsync).toHaveBeenCalledWith('remember_password');
      expect(SecureStore.deleteItemAsync).not.toHaveBeenCalledWith('last_username');
    });

    it('saveCredentials SecureStore 失败不抛(但会 warn)', async () => {
      (SecureStore.setItemAsync as jest.Mock).mockRejectedValueOnce(new Error('keychain locked'));
      await expect(saveCredentials('a', 'b', true)).resolves.toBeUndefined();
    });
  });
});
