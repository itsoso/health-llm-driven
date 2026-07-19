import axios from 'axios';
import * as SecureStore from 'expo-secure-store';
import { enforceAppEgressAllowed } from './egressPolicy';

const TOKEN_KEY = 'auth_token';

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
      onUnauthorized?.();
    }
    return Promise.reject(error);
  },
);

export default api;
export { TOKEN_KEY };
