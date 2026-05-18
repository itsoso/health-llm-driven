import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from 'react';
import {
  login as loginApi,
  logout as logoutApi,
  getToken,
  fetchCurrentUser,
  type User,
} from '../services/auth';
import { setOnUnauthorized } from '../services/api';
import { saveTokenToSharedKeychain } from '../modules/shared-keychain';

interface AuthState {
  user: User | null;
  token: string | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState>({
  user: null,
  token: null,
  isLoading: true,
  isAuthenticated: false,
  login: async () => {},
  logout: async () => {},
});

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
        const saved = await getToken();
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

  const login = useCallback(async (username: string, password: string) => {
    const result = await loginApi(username, password);
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
      value={{ user, token, isLoading, isAuthenticated, login, logout }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  return useContext(AuthContext);
}
