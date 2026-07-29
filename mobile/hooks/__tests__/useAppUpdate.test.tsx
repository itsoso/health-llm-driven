/* eslint-disable import/first */
import React from 'react';
import { AppState } from 'react-native';
import { act, renderHook, waitFor } from '@testing-library/react-native';

jest.mock('../../services/appUpdate', () => ({
  downloadAvailableUpdate: jest.fn(),
  applyDownloadedUpdate: jest.fn(),
  getAppUpdateLaunchSource: jest.fn().mockReturnValue('embedded'),
  getAppUpdateTelemetryContext: jest.fn().mockReturnValue({
    platform: 'ios',
    channel: 'production',
    runtime: '1.3.1',
    native_build: '190',
  }),
}));

jest.mock('expo-linking', () => ({
  canOpenURL: jest.fn().mockResolvedValue(true),
  openURL: jest.fn().mockResolvedValue(undefined),
}));

jest.mock('../../services/clientEvents', () => ({
  durationBucket: jest.fn().mockReturnValue('lt_1s'),
  emitClientEvent: jest.fn(),
}));

jest.mock('../../services/appReloadPreparation', () => ({
  prepareForAppReload: jest.fn().mockResolvedValue(undefined),
}));

jest.mock('../../services/remoteConfig', () => ({
  getReleasePolicyRolloutBucket: jest.fn().mockResolvedValue(0),
  getNativeUpdateRequirement: jest.fn().mockReturnValue('none'),
  isReleasePolicyEligible: jest.fn().mockReturnValue(true),
  loadReleasePolicy: jest.fn().mockResolvedValue({
    config_version: 0,
    platform: 'ios',
    channel: 'production',
    ota_enabled: true,
    rollout_percent: 100,
    minimum_native_build: null,
    recommended_native_build: null,
    forced_update: false,
    kill_switches: {},
    rollback_update_id: null,
    expires_at: null,
    source: 'safe_default',
  }),
}));

import { applyDownloadedUpdate, downloadAvailableUpdate } from '../../services/appUpdate';
import { prepareForAppReload } from '../../services/appReloadPreparation';
import { emitClientEvent } from '../../services/clientEvents';
import { loadReleasePolicy } from '../../services/remoteConfig';
import { AppUpdateProvider, useAppUpdate } from '../useAppUpdate';

const mockedDownload = downloadAvailableUpdate as jest.Mock;
const mockedApply = applyDownloadedUpdate as jest.Mock;
const mockedPrepareForReload = prepareForAppReload as jest.Mock;
const mockedEmit = emitClientEvent as jest.Mock;
const mockedLoadPolicy = loadReleasePolicy as jest.Mock;

