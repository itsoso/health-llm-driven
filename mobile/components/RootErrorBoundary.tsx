import React from 'react';
import { ErrorBoundary as REBErrorBoundary, type FallbackProps } from 'react-error-boundary';
import { useQueryClient } from '@tanstack/react-query';
import ErrorFallback from './ErrorFallback';
import { Sentry } from '../applib/sentry';

/**
 * App-level error boundary.
 *
 * What this catches that expo-router's built-in ErrorBoundary does NOT:
 *   - errors thrown from inside event handlers (e.g. onPress → API call that throws)
 *   - async errors from hooks that reach React render
 *   - anything thrown outside a route component tree
 *
 * Integrates with react-query: resetQueries on "重试", so the user gets a real
 * retry instead of the same stale error state.
 *
 * Also forwards the error to Sentry so we see the crash server-side.
 */
function FallbackWithReset({ error, resetErrorBoundary }: FallbackProps) {
  const qc = useQueryClient();
  return (
    <ErrorFallback
      error={error instanceof Error ? error : new Error(String(error))}
      onRetry={() => {
        qc.resetQueries();
        resetErrorBoundary();
      }}
    />
  );
}

export default function RootErrorBoundary({ children }: { children: React.ReactNode }) {
  return (
    <REBErrorBoundary
      FallbackComponent={FallbackWithReset}
      onError={(error, info) => {
        Sentry.captureException(error, {
          contexts: { react: { componentStack: info.componentStack } },
        });
      }}
    >
      {children}
    </REBErrorBoundary>
  );
}
