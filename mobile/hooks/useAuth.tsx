import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useRef,
  type ReactNode,
} from 'react';
import { AppState } from 'react-native';
import {
  login as loginApi,
  loginByPhoneCode as loginByPhoneCodeApi,
  logout as logoutApi,
  getToken,
  fetchCurrentUser,
  type User,
} from '../services/auth';
import { setOnUnauthorized } from '../services/api';
import { saveTokenToSharedKeychain } from '../modules/shared-keychain';
import {
  hasPersistedSessionMarker,
  markPersistedSession,
} from '../services/authSessionMarker';

const TOKEN_RESTORE_ATTEMPTS = 3;
const KNOWN_SESSION_RESTORE_ATTEMPTS = 10;
const TOKEN_RESTORE_RETRY_MS = 150;
const UNAUTHORIZED_CONFIRM_RETRY_MS = 350;

interface AuthState {
  user: User | null;
  token: string | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  loginByPhoneCode: (phone: string, code: string) => Promise<void>;
  logout: () => Promise<void>;
  retrySession: () => Promise<void>;
}

const AuthContext = createContext<AuthState>({
  user: null,
  token: null,
  isLoading: true,
  isAuthenticated: false,
  login: async () => {},
  loginByPhoneCode: async () => {},
  logout: async () => {},
  retrySession: async () => {},
});

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function restoreSavedToken(knownSession = false): Promise<string | null> {
  const attempts = knownSession
    ? KNOWN_SESSION_RESTORE_ATTEMPTS
    : TOKEN_RESTORE_ATTEMPTS;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const saved = await getToken();
    if (saved) return saved;
    if (attempt < attempts - 1) {
      await sleep(TOKEN_RESTORE_RETRY_MS);
    }
  }
  return null;
}

function isUnauthorizedError(error: unknown): boolean {
  return (error as { response?: { status?: number } } | null)?.response?.status === 401;
}

async function fetchCurrentUserWithConfirmedAuth(): Promise<User> {
  try {
    return await fetchCurrentUser();
  } catch (error) {
    if (!isUnauthorizedError(error)) throw error;
    await sleep(UNAUTHORIZED_CONFIRM_RETRY_MS);
    return fetchCurrentUser();
  }
}

export function AuthProvider({
  children,
  restoreCloudSession = true,
}: {
  children: ReactNode;
  restoreCloudSession?: boolean;
}) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const sessionEpochRef = useRef(0);
  const sessionValidationRef = useRef<Promise<void> | null>(null);

  const clearSession = useCallback(async () => {
    sessionEpochRef.current += 1;
    setToken(null);
    setUser(null);
    await logoutApi();
  }, []);

  const retrySession = useCallback(async () => {
    if (sessionValidationRef.current) return sessionValidationRef.current;

    const validation = (async () => {
      const recoveryEpoch = sessionEpochRef.current;
      const knownSession = token !== null || await hasPersistedSessionMarker();
      const saved = token || await restoreSavedToken(knownSession);
      if (!saved || sessionEpochRef.current !== recoveryEpoch) return;

      setToken(saved);
      await markPersistedSession();
      saveTokenToSharedKeychain(saved).catch(() => {});
      try {
        const me = await fetchCurrentUserWithConfirmedAuth();
        if (sessionEpochRef.current === recoveryEpoch) setUser(me);
      } catch (error) {
        if (sessionEpochRef.current === recoveryEpoch && isUnauthorizedError(error)) {
          await clearSession();
        }
        throw error;
      }
    })();
    sessionValidationRef.current = validation;
    try {
      await validation;
    } finally {
      if (sessionValidationRef.current === validation) {
        sessionValidationRef.current = null;
      }
    }
  }, [clearSession, token]);

  // A business endpoint can return 401 because of deploy/proxy timing or an
  // endpoint-specific policy. Revalidate against /auth/me before deciding that
  // the durable credential is invalid; never erase it from one incidental 401.
  useEffect(() => {
    setOnUnauthorized(() => {
      void retrySession().catch(() => {});
    });
    return () => setOnUnauthorized(null);
  }, [retrySession]);

  useEffect(() => {
    let mounted = true;
    if (!restoreCloudSession) {
      setToken(null);
      setUser(null);
      setIsLoading(false);
      return () => {
        mounted = false;
      };
    }
    setIsLoading(true);
    const hydrationEpoch = sessionEpochRef.current;
    (async () => {
      try {
        const knownSession = await hasPersistedSessionMarker();
        const saved = await restoreSavedToken(knownSession);
        if (saved && mounted && sessionEpochRef.current === hydrationEpoch) {
          setToken(saved);
          await markPersistedSession();
          // 冷启动回灌 token 到 App Group UserDefaults + 共享 keychain,
          // 让 Siri extension 能读到。失败静默 —— 主 App 体验不受影响。
          saveTokenToSharedKeychain(saved).catch(() => {});
          try {
            const me = await fetchCurrentUserWithConfirmedAuth();
            if (mounted && sessionEpochRef.current === hydrationEpoch) setUser(me);
          } catch (error) {
            if (sessionEpochRef.current !== hydrationEpoch) {
              return;
            }
            if (isUnauthorizedError(error)) {
              await clearSession();
            } else if (mounted) {
              // Preserve the token for offline/transient failures and retry on
              // the next foreground transition.
              setUser(null);
            }
          }
        }
      } catch {
        if (sessionEpochRef.current === hydrationEpoch) {
          setToken(null);
          setUser(null);
        }
      } finally {
        if (mounted) setIsLoading(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, [clearSession, restoreCloudSession]);

  // 回前台自愈:冷启动窗口 keychain 瞬时读失败会把人留在登录页,
  // transient 401/断网会让 user 悬空 —— 两者都不该需要手动重登。
  // 只做恢复,绝不在这里清 token(删除 token 的唯一路径仍是显式 logout)。
  useEffect(() => {
    const sub = AppState.addEventListener('change', (state) => {
      if (state !== 'active' || isLoading || !restoreCloudSession) return;
      void (async () => {
        try {
          if (!token || !user) await retrySession();
        } catch {
          // retrySession owns confirmed credential invalidation. Transient
          // failures remain recoverable on the next foreground transition.
        }
      })();
    });
    return () => sub.remove();
  }, [token, user, isLoading, restoreCloudSession, retrySession]);

  const login = useCallback(async (username: string, password: string) => {
    const result = await loginApi(username, password);
    sessionEpochRef.current += 1;
    setToken(result.access_token);
    setUser(result.user);
  }, []);

  const loginByPhoneCode = useCallback(async (phone: string, code: string) => {
    const result = await loginByPhoneCodeApi(phone, code);
    sessionEpochRef.current += 1;
    setToken(result.access_token);
    setUser(result.user);
  }, []);

  const logout = useCallback(async () => {
    sessionEpochRef.current += 1;
    setToken(null);
    setUser(null);
    await logoutApi();
  }, []);

  const isAuthenticated = token !== null;

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isLoading,
        isAuthenticated,
        login,
        loginByPhoneCode,
        logout,
        retrySession,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  return useContext(AuthContext);
}
