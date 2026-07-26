import axios from 'axios';
import * as SecureStore from 'expo-secure-store';
import { enforceAppEgressAllowed } from './egressPolicy';

const TOKEN_KEY = 'auth_token';
export const WEB_SESSION_AUTH_SENTINEL = '__web_cookie_session__';

// SecureStore can be temporarily unavailable while iOS unlocks the keychain.
// Keep the token returned by a successful login in-process so the first
// authenticated requests do not race the persistence layer.
let runtimeAuthToken: string | null = null;

export function isUsableNativeAuthToken(token: string | null | undefined): token is string {
  return Boolean(token && token !== WEB_SESSION_AUTH_SENTINEL);
}

export function setRuntimeAuthToken(token: string | null): void {
  runtimeAuthToken = isUsableNativeAuthToken(token) ? token : null;
}

const DEFAULT_API = 'https://health.executor.life/api';
export const BASE_URL =
  (process.env.EXPO_PUBLIC_API_URL && process.env.EXPO_PUBLIC_API_URL.trim()) ||
  DEFAULT_API;

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

export const EXPLICIT_CLOUD_AI_HEADER = 'X-Reva-Explicit-Cloud-AI';

api.interceptors.request.use(
  async (config) => {
    const explicitCloudAI = config.headers.get(EXPLICIT_CLOUD_AI_HEADER) === '1';
    config.headers.delete(EXPLICIT_CLOUD_AI_HEADER);
    await enforceAppEgressAllowed({ explicitCloudAI });
    let token = runtimeAuthToken;
    if (!token) {
      try {
        const persistedToken = await SecureStore.getItemAsync(TOKEN_KEY);
        if (isUsableNativeAuthToken(persistedToken)) {
          token = persistedToken;
          runtimeAuthToken = persistedToken;
        }
      } catch {
        // SecureStore not available (e.g. web or a transient iOS keychain
        // window). A token installed by login remains usable in memory.
      }
    }
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    // Scope a later 401 to the exact session that sent this request. Without
    // this marker, a delayed response from an old token can log out a newly
    // authenticated user after an app foreground or account switch.
    (config as typeof config & { __revaAuthToken?: string | null }).__revaAuthToken = token;
    return config;
  },
  (error) => Promise.reject(error),
);

// Global 401 callback — set by AuthProvider to force logout
let onUnauthorized: (() => void) | null = null;
export function setOnUnauthorized(cb: (() => void) | null) { onUnauthorized = cb; }

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      const requestToken = (
        error.config as { __revaAuthToken?: string | null } | undefined
      )?.__revaAuthToken;
      if (requestToken !== undefined && requestToken === runtimeAuthToken) {
        onUnauthorized?.();
      }
    }
    return Promise.reject(error);
  },
);

export default api;
export { TOKEN_KEY };
