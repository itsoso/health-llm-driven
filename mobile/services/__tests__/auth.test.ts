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
  saveCredentials, loadCredentials, clearCredentials,
} from '../auth';
import api, { TOKEN_KEY, setRuntimeAuthToken } from '../api';
import * as SecureStore from 'expo-secure-store';
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

describe('services/auth', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockedSave.mockResolvedValue(0);
    mockedDelete.mockResolvedValue(undefined);
    mockedReadShared.mockResolvedValue(null);
  });

  describe('login', () => {
    it('stores token in SecureStore and forwards to shared keychain on success', async () => {
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
      expect(result.user.username).toBe('alice');
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

      await expect(login('alice', 'hunter2')).resolves.toBeDefined();
      expect(mockedSetRuntimeToken).toHaveBeenCalledWith('tok_fallback');
      expect(mockedSave).toHaveBeenCalledWith('tok_fallback');
    });

    it('双存储全挂也不抛 — 内存态兜底,只 warn', async () => {
      mockedApi.post.mockResolvedValueOnce({
        data: {
          access_token: 'tok_memory_only',
          token_type: 'bearer',
          user: { id: 7, username: 'alice' },
        },
      } as never);
      (SecureStore.setItemAsync as jest.Mock).mockRejectedValueOnce(new Error('locked'));
      mockedSave.mockRejectedValueOnce(new Error('no module'));

      await expect(login('alice', 'hunter2')).resolves.toBeDefined();
      expect(mockedSetRuntimeToken).toHaveBeenCalledWith('tok_memory_only');
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
      await logout();
      expect(mockedSetRuntimeToken).toHaveBeenCalledWith(null);
      expect(SecureStore.deleteItemAsync).toHaveBeenCalledWith(TOKEN_KEY);
      expect(mockedDelete).toHaveBeenCalled();
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
