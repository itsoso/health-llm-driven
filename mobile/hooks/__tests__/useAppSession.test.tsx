/* eslint-disable import/first */
import React from 'react';
import { Text } from 'react-native';
import { act, fireEvent, render, waitFor } from '@testing-library/react-native';

const mockOpenVault = jest.fn();
const mockCreateVault = jest.fn();
const mockDeleteVault = jest.fn();
const mockLoadPreference = jest.fn();
const mockPersistPreference = jest.fn();
const mockCreateIdentity = jest.fn();
const mockClearPreference = jest.fn();
let mockAuth = {
  user: null as null | { id: number; username: string },
  token: null as string | null,
  isLoading: false,
  isAuthenticated: false,
};
let mockRestoreCloudSession: boolean | undefined;

jest.mock('../useAuth', () => ({
  AuthProvider: ({
    children,
    restoreCloudSession,
  }: {
    children: React.ReactNode;
    restoreCloudSession?: boolean;
  }) => {
    mockRestoreCloudSession = restoreCloudSession;
    return <>{children}</>;
  },
  useAuth: () => mockAuth,
}));

jest.mock('../../modules/local-health-kernel', () => ({
  createLocalHealthVault: (...args: unknown[]) => mockCreateVault(...args),
  openLocalHealthVault: (...args: unknown[]) => mockOpenVault(...args),
  deleteLocalHealthVault: (...args: unknown[]) => mockDeleteVault(...args),
}));

jest.mock('../../services/localIdentity', () => ({
  loadAppModePreference: (...args: unknown[]) => mockLoadPreference(...args),
  persistAppModePreference: (...args: unknown[]) => mockPersistPreference(...args),
  createPersistedLocalIdentity: (...args: unknown[]) => mockCreateIdentity(...args),
  clearAppModePreference: (...args: unknown[]) => mockClearPreference(...args),
}));

import { AppSessionProvider, useAppSession } from '../useAppSession';

function Probe() {
  const app = useAppSession();
  return (
    <>
      <Text testID="loading">{String(app.isLoading)}</Text>
      <Text testID="mode">{app.session?.mode ?? 'none'}</Text>
      <Text testID="error">{app.errorCode ?? 'none'}</Text>
      <Text onPress={() => void app.startLocalMode('strict_local').catch(() => undefined)}>start-local</Text>
      <Text onPress={() => void app.switchMode('cloud_account')}>switch-cloud</Text>
      <Text onPress={() => void app.deleteLocalData().catch(() => undefined)}>delete-local</Text>
    </>
  );
}

