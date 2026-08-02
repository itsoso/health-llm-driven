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
  verifyPhoneCode as verifyPhoneCodeApi,
  completeInvitedRegistration as completeInvitedRegistrationApi,
  logout as logoutApi,
  getToken,
  fetchCurrentUser,
  isAuthOperationSuperseded,
  registrationAuthErrorCode,
  loadPendingRegistration,
  type InvitationCredential,
  type PendingRegistration,
  type User,
} from '../services/auth';
import { setOnUnauthorized } from '../services/api';
import { hasPersistedSessionMarker } from '../services/authSessionMarker';

const TOKEN_RESTORE_ATTEMPTS = 3;
const KNOWN_SESSION_RESTORE_ATTEMPTS = 10;
const TOKEN_RESTORE_RETRY_MS = 150;
const UNAUTHORIZED_CONFIRM_RETRY_MS = 350;

interface AuthState {
  user: User | null;
  token: string | null;
  pendingRegistration: PendingRegistrationState | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  loginByPhoneCode: (phone: string, code: string) => Promise<void>;
  verifyPhoneCode: (
    phone: string,
    code: string,
  ) => Promise<'authenticated' | 'invitation_required' | 'superseded'>;
  completeInvitedRegistration: (credential: InvitationCredential) => Promise<void>;
  logout: () => Promise<void>;
  retrySession: () => Promise<void>;
}

export interface PendingRegistrationState {
  expiresAt: number;
  phoneMasked?: string;
}

const AuthContext = createContext<AuthState>({
  user: null,
  token: null,
  pendingRegistration: null,
  isLoading: true,
  isAuthenticated: false,
  login: async () => {},
  loginByPhoneCode: async () => {},
  verifyPhoneCode: async () => {
    throw new Error('认证服务尚未初始化');
  },
  completeInvitedRegistration: async () => {},
  logout: async () => {},
  retrySession: async () => {},
});

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function restoreSavedToken(
  knownSession = false,
  isCurrent?: () => boolean,
): Promise<string | null> {
  const attempts = knownSession
    ? KNOWN_SESSION_RESTORE_ATTEMPTS
    : TOKEN_RESTORE_ATTEMPTS;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const saved = await getToken({ isCurrent });
    if (isCurrent && !isCurrent()) throwAuthOperationSuperseded();
    if (saved) return saved;
    if (attempt < attempts - 1) {
      await sleep(TOKEN_RESTORE_RETRY_MS);
      if (isCurrent && !isCurrent()) throwAuthOperationSuperseded();
    }
  }
  return null;
}

function isUnauthorizedError(error: unknown): boolean {
  return (error as { response?: { status?: number } } | null)?.response?.status === 401;
}

function throwAuthOperationSuperseded(): never {
  const error = new Error('auth operation superseded');
  error.name = 'AuthOperationSuperseded';
  throw error;
}

async function fetchCurrentUserWithConfirmedAuth(
  isCurrent: () => boolean = () => true,
): Promise<User> {
  try {
    const currentUser = await fetchCurrentUser();
    if (!isCurrent()) throwAuthOperationSuperseded();
    return currentUser;
  } catch (error) {
    if (!isCurrent() || isAuthOperationSuperseded(error)) {
      throwAuthOperationSuperseded();
    }
    if (!isUnauthorizedError(error)) throw error;
  }

  await sleep(UNAUTHORIZED_CONFIRM_RETRY_MS);
  if (!isCurrent()) throwAuthOperationSuperseded();
  const currentUser = await fetchCurrentUser();
  if (!isCurrent()) throwAuthOperationSuperseded();
  return currentUser;
}

