import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from 'react';
import { Alert } from 'react-native';
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

  // Register 401 handler — forces logout on token expiry
  useEffect(() => {
    setOnUnauthorized(() => {
      setToken(null);
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
          // Backfill shared keychain on every cold start —— 老用户升级到带 Siri 的
          // build 后, 共享区原本是空的; 这里无条件回灌一次, 让 Siri extension 读得到。
          // Returns OSStatus: 0 = success, 非 0 = 错误码 (如 -34018 entitlement 缺失)。
          // 非 0 时立刻 Alert 暴露出来, 方便诊断 TestFlight 上的 Siri 问题。
          saveTokenToSharedKeychain(saved)
            .then((status) => {
              if (status !== 0) {
                Alert.alert(
                  'Siri 共享 keychain 写入失败',
                  `OSStatus=${status}\n\n-34018 = entitlement 缺失\n其他 = 见 Apple OSStatus 文档\n\n（此 Alert 仅用于诊断, 修好后下个版本会移除）`,
                );
              }
            })
            .catch((e) => {
              Alert.alert('Siri keychain 异常', String(e));
            });
          const me = await fetchCurrentUser();
          if (mounted) setUser(me);
        }
      } catch {
        // token expired or invalid
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

  const isAuthenticated = token !== null && user !== null;

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
