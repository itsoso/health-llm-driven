/**
 * Sentry bootstrap — imported for side-effect at the top of app/_layout.tsx.
 *
 * Why the top of the file: `Sentry.init` must run before any other code that
 * might throw, so import-time native module crashes (e.g. shared-keychain)
 * still get reported. Putting `init` inside the route layout component means
 * any bug in the imports *above* that component is lost.
 *
 * PII is disabled because HealthPilot stores medical data; do not flip that
 * flag without a privacy review.
 */

import * as Sentry from '@sentry/react-native';
import Constants from 'expo-constants';

const SENTRY_DSN =
  process.env.EXPO_PUBLIC_SENTRY_DSN ||
  (Constants.expoConfig?.extra as { sentryDsn?: string } | undefined)?.sentryDsn;

if (SENTRY_DSN) {
  Sentry.init({
    dsn: SENTRY_DSN,
    enableAutoSessionTracking: true,
    enabled: !__DEV__,
    environment: __DEV__ ? 'development' : 'production',
    sendDefaultPii: false,
    tracesSampleRate: 0.1,
  });
}

export const SENTRY_ENABLED = !!SENTRY_DSN;
export { Sentry };
