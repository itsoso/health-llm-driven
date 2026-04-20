import axios from 'axios';
import * as SecureStore from 'expo-secure-store';
import { deleteTokenFromSharedKeychain } from '../modules/shared-keychain';

const TOKEN_KEY = 'auth_token';
export const BASE_URL = 'https://health.executor.life/api';

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

api.interceptors.request.use(
  async (config) => {
    try {
      const token = await SecureStore.getItemAsync(TOKEN_KEY);
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
    } catch {
      // SecureStore not available (e.g. web), ignore
    }
    return config;
  },
  (error) => Promise.reject(error),
);

// Global 401 callback — set by AuthProvider to force logout
let onUnauthorized: (() => void) | null = null;
export function setOnUnauthorized(cb: () => void) { onUnauthorized = cb; }

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      try {
        await SecureStore.deleteItemAsync(TOKEN_KEY);
        deleteTokenFromSharedKeychain().catch(() => {});
      } catch {}
      onUnauthorized?.();
    }
    return Promise.reject(error);
  },
);

export default api;
export { TOKEN_KEY };
