/* eslint-disable import/first */
import React from 'react';
import { AppState } from 'react-native';
import { act, renderHook, waitFor } from '@testing-library/react-native';

jest.mock('../../services/appUpdate', () => ({
  downloadAvailableUpdate: jest.fn(),
  applyDownloadedUpdate: jest.fn(),
}));

import { applyDownloadedUpdate, downloadAvailableUpdate } from '../../services/appUpdate';
import { AppUpdateProvider, useAppUpdate } from '../useAppUpdate';

const mockedDownload = downloadAvailableUpdate as jest.Mock;
const mockedApply = applyDownloadedUpdate as jest.Mock;

describe('AppUpdateProvider', () => {
  let appStateListener: ((state: string) => void) | undefined;
  let now: number;

  beforeEach(() => {
    jest.clearAllMocks();
    now = 1_000_000;
    appStateListener = undefined;
    jest.spyOn(AppState, 'addEventListener').mockImplementation((_, listener: any) => {
      appStateListener = listener;
      return { remove: jest.fn() } as any;
    });
    mockedDownload.mockResolvedValue('current');
    mockedApply.mockResolvedValue(undefined);
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  function wrapper({ children }: { children: React.ReactNode }) {
    return (
      <AppUpdateProvider now={() => now} minimumIntervalMs={300_000}>
        {children}
      </AppUpdateProvider>
    );
  }

  it('checks on mount and exposes a downloaded update as ready', async () => {
    mockedDownload.mockImplementation(async (_adapter: unknown, onPhase: (phase: string) => void) => {
      onPhase('checking');
      onPhase('downloading');
      return 'ready';
    });

    const { result } = renderHook(() => useAppUpdate(), { wrapper });

    await waitFor(() => expect(result.current.status).toBe('ready'));
    expect(mockedDownload).toHaveBeenCalledTimes(1);
  });

  it('throttles foreground checks within five minutes', async () => {
    renderHook(() => useAppUpdate(), { wrapper });
    await waitFor(() => expect(mockedDownload).toHaveBeenCalledTimes(1));

    act(() => appStateListener?.('active'));
    expect(mockedDownload).toHaveBeenCalledTimes(1);

    now += 300_001;
    act(() => appStateListener?.('active'));
    await waitFor(() => expect(mockedDownload).toHaveBeenCalledTimes(2));
  });

  it('allows a manual check to bypass the foreground throttle', async () => {
    const { result } = renderHook(() => useAppUpdate(), { wrapper });
    await waitFor(() => expect(mockedDownload).toHaveBeenCalledTimes(1));

    await act(async () => {
      await result.current.checkNow({ force: true });
    });

    expect(mockedDownload).toHaveBeenCalledTimes(2);
  });

  it('applies only a ready update and reports failures', async () => {
    mockedDownload.mockResolvedValue('ready');
    mockedApply.mockRejectedValue(new Error('reload failed'));
    const { result } = renderHook(() => useAppUpdate(), { wrapper });
    await waitFor(() => expect(result.current.status).toBe('ready'));

    await act(async () => {
      await result.current.applyUpdate();
    });

    expect(mockedApply).toHaveBeenCalledTimes(1);
    expect(result.current.status).toBe('failed');
    expect(result.current.error).toBe('reload failed');
  });

  it('can apply immediately after a forced check without waiting for another render', async () => {
    const { result } = renderHook(() => useAppUpdate(), { wrapper });
    await waitFor(() => expect(mockedDownload).toHaveBeenCalledTimes(1));
    mockedDownload.mockResolvedValue('ready');
    const actions = result.current;

    await act(async () => {
      await actions.checkNow({ force: true });
      await actions.applyUpdate();
    });

    expect(mockedApply).toHaveBeenCalledTimes(1);
  });
});
