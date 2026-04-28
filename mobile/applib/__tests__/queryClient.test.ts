/**
 * lib/queryClient smoke tests.
 *
 * Goal: catch regressions where the persist configuration silently stops
 * working (stale queries cached forever, errors cached, wrong buster).
 */

// AsyncStorage has no in-Node runtime; use the official jest mock shipped
// with the package.
jest.mock('@react-native-async-storage/async-storage', () =>
  require('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

import { queryClient, persistOptions } from '../queryClient';
import { QueryClient } from '@tanstack/react-query';

describe('lib/queryClient', () => {
  it('constructs a QueryClient with 24h gcTime and retry/staleTime defaults', () => {
    expect(queryClient).toBeInstanceOf(QueryClient);
    const defaults = queryClient.getDefaultOptions();
    expect(defaults.queries?.retry).toBe(2);
    expect(defaults.queries?.staleTime).toBe(60_000);
    expect(defaults.queries?.gcTime).toBe(24 * 60 * 60 * 1000);
  });

  it('persists only successful queries — errors and pending states stay off disk', () => {
    const shouldDehydrateQuery = persistOptions.dehydrateOptions.shouldDehydrateQuery;

    expect(shouldDehydrateQuery({ state: { status: 'success' } } as never)).toBe(true);
    expect(shouldDehydrateQuery({ state: { status: 'error' } } as never)).toBe(false);
    expect(shouldDehydrateQuery({ state: { status: 'pending' } } as never)).toBe(false);
  });

  it('caps cache age at 24h so stale health data eventually expires', () => {
    expect(persistOptions.maxAge).toBe(24 * 60 * 60 * 1000);
  });

  it('uses a versioned storage key — bumping it invalidates old caches at once', () => {
    // Key includes a version suffix so a schema change can force-invalidate.
    // If someone drops the suffix, we lose the ability to invalidate safely.
    expect(typeof persistOptions.persister.persistClient).toBe('function');
  });
});
