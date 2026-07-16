import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from 'react';
import { AppState, type AppStateStatus } from 'react-native';
import {
  applyDownloadedUpdate,
  downloadAvailableUpdate,
  type AppUpdateDownloadResult,
} from '../services/appUpdate';

const DEFAULT_MINIMUM_INTERVAL_MS = 5 * 60 * 1000;

export type AppUpdateStatus =
  | 'idle'
  | 'checking'
  | 'downloading'
  | 'ready'
  | 'applying'
  | 'failed';

export type AppUpdateCheckResult = AppUpdateDownloadResult | 'throttled' | 'failed';

type AppUpdateContextValue = {
  status: AppUpdateStatus;
  error: string | null;
  checkNow: (options?: { force?: boolean }) => Promise<AppUpdateCheckResult>;
  applyUpdate: () => Promise<void>;
  dismiss: () => void;
};

const AppUpdateContext = createContext<AppUpdateContextValue | null>(null);

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : '更新失败，请稍后重试';
}

export function AppUpdateProvider({
  children,
  minimumIntervalMs = DEFAULT_MINIMUM_INTERVAL_MS,
  now = Date.now,
}: {
  children: React.ReactNode;
  minimumIntervalMs?: number;
  now?: () => number;
}) {
  const [status, setStatus] = useState<AppUpdateStatus>('idle');
  const [error, setError] = useState<string | null>(null);
  const statusRef = useRef<AppUpdateStatus>('idle');
  const lastCheckAtRef = useRef<number | null>(null);
  const checkPromiseRef = useRef<Promise<AppUpdateCheckResult> | null>(null);

  const transitionTo = useCallback((nextStatus: AppUpdateStatus) => {
    statusRef.current = nextStatus;
    setStatus(nextStatus);
  }, []);

  const checkNow = useCallback((options?: { force?: boolean }): Promise<AppUpdateCheckResult> => {
    if (checkPromiseRef.current) return checkPromiseRef.current;

    const checkedAt = now();
    const lastCheckedAt = lastCheckAtRef.current;
    if (!options?.force && lastCheckedAt !== null && checkedAt - lastCheckedAt < minimumIntervalMs) {
      return Promise.resolve('throttled');
    }

    lastCheckAtRef.current = checkedAt;
    setError(null);
    const promise = downloadAvailableUpdate(undefined, transitionTo)
      .then((result): AppUpdateCheckResult => {
        transitionTo(result === 'ready' ? 'ready' : 'idle');
        return result;
      })
      .catch((cause): AppUpdateCheckResult => {
        setError(errorMessage(cause));
        transitionTo('failed');
        return 'failed';
      })
      .finally(() => {
        checkPromiseRef.current = null;
      });

    checkPromiseRef.current = promise;
    return promise;
  }, [minimumIntervalMs, now, transitionTo]);

  const applyUpdate = useCallback(async () => {
    if (statusRef.current !== 'ready') return;
    transitionTo('applying');
    setError(null);
    try {
      await applyDownloadedUpdate();
    } catch (cause) {
      setError(errorMessage(cause));
      transitionTo('failed');
    }
  }, [transitionTo]);

  const dismiss = useCallback(() => {
    setError(null);
    transitionTo('idle');
  }, [transitionTo]);

  useEffect(() => {
    void checkNow();
    const subscription = AppState.addEventListener('change', (nextState: AppStateStatus) => {
      if (nextState === 'active') void checkNow();
    });
    return () => subscription.remove();
  }, [checkNow]);

  return (
    <AppUpdateContext.Provider value={{ status, error, checkNow, applyUpdate, dismiss }}>
      {children}
    </AppUpdateContext.Provider>
  );
}

export function useAppUpdate(): AppUpdateContextValue {
  const value = useContext(AppUpdateContext);
  if (!value) throw new Error('useAppUpdate must be used inside AppUpdateProvider');
  return value;
}