describe('AppUpdateProvider', () => {
  let appStateListener: ((state: string) => void) | undefined;
  let now: number;

  beforeEach(() => {
    jest.clearAllMocks();
    const { getNativeUpdateRequirement } = jest.requireMock('../../services/remoteConfig') as {
      getNativeUpdateRequirement: jest.Mock;
    };
    getNativeUpdateRequirement.mockReturnValue('none');
    now = 1_000_000;
    appStateListener = undefined;
    jest.spyOn(AppState, 'addEventListener').mockImplementation((_, listener: any) => {
      appStateListener = listener;
      return { remove: jest.fn() } as any;
    });
    mockedDownload.mockResolvedValue('current');
    mockedApply.mockResolvedValue(undefined);
    mockedPrepareForReload.mockResolvedValue(undefined);
    mockedLoadPolicy.mockResolvedValue({
      config_version: 0,
      platform: 'ios',
      channel: 'production',
      ota_enabled: true,
      rollout_percent: 100,
      minimum_native_build: null,
      recommended_native_build: null,
      forced_update: false,
      kill_switches: {},
      rollback_update_id: null,
      expires_at: null,
      source: 'safe_default',
    });
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
    expect(mockedEmit).toHaveBeenCalledWith('app_update_launch', expect.objectContaining({
      launch_source: 'embedded',
    }));
    expect(mockedEmit).toHaveBeenCalledWith('app_update_terminal', expect.objectContaining({
      phase: 'ready',
    }));
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

  it('persists active UI state before applying a downloaded update', async () => {
    mockedDownload.mockResolvedValue('ready');
    const order: string[] = [];
    mockedPrepareForReload.mockImplementation(async () => {
      order.push('prepare');
    });
    mockedApply.mockImplementation(async () => {
      order.push('reload');
    });
    const { result } = renderHook(() => useAppUpdate(), { wrapper });
    await waitFor(() => expect(result.current.status).toBe('ready'));

    await act(async () => {
      await result.current.applyUpdate();
    });

    expect(order).toEqual(['prepare', 'reload']);
  });

  it('does not reload when active UI state cannot be persisted', async () => {
    mockedDownload.mockResolvedValue('ready');
    mockedPrepareForReload.mockRejectedValue(new Error('无法安全保存当前内容，请稍后重试更新'));
    const { result } = renderHook(() => useAppUpdate(), { wrapper });
    await waitFor(() => expect(result.current.status).toBe('ready'));

    await act(async () => {
      await result.current.applyUpdate();
    });

    expect(mockedApply).not.toHaveBeenCalled();
    expect(result.current.status).toBe('failed');
    expect(result.current.error).toBe('无法安全保存当前内容，请稍后重试更新');
  });

  it('keeps a forced update non-dismissible after the bundle is ready', async () => {
    mockedLoadPolicy.mockResolvedValue({
      config_version: 1,
      platform: 'ios',
      channel: 'production',
      ota_enabled: true,
      rollout_percent: 100,
      minimum_native_build: null,
      recommended_native_build: null,
      forced_update: true,
      kill_switches: {},
      rollback_update_id: null,
      expires_at: null,
      source: 'remote',
    });
    mockedDownload.mockResolvedValue('ready');
    const { result } = renderHook(() => useAppUpdate(), { wrapper });

    await waitFor(() => expect(result.current.status).toBe('ready'));
    expect(result.current.isForced).toBe(true);

    act(() => result.current.dismiss());
    expect(result.current.status).toBe('ready');
  });

  it('does not download OTA when the native build is below the minimum', async () => {
    const { getNativeUpdateRequirement } = jest.requireMock('../../services/remoteConfig') as {
      getNativeUpdateRequirement: jest.Mock;
    };
    getNativeUpdateRequirement.mockReturnValue('required');
    mockedLoadPolicy.mockResolvedValue({
      config_version: 2,
      platform: 'ios',
      channel: 'production',
      ota_enabled: true,
      rollout_percent: 100,
      minimum_native_build: '227',
      recommended_native_build: '228',
      native_update_url: 'https://apps.apple.com/app/id123456789',
      forced_update: false,
      kill_switches: {},
      rollback_update_id: null,
      expires_at: null,
      source: 'remote',
    });

    const { result } = renderHook(() => useAppUpdate(), { wrapper });

    await waitFor(() => expect(result.current.nativeUpdateRequirement).toBe('required'));
    expect(result.current.status).toBe('idle');
    expect(result.current.nativeUpdateUrl).toBe('https://apps.apple.com/app/id123456789');
    expect(mockedDownload).not.toHaveBeenCalled();
  });

  it('allows OTA while exposing a recommended native update', async () => {
    const { getNativeUpdateRequirement } = jest.requireMock('../../services/remoteConfig') as {
      getNativeUpdateRequirement: jest.Mock;
    };
    getNativeUpdateRequirement.mockReturnValue('recommended');
    mockedLoadPolicy.mockResolvedValue({
      config_version: 2,
      platform: 'ios',
      channel: 'production',
      ota_enabled: true,
      rollout_percent: 100,
      minimum_native_build: '190',
      recommended_native_build: '228',
      native_update_url: 'https://apps.apple.com/app/id123456789',
      forced_update: false,
      kill_switches: {},
      rollback_update_id: null,
      expires_at: null,
      source: 'remote',
    });

    const { result } = renderHook(() => useAppUpdate(), { wrapper });

    await waitFor(() => expect(mockedDownload).toHaveBeenCalledTimes(1));
    expect(result.current.nativeUpdateRequirement).toBe('recommended');
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
