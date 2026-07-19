/**
 * Sentry bootstrap — imported for side-effect at the top of app/_layout.tsx.
 *
 * The SDK is imported at bootstrap, but initialization is deferred until the
 * persisted app mode is known. A strict-local launch must not create a Sentry
 * session before the local privacy boundary has loaded.
 *
 * PII is disabled because HealthPilot stores medical data; do not flip that
 * flag without a privacy review.
 */

import * as Sentry from '@sentry/react-native';
import Constants from 'expo-constants';

const SENTRY_DSN =
  process.env.EXPO_PUBLIC_SENTRY_DSN ||
  (Constants.expoConfig?.extra as { sentryDsn?: string } | undefined)?.sentryDsn;

let configuredMode: 'cloud' | 'local' | null = null;

export function configureSentryForAppMode(mode: 'cloud' | 'local'): void {
  if (!SENTRY_DSN || configuredMode === mode) return;
  configuredMode = mode;
  Sentry.init({
    dsn: SENTRY_DSN,
    enableAutoSessionTracking: mode === 'cloud',
    enabled: mode === 'cloud' && !__DEV__,
    environment: __DEV__ ? 'development' : 'production',
    sendDefaultPii: false,
    tracesSampleRate: mode === 'cloud' ? 0.1 : 0,
    beforeSend: mode === 'cloud' ? undefined : () => null,
    beforeSendTransaction: mode === 'cloud' ? undefined : () => null,
  });
}

export const SENTRY_ENABLED = !!SENTRY_DSN;
export { Sentry };
