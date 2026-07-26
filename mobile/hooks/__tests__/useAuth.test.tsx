import React from 'react';
import { AppState, Text } from 'react-native';
import { act, render, screen, waitFor } from '@testing-library/react-native';

let unauthorizedHandler: (() => void) | null = null;

jest.mock('../../services/api', () => ({
  setOnUnauthorized: jest.fn((cb) => {
    unauthorizedHandler = cb;
  }),
}));

jest.mock('../../services/auth', () => ({
  login: jest.fn(),
  logout: jest.fn(),
  getToken: jest.fn(),
  fetchCurrentUser: jest.fn(),
}));

jest.mock('../../modules/shared-keychain', () => ({
  saveTokenToSharedKeychain: jest.fn().mockResolvedValue(0),
  readTokenFromSharedKeychain: jest.fn().mockResolvedValue(null),
}));

import { AuthProvider, useAuth } from '../useAuth';
import { getToken, fetchCurrentUser, logout } from '../../services/auth';

function Probe() {
  const auth = useAuth();
  return (
    <Text testID="state">
      {auth.isLoading
        ? 'loading'
        : auth.isAuthenticated
          ? auth.user
            ? 'auth+user'
            : 'auth'
          : auth.user
            ? 'guest+stale-user'
            : 'guest'}
    </Text>
  );
}

describe('useAuth update resilience', () => {
  let appStateHandler: ((state: string) => void) | null = null;

  beforeEach(() => {
    jest.clearAllMocks();
    unauthorizedHandler = null;
    appStateHandler = null;
    jest.spyOn(AppState, 'addEventListener').mockImplementation(((_type: string, handler: (state: string) => void) => {
      appStateHandler = handler;
      return { remove: jest.fn() };
    }) as never);
  });

  it('clears an expired saved token when user hydration returns 401', async () => {
    (getToken as jest.Mock).mockResolvedValueOnce('tok_saved');
    (fetchCurrentUser as jest.Mock).mockRejectedValueOnce({ response: { status: 401 } });

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );

    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('guest'));
    expect(logout).toHaveBeenCalledTimes(1);
  });

  it('keeps the app authenticated when token storage is briefly unavailable after an update', async () => {
    (getToken as jest.Mock)
      .mockResolvedValueOnce(null)
      .mockResolvedValueOnce('tok_saved');
    (fetchCurrentUser as jest.Mock).mockResolvedValueOnce({ id: 3, username: 'q' });

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );

    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('auth+user'));
    expect(getToken).toHaveBeenCalledTimes(2);
  });

  it('clears the current session after an authenticated API returns 401', async () => {
    (getToken as jest.Mock).mockResolvedValueOnce('tok_saved');
    (fetchCurrentUser as jest.Mock).mockResolvedValueOnce({ id: 3, username: 'q' });

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );

    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('auth+user'));
    act(() => {
      unauthorizedHandler?.();
    });

    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('guest'));
    expect(logout).toHaveBeenCalledTimes(1);
  });

  it('foreground self-heal: token becomes readable after a failed cold-start restore', async () => {
    (getToken as jest.Mock).mockResolvedValue(null); // 冷启动 3 次尝试全空 → 落在登录页

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );

    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('guest'));

    (getToken as jest.Mock).mockResolvedValue('tok_recovered');
    (fetchCurrentUser as jest.Mock).mockResolvedValueOnce({ id: 3, username: 'q' });

    await act(async () => {
      appStateHandler?.('active');
    });

    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('auth+user'));
  });

  it('foreground self-heal: re-hydrates the user after a transient cold-start /auth/me failure', async () => {
    (getToken as jest.Mock).mockResolvedValueOnce('tok_saved');
    (fetchCurrentUser as jest.Mock)
      .mockRejectedValueOnce(new Error('network down during app update'))
      .mockResolvedValueOnce({ id: 3, username: 'q' });

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );

    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('auth'));

    await act(async () => {
      appStateHandler?.('active');
    });

    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('auth+user'));
    expect(fetchCurrentUser).toHaveBeenCalledTimes(2);
  });

  it('does not restore a stale user after the session is cleared during foreground hydration', async () => {
    let resolveForegroundUser: ((user: { id: number; username: string }) => void) | null = null;
    (getToken as jest.Mock).mockResolvedValueOnce('tok_saved');
    (fetchCurrentUser as jest.Mock)
      .mockRejectedValueOnce(new Error('temporary network failure'))
      .mockImplementationOnce(() => new Promise((resolve) => {
        resolveForegroundUser = resolve;
      }));

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );

    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('auth'));

    act(() => {
      appStateHandler?.('active');
    });
    await waitFor(() => expect(fetchCurrentUser).toHaveBeenCalledTimes(2));

    act(() => {
      unauthorizedHandler?.();
    });
    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('guest'));

    await act(async () => {
      resolveForegroundUser?.({ id: 3, username: 'old-user' });
    });

    expect(screen.getByTestId('state')).toHaveTextContent('guest');
    expect(screen.getByTestId('state')).not.toHaveTextContent('stale-user');
  });

  it('unregisters the global unauthorized callback when the provider unmounts', async () => {
    (getToken as jest.Mock).mockResolvedValue(null);

    const view = render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('guest'));

    view.unmount();

    expect(unauthorizedHandler).toBeNull();
  });
});