async function restorePendingRegistrationState(
  isCurrent: () => boolean = () => true,
): Promise<PendingRegistrationState | null> {
  const pending: PendingRegistration | null = await loadPendingRegistration();
  if (!isCurrent()) throwAuthOperationSuperseded();
  if (!pending) return null;
  return {
    expiresAt: pending.expiresAt,
    ...(pending.phoneMasked ? { phoneMasked: pending.phoneMasked } : {}),
  };
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
  const [pendingRegistration, setPendingRegistration] = useState<PendingRegistrationState | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const sessionEpochRef = useRef(0);
  const sessionValidationRef = useRef<Promise<void> | null>(null);
  const providerMountedRef = useRef(true);

  useEffect(() => {
    providerMountedRef.current = true;
    return () => {
      providerMountedRef.current = false;
    };
  }, []);

  const beginAuthOperation = useCallback(() => {
    sessionEpochRef.current += 1;
    const operationEpoch = sessionEpochRef.current;
    return {
      isCurrent: () => (
        providerMountedRef.current
        && sessionEpochRef.current === operationEpoch
      ),
    };
  }, []);

  const clearSession = useCallback(async () => {
    sessionEpochRef.current += 1;
    setToken(null);
    setUser(null);
    setPendingRegistration(null);
    await logoutApi();
  }, []);

  const retrySession = useCallback(async () => {
    if (sessionValidationRef.current) return sessionValidationRef.current;

    const validation = (async () => {
      const recoveryEpoch = sessionEpochRef.current;
      const isCurrent = () => (
        providerMountedRef.current
        && sessionEpochRef.current === recoveryEpoch
      );
      let knownSession = token !== null;
      if (!knownSession) {
        knownSession = await hasPersistedSessionMarker();
        if (!isCurrent()) return;
      }
      const saved = token || await restoreSavedToken(knownSession, isCurrent);
      if (!isCurrent() || !saved) return;

      setToken(saved);
      try {
        const me = await fetchCurrentUserWithConfirmedAuth(isCurrent);
        if (!isCurrent()) return;
        setUser(me);
      } catch (error) {
        if (!isCurrent() || isAuthOperationSuperseded(error)) return;
        if (isUnauthorizedError(error)) {
          await clearSession();
          return;
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
      setPendingRegistration(null);
      setIsLoading(false);
      return () => {
        mounted = false;
      };
    }
    setIsLoading(true);
    const hydrationEpoch = sessionEpochRef.current;
    (async () => {
      const isCurrent = () => (
        mounted
        && providerMountedRef.current
        && sessionEpochRef.current === hydrationEpoch
      );
      try {
        const knownSession = await hasPersistedSessionMarker();
        if (!isCurrent()) return;
        const saved = await restoreSavedToken(knownSession, isCurrent);
        if (!isCurrent()) return;
        if (saved) {
          setToken(saved);
          try {
            const me = await fetchCurrentUserWithConfirmedAuth(isCurrent);
            if (!isCurrent()) return;
            setUser(me);
          } catch (error) {
            if (!isCurrent() || isAuthOperationSuperseded(error)) return;
            if (isUnauthorizedError(error)) {
              await clearSession();
            } else {
              // Preserve the token for offline/transient failures and retry on
              // the next foreground transition.
              setUser(null);
            }
          }
        } else {
          const pending = await restorePendingRegistrationState(isCurrent);
          if (!isCurrent()) return;
          setPendingRegistration(pending);
        }
      } catch (error) {
        if (!isCurrent() || isAuthOperationSuperseded(error)) return;
        setToken(null);
        setUser(null);
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
    const operation = beginAuthOperation();
    try {
      const result = await loginApi(username, password, operation);
      if (!operation.isCurrent()) return;
      setToken(result.access_token);
      setUser(result.user);
      setPendingRegistration(null);
    } catch (error) {
      if (!operation.isCurrent() || isAuthOperationSuperseded(error)) return;
      throw error;
    }
  }, [beginAuthOperation]);

  const loginByPhoneCode = useCallback(async (phone: string, code: string) => {
    const operation = beginAuthOperation();
    try {
      const result = await loginByPhoneCodeApi(phone, code, operation);
      if (!operation.isCurrent()) return;
      setToken(result.access_token);
      setUser(result.user);
      setPendingRegistration(null);
    } catch (error) {
      if (!operation.isCurrent() || isAuthOperationSuperseded(error)) return;
      throw error;
    }
  }, [beginAuthOperation]);

  const verifyPhoneCode = useCallback(async (phone: string, code: string) => {
    const operation = beginAuthOperation();
    try {
      const result = await verifyPhoneCodeApi(phone, code, operation);
      if (!operation.isCurrent()) return 'superseded';
      if (result.outcome === 'authenticated') {
        setToken(result.access_token);
        setUser(result.user);
        setPendingRegistration(null);
      } else {
        const pending = await restorePendingRegistrationState(operation.isCurrent);
        if (!operation.isCurrent()) return 'superseded';
        setPendingRegistration(pending);
      }
      return result.outcome;
    } catch (error) {
      if (!operation.isCurrent() || isAuthOperationSuperseded(error)) return 'superseded';
      throw error;
    }
  }, [beginAuthOperation]);

  const completeInvitedRegistration = useCallback(async (
    credential: InvitationCredential,
  ) => {
    const operation = beginAuthOperation();
    try {
      const result = await completeInvitedRegistrationApi(credential, operation);
      if (!operation.isCurrent()) return;
      setToken(result.access_token);
      setUser(result.user);
      setPendingRegistration(null);
    } catch (error) {
      if (!operation.isCurrent() || isAuthOperationSuperseded(error)) return;
      if (registrationAuthErrorCode(error) === 'VERIFIED_PHONE_TICKET_EXPIRED') {
        setPendingRegistration(null);
        throw error;
      }
      const pending = await restorePendingRegistrationState(operation.isCurrent);
      if (!operation.isCurrent()) return;
      setPendingRegistration(pending);
      throw error;
    }
  }, [beginAuthOperation]);

  const logout = useCallback(async () => {
    sessionEpochRef.current += 1;
    setToken(null);
    setUser(null);
    setPendingRegistration(null);
    await logoutApi();
  }, []);

  const isAuthenticated = token !== null;

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        pendingRegistration,
        isLoading,
        isAuthenticated,
        login,
        loginByPhoneCode,
        verifyPhoneCode,
        completeInvitedRegistration,
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
