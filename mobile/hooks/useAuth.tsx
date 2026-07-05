import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
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

const TOKEN_RESTORE_ATTEMPTS = 3;
const TOKEN_RESTORE_RETRY_MS = 150;

interface AuthState {
  user: User | null;
  token: string | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  loginByPhoneCode: (phone: string, code: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState>({
  user: null,
  token: null,
  isLoading: true,
  isAuthenticated: false,
  login: async () => {},
  loginByPhoneCode: async () => {},
  logout: async () => {},
});

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function restoreSavedToken(): Promise<string | null> {
  for (let attempt = 0; attempt < TOKEN_RESTORE_ATTEMPTS; attempt += 1) {
    const saved = await getToken();
    if (saved) return saved;
    if (attempt < TOKEN_RESTORE_ATTEMPTS - 1) {
      await sleep(TOKEN_RESTORE_RETRY_MS);
    }
  }
  return null;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Register 401 handler. Do not erase the persisted token here: a single
  // incidental 401 during backend deploy/OTA reload should not log the user out.
  useEffect(() => {
    setOnUnauthorized(() => {
      setUser(null);
    });
  }, []);

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const saved = await restoreSavedToken();
        if (saved && mounted) {
          setToken(saved);
          // 冷启动回灌 token 到 App Group UserDefaults + 共享 keychain,
          // 让 Siri extension 能读到。失败静默 —— 主 App 体验不受影响。
          saveTokenToSharedKeychain(saved).catch(() => {});
          try {
            const me = await fetchCurrentUser();
            if (mounted) setUser(me);
          } catch {
            // Keep token-authenticated state. Most startup failures after an
            // app update are transient; explicit logout is the only path that
            // should delete the persisted token.
            if (mounted) setUser(null);
          }
        }
      } catch {
        setToken(null);
        setUser(null);
      } finally {
        if (mounted) setIsLoading(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  // 回前台自愈:冷启动窗口 keychain 瞬时读失败会把人留在登录页,
  // transient 401/断网会让 user 悬空 —— 两者都不该需要手动重登。
  // 只做恢复,绝不在这里清 token(删除 token 的唯一路径仍是显式 logout)。
  useEffect(() => {
    const sub = AppState.addEventListener('change', (state) => {
      if (state !== 'active' || isLoading) return;
      void (async () => {
        try {
          if (!token) {
            const saved = await restoreSavedToken();
            if (saved) {
              setToken(saved);
              saveTokenToSharedKeychain(saved).catch(() => {});
              setUser(await fetchCurrentUser());
            }
          } else if (!user) {
            setUser(await fetchCurrentUser());
          }
        } catch {
          // transient — 下次回前台再试
        }
      })();
    });
    return () => sub.remove();
  }, [token, user, isLoading]);

  const login = useCallback(async (username: string, password: string) => {
    const result = await loginApi(username, password);
    setToken(result.access_token);
    setUser(result.user);
  }, []);

  const loginByPhoneCode = useCallback(async (phone: string, code: string) => {
    const result = await loginByPhoneCodeApi(phone, code);
    setToken(result.access_token);
    setUser(result.user);
  }, []);

  const logout = useCallback(async () => {
    await logoutApi();
    setToken(null);
    setUser(null);
  }, []);

  const isAuthenticated = token !== null;

  return (
    <AuthContext.Provider
      value={{ user, token, isLoading, isAuthenticated, login, loginByPhoneCode, logout }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  return useContext(AuthContext);
}
