import axios from 'axios';
import * as SecureStore from 'expo-secure-store';
import { enforceAppEgressAllowed } from './egressPolicy';
import { aiConsentRevision, hasAIConsent, invalidateAIConsent, isAIConsentError, isAIConsentRequired, setAIConsentIdentity } from './aiConsentState';

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
  setAIConsentIdentity(runtimeAuthToken);
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

const CLOUD_SESSION_BOOTSTRAP_REQUESTS = new Set([
  'POST /auth/login/json',
  'POST /auth/phone/code',
  'POST /auth/phone/login',
]);

function isCloudSessionBootstrapRequest(method: string | undefined, url: string | undefined): boolean {
  const normalizedMethod = String(method || 'get').toUpperCase();
  const normalizedPath = String(url || '').split('?', 1)[0];
  return CLOUD_SESSION_BOOTSTRAP_REQUESTS.has(`${normalizedMethod} ${normalizedPath}`);
}

api.interceptors.request.use(
  async (config) => {
    const consentRevision = (config as typeof config & { __revaConsentRevision?: number }).__revaConsentRevision;
    const explicitCloudAI = config.headers.get(EXPLICIT_CLOUD_AI_HEADER) === '1';
    config.headers.delete(EXPLICIT_CLOUD_AI_HEADER);
    let token = runtimeAuthToken;
    if (!token) {
      try {
        const persistedToken = await SecureStore.getItemAsync(TOKEN_KEY);
        if (isUsableNativeAuthToken(persistedToken)) {
          token = persistedToken;
          setRuntimeAuthToken(persistedToken);
        }
      } catch {
        // SecureStore not available (e.g. web or a transient iOS keychain
        // window). A token installed by login remains usable in memory.
      }
    }
    await enforceAppEgressAllowed({
      explicitCloudAI,
      cloudSessionBootstrap: isCloudSessionBootstrapRequest(config.method, config.url),
      cloudCredentialPresent: isUsableNativeAuthToken(token),
    });
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    if (requiresAIConsent(config.method, config.url) && !hasAIConsent()) {
      // Lazy load avoids an api → consent → auth → api initialization cycle.
      const { requireAIConsent } = require('./aiConsent') as typeof import('./aiConsent');
      await requireAIConsent();
      if (token !== runtimeAuthToken) throw new Error('auth_session_changed');
    }
    if (consentRevision !== undefined && consentRevision !== aiConsentRevision()) {
      throw new Error('auth_session_changed');
    }
    // Scope a later 401 to the exact session that sent this request. Without
    // this marker, a delayed response from an old token can log out a newly
    // authenticated user after an app foreground or account switch.
    const scopedConfig = config as typeof config & {
      __revaAuthToken?: string | null;
      __revaRequestConsentRevision?: number;
    };
    scopedConfig.__revaAuthToken = token;
    scopedConfig.__revaRequestConsentRevision = aiConsentRevision();
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
    if (isAIConsentError(error)) {
      const request = error.config as {
        __revaAuthToken?: string | null;
        __revaRequestConsentRevision?: number;
      } | undefined;
      if (request?.__revaAuthToken !== undefined
        && request.__revaAuthToken === runtimeAuthToken
        && request.__revaRequestConsentRevision === aiConsentRevision()) {
        invalidateAIConsent(isAIConsentRequired() || error.response?.status === 403);
      }
    }
    if (error.response?.status === 401) {
      const requestToken = (
        error.config as { __revaAuthToken?: string | null } | undefined
      )?.__revaAuthToken;
      const requestUrl = String(error.config?.url || '').split('?', 1)[0];
      const isAuthRequest = requestUrl.startsWith('/auth/');
      if (
        !isAuthRequest
        && requestToken !== undefined
        && requestToken === runtimeAuthToken
      ) {
        onUnauthorized?.();
      }
    }
    return Promise.reject(error);
  },
);

export default api;
export { TOKEN_KEY };

// Record reads and deterministic data management remain available without AI.
// The backend also gates the provider boundary for other clients and jobs.
export function requiresAIConsent(method?: string, url?: string): boolean {
  const path = String(url || '').split('?', 1)[0];
  const verb = String(method || 'get').toUpperCase();
  return verb === 'POST' && (
    /^\/(agent\/(chat|stream)|chat\/(transcribe|tts)|tts\/synthesize|diet\/(recognize|voice\/parse|estimate-nutrition)|quick-record|safety\/explain|clarification\/extract-memory|dynamic-views\/today)(\/|$)/.test(path)
    || /^\/(ambient\/(visual-inputs|audio-inputs|rokid-voice-commands)|aigc|medical-exams\/import|prescriptions\/recognize|genetic\/profiles\/upload-pdf)(\/|$)/.test(path)
    || /^\/ambient\/meal-sessions(?:\/?$|\/[^/]+\/(frames|finish)\/?$)/.test(path)
    || /^\/(workout\/me\/[^/]+\/analyze|monthly-report\/me\/[^/]+\/[^/]+\/regenerate|goals\/(guidance|me\/generate-from-analysis))\/?$/.test(path)
  );
}
