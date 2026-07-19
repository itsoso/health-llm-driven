import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

import {
  deleteLocalHealthVault,
  openLocalHealthVault,
} from '../modules/local-health-kernel';
import {
  clearAppModePreference,
  createPersistedLocalIdentity,
  loadAppModePreference,
  persistAppModePreference,
  type AppMode,
  type AppModePreference,
  type LocalAppMode,
} from '../services/localIdentity';
import { AuthProvider, useAuth } from './useAuth';
import type { User } from '../services/auth';
import { setAppEgressAuditSink, setAppEgressMode } from '../services/egressPolicy';
import { appendLocalExecutionEvent } from '../services/localExecutionEvents';

export type AppSession = {
  mode: AppMode;
  localIdentityId: string | null;
  cloudUser: User | null;
  canUseCloudInference: boolean;
  canSync: boolean;
};

type AppSessionContextValue = {
  session: AppSession | null;
  isLoading: boolean;
  errorCode: string | null;
  startLocalMode: (mode: LocalAppMode) => Promise<void>;
  switchMode: (mode: AppMode) => Promise<void>;
  deleteLocalData: () => Promise<void>;
};

const unavailable = async () => {
  throw new Error('app_session_provider_missing');
};

const AppSessionContext = createContext<AppSessionContextValue>({
  session: null,
  isLoading: true,
  errorCode: null,
  startLocalMode: unavailable,
  switchMode: unavailable,
  deleteLocalData: unavailable,
});

function errorCode(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error);
  for (const code of [
    'device_passcode_required',
    'protected_data_unavailable',
    'vault_key_missing',
    'vault_not_empty',
    'invalid_local_session_preference',
    'native_module_unavailable',
    'local_identity_rollback_failed',
  ]) {
    if (message.includes(code)) return code;
  }
  return 'local_session_failed';
}

function sessionFor(
  preference: AppModePreference,
  cloudUser: User | null,
): AppSession {
  return {
    mode: preference.mode,
    localIdentityId: preference.localIdentityId,
    cloudUser: preference.mode === 'cloud_account' ? cloudUser : null,
    canUseCloudInference: preference.mode !== 'strict_local',
    canSync: preference.mode === 'cloud_account',
  };
}

