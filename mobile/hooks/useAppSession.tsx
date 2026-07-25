import AsyncStorage from '@react-native-async-storage/async-storage';
import React, {
  createContext,
  useContext,
  useEffect,
  useMemo,
  type ReactNode,
} from 'react';

import { AuthProvider, useAuth } from './useAuth';
import type { User } from '../services/auth';
import { setAppEgressMode } from '../services/egressPolicy';

const RETIRED_APP_MODE_STORAGE_KEY = 'reva_app_mode_preference_v1';

export type AppSession = {
  mode: 'cloud_account';
  cloudUser: User;
};

type AppSessionContextValue = {
  session: AppSession | null;
  isLoading: boolean;
  errorCode: null;
};

const AppSessionContext = createContext<AppSessionContextValue>({
  session: null,
  isLoading: true,
  errorCode: null,
});

function CloudSessionProvider({ children }: { children: ReactNode }) {
  const auth = useAuth();
  useEffect(() => {
    setAppEgressMode(auth.isAuthenticated ? 'cloud_account' : null);
    return () => setAppEgressMode(null);
  }, [auth.isAuthenticated]);
  const session = useMemo<AppSession | null>(() => {
    if (!auth.isAuthenticated || !auth.user) return null;
    return {
      mode: 'cloud_account',
      cloudUser: auth.user,
    };
  }, [auth.isAuthenticated, auth.user]);

  const value = useMemo<AppSessionContextValue>(() => ({
    session,
    isLoading: auth.isLoading,
    errorCode: null,
  }), [auth.isLoading, session]);

  return <AppSessionContext.Provider value={value}>{children}</AppSessionContext.Provider>;
}

export function AppSessionProvider({ children }: { children: ReactNode }) {
  useEffect(() => {
    // Retire the old routing preference without deleting the user's on-device
    // vault. The cloud-only build must never reopen it or package local AI.
    void AsyncStorage.removeItem(RETIRED_APP_MODE_STORAGE_KEY).catch((error) => {
      console.warn('[AppSession] failed to retire local-mode preference', error);
    });
  }, []);

  return (
    <AuthProvider restoreCloudSession>
      <CloudSessionProvider>{children}</CloudSessionProvider>
    </AuthProvider>
  );
}

export function useAppSession(): AppSessionContextValue {
  return useContext(AppSessionContext);
}
