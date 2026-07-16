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
  getAppUpdateLaunchSource,
  getAppUpdateTelemetryContext,
  type AppUpdateDownloadResult,
} from '../services/appUpdate';
import { durationBucket, emitClientEvent } from '../services/clientEvents';
import {
  getReleasePolicyRolloutBucket,
  isReleasePolicyEligible,
  loadReleasePolicy,
} from '../services/remoteConfig';

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
  isForced: boolean;
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
  const [isForced, setIsForced] = useState(false);
  const statusRef = useRef<AppUpdateStatus>('idle');
  const lastCheckAtRef = useRef<number | null>(null);
  const checkPromiseRef = useRef<Promise<AppUpdateCheckResult> | null>(null);

  const emitUpdateEvent = useCallback((
    name: 'app_update_phase' | 'app_update_terminal' | 'app_update_launch',
    meta: Record<string, unknown>,
  ) => {
    void emitClientEvent(name, {
      ...getAppUpdateTelemetryContext(),
      ...meta,
    });
  }, []);

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
    const startedAt = checkedAt;
    setError(null);
    setIsForced(false);
    const promise = loadReleasePolicy()
      .then(async (policy) => {
        const rolloutBucket = await getReleasePolicyRolloutBucket();
        const nativeBuild = getAppUpdateTelemetryContext().native_build;
        if (!isReleasePolicyEligible(policy, nativeBuild, rolloutBucket)) {
          setIsForced(false);
          transitionTo('idle');
          return 'disabled' as AppUpdateDownloadResult;
        }
        setIsForced(policy.forced_update);
        return downloadAvailableUpdate(undefined, (phase) => {
          transitionTo(phase);
          emitUpdateEvent('app_update_phase', { phase });
        });
      })
      .then((result): AppUpdateCheckResult => {
        transitionTo(result === 'ready' ? 'ready' : 'idle');
        emitUpdateEvent('app_update_terminal', {
          phase: result,
          duration_bucket: durationBucket(startedAt, now()),
        });
        return result;
      })
      .catch((cause): AppUpdateCheckResult => {
        setError(errorMessage(cause));
        setIsForced(false);
        transitionTo('failed');
        emitUpdateEvent('app_update_terminal', {
          phase: 'failed',
          duration_bucket: durationBucket(startedAt, now()),
          error_code: 'check_failed',
        });
        return 'failed';
      })
      .finally(() => {
        checkPromiseRef.current = null;
      });

    checkPromiseRef.current = promise;
    return promise;
  }, [emitUpdateEvent, minimumIntervalMs, now, transitionTo]);

  const applyUpdate = useCallback(async () => {
    if (statusRef.current !== 'ready') return;
    transitionTo('applying');
    setError(null);
    const startedAt = now();
    emitUpdateEvent('app_update_phase', { phase: 'applying' });
    try {
      await applyDownloadedUpdate();
      emitUpdateEvent('app_update_terminal', {
        phase: 'applied',
        duration_bucket: durationBucket(startedAt, now()),
      });
    } catch (cause) {
      setError(errorMessage(cause));
      setIsForced(false);
      transitionTo('failed');
      emitUpdateEvent('app_update_terminal', {
        phase: 'failed',
        duration_bucket: durationBucket(startedAt, now()),
        error_code: 'apply_failed',
      });
    }
  }, [emitUpdateEvent, now, transitionTo]);

  const dismiss = useCallback(() => {
    if (isForced) return;
    setError(null);
    transitionTo('idle');
  }, [isForced, transitionTo]);

  useEffect(() => {
    emitUpdateEvent('app_update_launch', {
      launch_source: getAppUpdateLaunchSource(),
    });
    void checkNow();
    const subscription = AppState.addEventListener('change', (nextState: AppStateStatus) => {
      if (nextState === 'active') void checkNow();
    });
    return () => subscription.remove();
  }, [checkNow, emitUpdateEvent]);

  return (
    <AppUpdateContext.Provider value={{ status, error, isForced, checkNow, applyUpdate, dismiss }}>
      {children}
    </AppUpdateContext.Provider>
  );
}

export function useAppUpdate(): AppUpdateContextValue {
  const value = useContext(AppUpdateContext);
  if (!value) throw new Error('useAppUpdate must be used inside AppUpdateProvider');
  return value;
}
