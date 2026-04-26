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
}));

jest.mock('../../modules/shared-keychain', () => ({
  saveTokenToSharedKeychain: jest.fn().mockResolvedValue(true),
  deleteTokenFromSharedKeychain: jest.fn().mockResolvedValue(undefined),
}));

import { login, logout, getToken, isLoggedIn, fetchCurrentUser } from '../auth';
import api, { TOKEN_KEY } from '../api';
import * as SecureStore from 'expo-secure-store';
import {
  saveTokenToSharedKeychain,
  deleteTokenFromSharedKeychain,
} from '../../modules/shared-keychain';

const mockedApi = api as jest.Mocked<typeof api>;
const mockedSave = saveTokenToSharedKeychain as jest.MockedFunction<typeof saveTokenToSharedKeychain>;
const mockedDelete = deleteTokenFromSharedKeychain as jest.MockedFunction<typeof deleteTokenFromSharedKeychain>;

describe('services/auth', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockedSave.mockResolvedValue(true);
    mockedDelete.mockResolvedValue(undefined);
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
      expect(SecureStore.setItemAsync).toHaveBeenCalled();
    });
  });

  describe('logout', () => {
    it('clears SecureStore and shared keychain', async () => {
      await logout();
      expect(SecureStore.deleteItemAsync).toHaveBeenCalledWith(TOKEN_KEY);
      expect(mockedDelete).toHaveBeenCalled();
    });

    it('ignores keychain clearing failure', async () => {
      mockedDelete.mockRejectedValueOnce(new Error('no module'));
      await expect(logout()).resolves.toBeUndefined();
    });
  });

  describe('getToken / isLoggedIn', () => {
    it('returns the stored token', async () => {
      (SecureStore.getItemAsync as jest.Mock).mockResolvedValueOnce('tok_xyz');
      await expect(getToken()).resolves.toBe('tok_xyz');
    });

    it('returns null when SecureStore throws', async () => {
      (SecureStore.getItemAsync as jest.Mock).mockRejectedValueOnce(
        new Error('SecureStore unavailable'),
      );
      await expect(getToken()).resolves.toBeNull();
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
});
