import React from 'react';
import { AppState, Text } from 'react-native';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';

let unauthorizedHandler: (() => void) | null = null;
let mockHadPersistedSession = false;

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

jest.mock('../../services/authSessionMarker', () => ({
  hasPersistedSessionMarker: jest.fn(async () => mockHadPersistedSession),
  markPersistedSession: jest.fn(async () => {
    mockHadPersistedSession = true;
  }),
  clearPersistedSessionMarker: jest.fn(async () => {
    mockHadPersistedSession = false;
  }),
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
    <>
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
      <Text testID="logout" onPress={() => void auth.logout()}>logout</Text>
    </>
  );
}

describe('useAuth update resilience', () => {
  let appStateHandler: ((state: string) => void) | null = null;

  beforeEach(() => {
    jest.clearAllMocks();
    unauthorizedHandler = null;
    appStateHandler = null;
    mockHadPersistedSession = false;
    jest.spyOn(AppState, 'addEventListener').mockImplementation(((_type: string, handler: (state: string) => void) => {
      appStateHandler = handler;
      return { remove: jest.fn() };
    }) as never);
  });

  it('clears an expired saved token only after /auth/me confirms 401 twice', async () => {
    (getToken as jest.Mock).mockResolvedValueOnce('tok_saved');
    (fetchCurrentUser as jest.Mock)
      .mockRejectedValueOnce({ response: { status: 401 } })
      .mockRejectedValueOnce({ response: { status: 401 } });

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );

    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('guest'));
    expect(fetchCurrentUser).toHaveBeenCalledTimes(2);
    expect(logout).toHaveBeenCalledTimes(1);
  });

  it('preserves a saved session when the first /auth/me 401 is transient', async () => {
    (getToken as jest.Mock).mockResolvedValueOnce('tok_saved');
    (fetchCurrentUser as jest.Mock)
      .mockRejectedValueOnce({ response: { status: 401 } })
      .mockResolvedValueOnce({ id: 3, username: 'q' });

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );

    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('auth+user'));
    expect(fetchCurrentUser).toHaveBeenCalledTimes(2);
    expect(logout).not.toHaveBeenCalled();
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

  it('revalidates and preserves the current session after an incidental business API 401', async () => {
    (getToken as jest.Mock).mockResolvedValueOnce('tok_saved');
    (fetchCurrentUser as jest.Mock)
      .mockResolvedValueOnce({ id: 3, username: 'q' })
      .mockResolvedValueOnce({ id: 3, username: 'q' });

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );

    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('auth+user'));
    act(() => {
      unauthorizedHandler?.();
    });

    await waitFor(() => expect(fetchCurrentUser).toHaveBeenCalledTimes(2));
    expect(screen.getByTestId('state')).toHaveTextContent('auth+user');
    expect(logout).not.toHaveBeenCalled();
  });

  it('keeps recovering a known persisted session when keychain reads are initially empty', async () => {
    mockHadPersistedSession = true;
    (getToken as jest.Mock)
      .mockResolvedValueOnce(null)
      .mockResolvedValueOnce(null)
      .mockResolvedValueOnce(null)
      .mockResolvedValueOnce('tok_recovered');
    (fetchCurrentUser as jest.Mock).mockResolvedValueOnce({ id: 3, username: 'q' });

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );

    await waitFor(
      () => expect(screen.getByTestId('state')).toHaveTextContent('auth+user'),
      { timeout: 5000 },
    );
    expect(logout).not.toHaveBeenCalled();
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

    fireEvent.press(screen.getByTestId('logout'));
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
