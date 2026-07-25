/* eslint-disable import/first */
import React from 'react';
import { Text } from 'react-native';
import { render } from '@testing-library/react-native';

const mockRemoveItem = jest.fn();
let mockAuth = {
  user: null as null | { id: number; username: string },
  token: null as string | null,
  isLoading: false,
  isAuthenticated: false,
};
let mockRestoreCloudSession: boolean | undefined;

jest.mock('@react-native-async-storage/async-storage', () => ({
  removeItem: (...args: unknown[]) => mockRemoveItem(...args),
}));

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

import { AppSessionProvider, useAppSession } from '../useAppSession';

function Probe() {
  const app = useAppSession();
  return (
    <>
      <Text testID="loading">{String(app.isLoading)}</Text>
      <Text testID="mode">{app.session?.mode ?? 'none'}</Text>
    </>
  );
}

describe('AppSessionProvider cloud-only runtime', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockAuth = {
      user: null,
      token: null,
      isLoading: false,
      isAuthenticated: false,
    };
    mockRestoreCloudSession = undefined;
    mockRemoveItem.mockResolvedValue(undefined);
  });

  it('restores only the cloud account session and retires the old local-mode preference', () => {
    mockAuth = {
      user: { id: 7, username: 'cloud-user' },
      token: 'token',
      isLoading: false,
      isAuthenticated: true,
    };

    const screen = render(<AppSessionProvider><Probe /></AppSessionProvider>);

    expect(screen.getByTestId('mode')).toHaveTextContent('cloud_account');
    expect(mockRestoreCloudSession).toBe(true);
    expect(mockRemoveItem).toHaveBeenCalledWith('reva_app_mode_preference_v1');
  });

  it('requires cloud authentication instead of creating an offline session', () => {
    const screen = render(<AppSessionProvider><Probe /></AppSessionProvider>);

    expect(screen.getByTestId('mode')).toHaveTextContent('none');
    expect(screen.getByTestId('loading')).toHaveTextContent('false');
    expect(mockRestoreCloudSession).toBe(true);
  });
});
