import axios from 'axios';
import { enforceAppEgressAllowed } from './egressPolicy';
import { aiConsentRevision, hasAIConsent, invalidateAIConsent, isAIConsentError, isAIConsentRequired, setAIConsentIdentity } from './aiConsentState';

const TOKEN_KEY = 'auth_token';
export const WEB_SESSION_AUTH_SENTINEL = '__web_cookie_session__';

// SecureStore can be temporarily unavailable while iOS unlocks the keychain.
// Keep the token returned by a successful login in-process so the first
// authenticated requests do not race the persistence layer.
let runtimeAuthToken: string | null = null;
let authGeneration = 0;
let authInitialized = false;
const authChangeListeners = new Set<() => void>();

export function subscribeAuthSessionChange(listener: () => void): () => void {
  authChangeListeners.add(listener);
  return () => { authChangeListeners.delete(listener); };
}

export function isUsableNativeAuthToken(token: string | null | undefined): token is string {
  return Boolean(token && token !== WEB_SESSION_AUTH_SENTINEL);
}

export function setRuntimeAuthToken(token: string | null): void {
  const nextToken = isUsableNativeAuthToken(token) ? token : null;
  authInitialized = true;
  if (nextToken !== runtimeAuthToken || nextToken === null) {
    authGeneration += 1;
    runtimeAuthToken = nextToken;
    for (const listener of authChangeListeners) listener();
  }
  setAIConsentIdentity(runtimeAuthToken);
}

const DEFAULT_API = 'https://health.executor.life/api';
export const BASE_URL =
  (process.env.EXPO_PUBLIC_API_URL && process.env.EXPO_PUBLIC_API_URL.trim()) ||
  DEFAULT_API;

const transport = axios.create({
  baseURL: BASE_URL,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

// Axios schedules async interceptors after the caller returns. Capture the
// generation at invocation so an immediate account switch cannot rebind an
// already-created request to the next account.
function scopedCall(args: unknown[], configIndex: number): unknown[] {
  const scoped = [...args];
  scoped[configIndex] = { ...(scoped[configIndex] as object | undefined), __revaDispatchGeneration: authGeneration };
  return scoped;
}
const readMethods = new Set(['get', 'delete', 'head', 'options']);
const writeMethods = new Set(['post', 'put', 'patch', 'postForm', 'putForm', 'patchForm']);
const api = new Proxy(transport, {
  apply(target, thisArg, args) {
    return Reflect.apply(target, thisArg, scopedCall(args, typeof args[0] === 'string' ? 1 : 0));
  },
  get(target, property, receiver) {
    const value = Reflect.get(target, property, receiver);
    if (typeof property !== 'string' || typeof value !== 'function') return value;
    const configIndex = readMethods.has(property) ? 1 : writeMethods.has(property) ? 2 : null;
    if (configIndex !== null || property === 'request') {
      return (...args: unknown[]) => Reflect.apply(value, target,
        scopedCall(args, configIndex ?? (typeof args[0] === 'string' ? 1 : 0)));
    }
    return value;
  },
});

export const EXPLICIT_CLOUD_AI_HEADER = 'X-Reva-Explicit-Cloud-AI';

const CLOUD_SESSION_BOOTSTRAP_REQUESTS = new Set([
  'POST /auth/login/json',
  'POST /auth/phone/code',
  'POST /auth/phone/login',
  'POST /auth/phone/verify',
  'POST /auth/invited-registration',
]);

function isCloudSessionBootstrapRequest(method: string | undefined, url: string | undefined): boolean {
  const normalizedMethod = String(method || 'get').toUpperCase();
  const normalizedPath = String(url || '').split('?', 1)[0];
  return CLOUD_SESSION_BOOTSTRAP_REQUESTS.has(`${normalizedMethod} ${normalizedPath}`);
}

api.interceptors.request.use(
  async (config) => {
    const generation = (config as typeof config & { __revaDispatchGeneration?: number }).__revaDispatchGeneration ?? authGeneration;
    const assertCurrentSession = () => {
      if (generation !== authGeneration) throw new Error('auth_session_changed');
    };
    assertCurrentSession();
    const consentRevision = (config as typeof config & { __revaConsentRevision?: number }).__revaConsentRevision;
    const explicitCloudAI = config.headers.get(EXPLICIT_CLOUD_AI_HEADER) === '1';
    config.headers.delete(EXPLICIT_CLOUD_AI_HEADER);
    let token = runtimeAuthToken;
    if (!authInitialized) {
      let persistedToken: string | null = null;
      try {
        const { readPersistedApiAuthToken } = require('./auth') as typeof import('./auth');
        persistedToken = await readPersistedApiAuthToken();
      } catch {
        assertCurrentSession();
        if (!isCloudSessionBootstrapRequest(config.method, config.url)) {
          throw new Error('auth_storage_unavailable');
        }
        // An explicit new login can proceed without a residual credential.
      }
      assertCurrentSession();
      if (authInitialized) {
        token = runtimeAuthToken;
      } else if (isUsableNativeAuthToken(persistedToken)) {
        token = persistedToken;
        // Initial keychain hydration belongs to this startup generation.
        // An explicit login/logout above cannot be replaced by this read.
        runtimeAuthToken = persistedToken;
        authInitialized = true;
        setAIConsentIdentity(runtimeAuthToken);
      }
    }
    await enforceAppEgressAllowed({
      explicitCloudAI,
      cloudSessionBootstrap: isCloudSessionBootstrapRequest(config.method, config.url),
      cloudCredentialPresent: isUsableNativeAuthToken(token),
    });
    assertCurrentSession();
    config.headers.delete('Authorization');
    delete config.headers.Authorization;
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    if (requiresAIConsent(config.method, config.url) && !hasAIConsent()) {
      // Lazy load avoids an api → consent → auth → api initialization cycle.
      const { requireAIConsent } = require('./aiConsent') as typeof import('./aiConsent');
      await requireAIConsent();
      assertCurrentSession();
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
      __revaAuthGeneration?: number;
    };
    scopedConfig.__revaAuthToken = token;
    scopedConfig.__revaAuthGeneration = generation;
    scopedConfig.__revaRequestConsentRevision = aiConsentRevision();
    return config;
  },
  (error) => Promise.reject(error),
);

// Global 401 callback — set by AuthProvider to force logout
let onUnauthorized: (() => void) | null = null;
export function setOnUnauthorized(cb: (() => void) | null) { onUnauthorized = cb; }

api.interceptors.response.use(
  (response) => {
    const generation = (response.config as typeof response.config & { __revaAuthGeneration?: number }).__revaAuthGeneration;
    if (generation !== undefined && generation !== authGeneration) throw new Error('auth_session_changed');
    return response;
  },
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
        && (error.config as { __revaAuthGeneration?: number } | undefined)?.__revaAuthGeneration === authGeneration
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