describe('AppSessionProvider', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockAuth = {
      user: null,
      token: null,
      isLoading: false,
      isAuthenticated: false,
    };
    mockRestoreCloudSession = undefined;
    mockLoadPreference.mockResolvedValue(null);
    mockPersistPreference.mockImplementation(async (value) => value);
    mockCreateIdentity.mockResolvedValue({
      schemaVersion: 1,
      mode: 'strict_local',
      localIdentityId: 'local-created',
    });
    mockOpenVault.mockResolvedValue(undefined);
    mockDeleteVault.mockResolvedValue(undefined);
    mockClearPreference.mockResolvedValue(undefined);
  });

  it('crypto-shreds local data and forgets the identity only after deletion succeeds', async () => {
    mockLoadPreference.mockResolvedValue({
      schemaVersion: 1,
      mode: 'strict_local',
      localIdentityId: 'local-existing',
    });
    const screen = render(<AppSessionProvider><Probe /></AppSessionProvider>);
    await waitFor(() => expect(screen.getByTestId('mode')).toHaveTextContent('strict_local'));

    await act(async () => {
      fireEvent.press(screen.getByText('delete-local'));
    });

    expect(mockDeleteVault).toHaveBeenCalledTimes(1);
    expect(mockPersistPreference).toHaveBeenCalledWith({
      schemaVersion: 1,
      mode: 'cloud_account',
      localIdentityId: null,
    });
    expect(screen.getByTestId('mode')).toHaveTextContent('none');
  });

  it('does not report deletion as failed when only the mode preference write fails', async () => {
    mockLoadPreference.mockResolvedValue({
      schemaVersion: 1,
      mode: 'strict_local',
      localIdentityId: 'local-existing',
    });
    mockPersistPreference.mockRejectedValueOnce(new Error('preference_write_failed'));
    const screen = render(<AppSessionProvider><Probe /></AppSessionProvider>);
    await waitFor(() => expect(screen.getByTestId('mode')).toHaveTextContent('strict_local'));

    await act(async () => {
      fireEvent.press(screen.getByText('delete-local'));
    });

    expect(mockDeleteVault).toHaveBeenCalledTimes(1);
    expect(mockClearPreference).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('mode')).toHaveTextContent('none');
    expect(screen.getByTestId('error')).toHaveTextContent('none');
  });

  it('preserves an existing authenticated user as cloud account mode', async () => {
    mockAuth = {
      user: { id: 7, username: 'cloud-user' },
      token: 'token',
      isLoading: false,
      isAuthenticated: true,
    };
    const screen = render(<AppSessionProvider><Probe /></AppSessionProvider>);

    await waitFor(() => expect(screen.getByTestId('mode')).toHaveTextContent('cloud_account'));
    expect(mockPersistPreference).toHaveBeenCalledWith({
      schemaVersion: 1,
      mode: 'cloud_account',
      localIdentityId: null,
    });
    expect(mockRestoreCloudSession).toBe(true);
  });

  it('reopens strict local mode without any login request', async () => {
    mockLoadPreference.mockResolvedValue({
      schemaVersion: 1,
      mode: 'strict_local',
      localIdentityId: 'local-existing',
    });
    const screen = render(<AppSessionProvider><Probe /></AppSessionProvider>);

    await waitFor(() => expect(screen.getByTestId('mode')).toHaveTextContent('strict_local'));
    expect(mockOpenVault).toHaveBeenCalledWith('local-existing');
    expect(mockPersistPreference).not.toHaveBeenCalled();
    expect(mockRestoreCloudSession).toBe(false);
  });

  it('enters local mode only after native vault creation succeeds', async () => {
    const screen = render(<AppSessionProvider><Probe /></AppSessionProvider>);
    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'));

    await act(async () => {
      fireEvent.press(screen.getByText('start-local'));
    });

    expect(mockCreateIdentity).toHaveBeenCalledWith('strict_local');
    expect(screen.getByTestId('mode')).toHaveTextContent('strict_local');
  });

  it('surfaces passcode setup guidance and keeps the fresh session empty', async () => {
    mockCreateIdentity.mockRejectedValue(new Error('device_passcode_required'));
    const screen = render(<AppSessionProvider><Probe /></AppSessionProvider>);
    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'));

    await act(async () => {
      fireEvent.press(screen.getByText('start-local'));
    });

    expect(screen.getByTestId('mode')).toHaveTextContent('none');
    expect(screen.getByTestId('error')).toHaveTextContent('device_passcode_required');
  });

  it('switches to cloud without deleting the retained local identity', async () => {
    mockLoadPreference.mockResolvedValue({
      schemaVersion: 1,
      mode: 'strict_local',
      localIdentityId: 'local-existing',
    });
    const screen = render(<AppSessionProvider><Probe /></AppSessionProvider>);
    await waitFor(() => expect(screen.getByTestId('mode')).toHaveTextContent('strict_local'));

    await act(async () => {
      fireEvent.press(screen.getByText('switch-cloud'));
    });

    expect(mockPersistPreference).toHaveBeenCalledWith({
      schemaVersion: 1,
      mode: 'cloud_account',
      localIdentityId: 'local-existing',
    });
    expect(screen.getByTestId('mode')).toHaveTextContent('none');
  });
});