function ActiveAppSessionProvider({
  children,
  preference,
  setPreference,
  bootstrapError,
}: {
  children: ReactNode;
  preference: AppModePreference | null;
  setPreference: React.Dispatch<React.SetStateAction<AppModePreference | null | undefined>>;
  bootstrapError: string | null;
}) {
  const auth = useAuth();
  const [localReady, setLocalReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [currentError, setCurrentError] = useState<string | null>(bootstrapError);

  useEffect(() => {
    let active = true;
    if (!preference || preference.mode === 'cloud_account') {
      setLocalReady(false);
      return () => {
        active = false;
      };
    }
    setLocalReady(false);
    setCurrentError(null);
    void openLocalHealthVault(preference.localIdentityId as string)
      .then(() => {
        if (active) setLocalReady(true);
      })
      .catch((error) => {
        if (active) setCurrentError(errorCode(error));
      });
    return () => {
      active = false;
    };
  }, [preference]);

  useEffect(() => {
    if (!localReady || !preference?.localIdentityId || preference.mode === 'cloud_account') {
      setAppEgressAuditSink(null);
      return;
    }
    const ownerScope = preference.localIdentityId;
    setAppEgressAuditSink(async () => {
      await appendLocalExecutionEvent(ownerScope, 'privacy_egress_blocked');
    });
    return () => setAppEgressAuditSink(null);
  }, [localReady, preference?.localIdentityId, preference?.mode]);

  useEffect(() => {
    if (preference || auth.isLoading || !auth.isAuthenticated) return;
    const cloudPreference: AppModePreference = {
      schemaVersion: 1,
      mode: 'cloud_account',
      localIdentityId: null,
    };
    void persistAppModePreference(cloudPreference)
      .then(setPreference)
      .catch((error) => setCurrentError(errorCode(error)));
  }, [auth.isAuthenticated, auth.isLoading, preference, setPreference]);

  const startLocalMode = useCallback(async (mode: LocalAppMode) => {
    setBusy(true);
    setCurrentError(null);
    const previousMode = preference?.mode ?? 'cloud_account';
    setAppEgressMode(mode);
    try {
      let next: AppModePreference;
      if (preference?.localIdentityId) {
        await openLocalHealthVault(preference.localIdentityId);
        next = await persistAppModePreference({
          schemaVersion: 1,
          mode,
          localIdentityId: preference.localIdentityId,
        });
      } else {
        next = await createPersistedLocalIdentity(mode);
      }
      setLocalReady(true);
      setAppEgressMode(next.mode);
      setPreference(next);
    } catch (error) {
      setAppEgressMode(previousMode);
      const code = errorCode(error);
      setCurrentError(code);
      throw new Error(code);
    } finally {
      setBusy(false);
    }
  }, [preference, setPreference]);

  const switchMode = useCallback(async (mode: AppMode) => {
    if (mode !== 'cloud_account') {
      await startLocalMode(mode);
      return;
    }
    setBusy(true);
    setCurrentError(null);
    try {
      const next = await persistAppModePreference({
        schemaVersion: 1,
        mode: 'cloud_account',
        localIdentityId: preference?.localIdentityId ?? null,
      });
      setAppEgressMode(next.mode);
      setPreference(next);
    } catch (error) {
      const code = errorCode(error);
      setCurrentError(code);
      throw new Error(code);
    } finally {
      setBusy(false);
    }
  }, [preference?.localIdentityId, setPreference, startLocalMode]);

  const deleteLocalData = useCallback(async () => {
    if (!preference?.localIdentityId || preference.mode === 'cloud_account') {
      throw new Error('local_identity_missing');
    }
    setBusy(true);
    setCurrentError(null);
    let vaultDeleted = false;
    try {
      await deleteLocalHealthVault();
      vaultDeleted = true;
      const next = await persistAppModePreference({
        schemaVersion: 1,
        mode: 'cloud_account',
        localIdentityId: null,
      });
      setLocalReady(false);
      setAppEgressAuditSink(null);
      setAppEgressMode('cloud_account');
      setPreference(next);
    } catch (error) {
      if (vaultDeleted) {
        try {
          await clearAppModePreference();
          setLocalReady(false);
          setAppEgressAuditSink(null);
          setAppEgressMode('cloud_account');
          setPreference(null);
          return;
        } catch {
          const code = 'local_data_deleted_preference_cleanup_failed';
          setCurrentError(code);
          throw new Error(code);
        }
      }
      const code = errorCode(error);
      setCurrentError(code);
      throw new Error(code);
    } finally {
      setBusy(false);
    }
  }, [preference?.localIdentityId, preference?.mode, setPreference]);

  const session = useMemo(() => {
    if (!preference) return null;
    if (preference.mode === 'cloud_account') {
      return auth.isAuthenticated
        ? sessionFor(preference, auth.user)
        : null;
    }
    return localReady ? sessionFor(preference, null) : null;
  }, [auth.isAuthenticated, auth.user, localReady, preference]);

  const value = useMemo<AppSessionContextValue>(() => ({
    session,
    isLoading: busy || auth.isLoading
      || (!!preference && preference.mode !== 'cloud_account' && !localReady && !currentError),
    errorCode: currentError,
    startLocalMode,
    switchMode,
    deleteLocalData,
  }), [auth.isLoading, busy, currentError, localReady, preference, session, startLocalMode, switchMode, deleteLocalData]);

  return <AppSessionContext.Provider value={value}>{children}</AppSessionContext.Provider>;
}

export function AppSessionProvider({ children }: { children: ReactNode }) {
  const [preference, setPreference] = useState<AppModePreference | null | undefined>(undefined);
  const [bootstrapError, setBootstrapError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void loadAppModePreference()
      .then((loaded) => {
        if (active) {
          setAppEgressMode(loaded?.mode ?? 'cloud_account');
          setPreference(loaded);
        }
      })
      .catch((error) => {
        if (active) {
          setAppEgressMode(null);
          setBootstrapError(errorCode(error));
          setPreference(null);
        }
      });
    return () => {
      active = false;
    };
  }, []);

  if (preference === undefined) {
    return (
      <AppSessionContext.Provider value={{
        ...useContextFallback,
        errorCode: bootstrapError,
      }}>
        {children}
      </AppSessionContext.Provider>
    );
  }

  const restoreCloudSession = !bootstrapError
    && (preference === null || preference.mode === 'cloud_account');
  return (
    <AuthProvider restoreCloudSession={restoreCloudSession}>
      <ActiveAppSessionProvider
        preference={preference}
        setPreference={setPreference}
        bootstrapError={bootstrapError}
      >
        {children}
      </ActiveAppSessionProvider>
    </AuthProvider>
  );
}

const useContextFallback: AppSessionContextValue = {
  session: null,
  isLoading: true,
  errorCode: null,
  startLocalMode: unavailable,
  switchMode: unavailable,
  deleteLocalData: unavailable,
};

export function useAppSession(): AppSessionContextValue {
  return useContext(AppSessionContext);
}
