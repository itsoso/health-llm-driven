import { renderHook, waitFor } from '@testing-library/react-native';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

let appStateHandler: ((status: string) => void) | null = null;

jest.mock('react-native', () => ({
  AppState: {
    addEventListener: jest.fn((_event: string, handler: (status: string) => void) => {
      appStateHandler = handler;
      return { remove: jest.fn() };
    }),
  },
}));

const mockMaybeSyncHealthKitOnForeground = jest.fn<Promise<any>, []>(async () => ({
  status: 'synced',
  totalImported: 1,
}));
jest.mock('../../services/healthKitForegroundSync', () => ({
  maybeSyncHealthKitOnForeground: () => mockMaybeSyncHealthKitOnForeground(),
}));

const mockInvalidateHealthSnapshot = jest.fn<Promise<void>, [QueryClient]>(async () => undefined);
jest.mock('../../applib/queryKeys', () => ({
  invalidateHealthSnapshot: (qc: QueryClient) => mockInvalidateHealthSnapshot(qc),
}));

import { useHealthKitForegroundSync } from '../useHealthKitForegroundSync';

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return React.createElement(QueryClientProvider, { client: qc }, children);
}

describe('useHealthKitForegroundSync', () => {
  beforeEach(() => {
    appStateHandler = null;
    mockMaybeSyncHealthKitOnForeground.mockClear();
    mockMaybeSyncHealthKitOnForeground.mockResolvedValue({ status: 'synced', totalImported: 1 });
    mockInvalidateHealthSnapshot.mockClear();
  });

  it('runs on mount and invalidates health snapshot after a successful sync', async () => {
    renderHook(() => useHealthKitForegroundSync(true), { wrapper });

    await waitFor(() => expect(mockMaybeSyncHealthKitOnForeground).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(mockInvalidateHealthSnapshot).toHaveBeenCalledTimes(1));
  });

  it('runs again when the app returns to foreground', async () => {
    renderHook(() => useHealthKitForegroundSync(true), { wrapper });
    await waitFor(() => expect(mockMaybeSyncHealthKitOnForeground).toHaveBeenCalledTimes(1));

    appStateHandler?.('active');

    await waitFor(() => expect(mockMaybeSyncHealthKitOnForeground).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(mockInvalidateHealthSnapshot).toHaveBeenCalledTimes(2));
  });

  it('does not invalidate when sync is skipped', async () => {
    mockMaybeSyncHealthKitOnForeground.mockResolvedValueOnce({ status: 'skipped_cooldown' });

    renderHook(() => useHealthKitForegroundSync(true), { wrapper });

    await waitFor(() => expect(mockMaybeSyncHealthKitOnForeground).toHaveBeenCalledTimes(1));
    expect(mockInvalidateHealthSnapshot).not.toHaveBeenCalled();
  });

  it('does nothing while disabled', async () => {
    renderHook(() => useHealthKitForegroundSync(false), { wrapper });
    await new Promise(resolve => setTimeout(resolve, 20));
    expect(mockMaybeSyncHealthKitOnForeground).not.toHaveBeenCalled();
    expect(mockInvalidateHealthSnapshot).not.toHaveBeenCalled();
  });
});
