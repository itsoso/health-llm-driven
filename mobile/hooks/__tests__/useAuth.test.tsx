/* eslint-disable import/first */
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
  loginByPhoneCode: jest.fn(),
  verifyPhoneCode: jest.fn(),
  completeInvitedRegistration: jest.fn(),
  logout: jest.fn(),
  getToken: jest.fn(),
  fetchCurrentUser: jest.fn(),
  loadPendingRegistration: jest.fn(),
  loadPendingRegistrationForHydration: jest.fn(),
  isAuthOperationSuperseded: (error: unknown) => (
    (error as { name?: string } | null)?.name === 'AuthOperationSuperseded'
  ),
  authLogoutErrorCode: (error: unknown) => (
    (error as { code?: string } | null)?.code ?? null
  ),
  registrationAuthErrorCode: (error: unknown) => (
    (error as { code?: string } | null)?.code ?? null
  ),
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
import {
  completeInvitedRegistration,
  fetchCurrentUser,
  getToken,
  login,
  loadPendingRegistration,
  loadPendingRegistrationForHydration,
  logout,
  verifyPhoneCode,
} from '../../services/auth';

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
      <Text testID="username">{auth.user?.username ?? 'no-user'}</Text>
      <Text testID="logout" onPress={() => void auth.logout().catch(() => {})}>logout</Text>
      <Text testID="retry" onPress={() => void auth.retrySession().catch(() => {})}>retry</Text>
      <Text testID="login" onPress={() => void auth.login('alice', 'hunter2').catch(() => {})}>login</Text>
      <Text testID="verify" onPress={() => void auth.verifyPhoneCode('13800138000', '123456').catch(() => {})}>verify</Text>
      <Text testID="verify-2" onPress={() => void auth.verifyPhoneCode('13900139000', '654321').catch(() => {})}>verify-2</Text>
      <Text testID="complete" onPress={() => void auth.completeInvitedRegistration({ manualCode: 'ABCD2345' }).catch(() => {})}>complete</Text>
      <Text testID="pending">{auth.pendingRegistration ? 'pending' : 'no-pending'}</Text>
      <Text testID="pending-metadata">{JSON.stringify(auth.pendingRegistration)}</Text>
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
    (loadPendingRegistration as jest.Mock).mockResolvedValue(null);
    (loadPendingRegistrationForHydration as jest.Mock).mockImplementation(
      (...args: unknown[]) => (loadPendingRegistration as jest.Mock)(...args),
    );
    jest.spyOn(AppState, 'addEventListener').mockImplementation(((_type: string, handler: (state: string) => void) => {
      appStateHandler = handler;
      return { remove: jest.fn() };
    }) as never);
  });

  function makeSupersededError(): Error {
    const error = new Error('auth operation superseded');
    error.name = 'AuthOperationSuperseded';
    return error;
  }

  function makeDeferred<T>() {
    let resolve!: (value: T) => void;
    let reject!: (reason?: unknown) => void;
    const promise = new Promise<T>((done, fail) => {
      resolve = done;
      reject = fail;
    });
    return { promise, resolve, reject };
  }

  async function waitForUnauthorizedConfirmation(): Promise<void> {
    await new Promise((resolve) => setTimeout(resolve, 450));
  }

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

  it('cancels hydration on unmount without logging out the durable session', async () => {
    type GuardOptions = { isCurrent?: () => boolean };
    const hydrationGate = makeDeferred<string>();
    (getToken as jest.Mock).mockImplementation(async (options?: GuardOptions) => {
      const token = await hydrationGate.promise;
      if (!options?.isCurrent?.()) throw makeSupersededError();
      return token;
    });

    const view = render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(getToken).toHaveBeenCalledTimes(1));
    const guard = (getToken as jest.Mock).mock.calls[0][0]?.isCurrent;
    expect(guard).toEqual(expect.any(Function));
    view.unmount();
    expect(guard()).toBe(false);
    await act(async () => {
      hydrationGate.resolve('tok_existing');
    });

    expect(logout).not.toHaveBeenCalled();
  });

  it('does not clear durable auth when initial /auth/me returns 401 after unmount', async () => {
    const currentUserGate = makeDeferred<{ id: number; username: string }>();
    (getToken as jest.Mock).mockResolvedValueOnce('tok_existing');
    (fetchCurrentUser as jest.Mock).mockReturnValueOnce(currentUserGate.promise);

    const view = render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(fetchCurrentUser).toHaveBeenCalledTimes(1));
    view.unmount();
    await act(async () => {
      currentUserGate.reject({ response: { status: 401 } });
      await waitForUnauthorizedConfirmation();
    });

    expect(fetchCurrentUser).toHaveBeenCalledTimes(1);
    expect(logout).not.toHaveBeenCalled();
  });

  it('does not clear durable auth when retry /auth/me returns 401 after unmount', async () => {
    const currentUserGate = makeDeferred<{ id: number; username: string }>();
    (getToken as jest.Mock).mockResolvedValueOnce('tok_existing');
    (fetchCurrentUser as jest.Mock).mockReturnValueOnce(currentUserGate.promise);

    const view = render(
      <AuthProvider restoreCloudSession={false}>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('guest'));
    fireEvent.press(screen.getByTestId('retry'));
    await waitFor(() => expect(fetchCurrentUser).toHaveBeenCalledTimes(1));
    view.unmount();
    await act(async () => {
      currentUserGate.reject({ response: { status: 401 } });
      await waitForUnauthorizedConfirmation();
    });

    expect(fetchCurrentUser).toHaveBeenCalledTimes(1);
    expect(logout).not.toHaveBeenCalled();
  });

  it('stops an old hydration 401 after a newer login supersedes its epoch', async () => {
    const currentUserGate = makeDeferred<{ id: number; username: string }>();
    (getToken as jest.Mock).mockResolvedValueOnce('tok_existing');
    (fetchCurrentUser as jest.Mock).mockReturnValueOnce(currentUserGate.promise);
    (login as jest.Mock).mockResolvedValue({
      access_token: 'tok_new_login',
      token_type: 'bearer',
      user: { id: 7, username: 'alice' },
    });

    render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(fetchCurrentUser).toHaveBeenCalledTimes(1));
    fireEvent.press(screen.getByTestId('login'));
    await waitFor(() => expect(login).toHaveBeenCalledTimes(1));
    await act(async () => {
      currentUserGate.reject({ response: { status: 401 } });
      await waitForUnauthorizedConfirmation();
    });

    expect(fetchCurrentUser).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('auth+user'));
    expect(logout).not.toHaveBeenCalled();
  });

  it('restores an unexpired pending registration during first-load hydration', async () => {
    (getToken as jest.Mock).mockResolvedValue(null);
    (loadPendingRegistration as jest.Mock).mockResolvedValue({
      version: 1,
      verifiedPhoneTicket: 'T'.repeat(32),
      expiresAt: Date.now() + 300_000,
      idempotencyKey: 'registration-1234567890abcdef',
    });

    render(<AuthProvider><Probe /></AuthProvider>);

    expect(screen.getByTestId('state')).toHaveTextContent('loading');
    await waitFor(() => expect(screen.getByTestId('pending')).toHaveTextContent('pending'));
    expect(screen.getByTestId('state')).toHaveTextContent('guest');
    expect(screen.getByTestId('pending-metadata')).not.toHaveTextContent('verifiedPhoneTicket');
    expect(screen.getByTestId('pending-metadata')).not.toHaveTextContent('idempotencyKey');
  });

  it('does not restore raw pending credentials when logout tombstone hydration blocks them', async () => {
    (getToken as jest.Mock).mockResolvedValue(null);
    (loadPendingRegistrationForHydration as jest.Mock).mockResolvedValueOnce(null);
    (loadPendingRegistration as jest.Mock).mockResolvedValue({
      version: 1,
      verifiedPhoneTicket: 'T'.repeat(32),
      expiresAt: Date.now() + 300_000,
      idempotencyKey: 'registration-residue-12345678',
    });

    render(<AuthProvider><Probe /></AuthProvider>);

    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('guest'));
    expect(screen.getByTestId('pending')).toHaveTextContent('no-pending');
    expect(loadPendingRegistrationForHydration).toHaveBeenCalledTimes(1);
    expect(loadPendingRegistration).not.toHaveBeenCalled();
  });

  it('does not authenticate when verification requires an invitation', async () => {
    const pending = {
      version: 1 as const,
      verifiedPhoneTicket: 'T'.repeat(32),
      expiresAt: Date.now() + 300_000,
      idempotencyKey: 'registration-1234567890abcdef',
    };
    (getToken as jest.Mock).mockResolvedValue(null);
    (verifyPhoneCode as jest.Mock).mockResolvedValue({
      outcome: 'invitation_required',
      verified_phone_ticket: 'T'.repeat(32),
      expires_in_seconds: 300,
    });
    (loadPendingRegistration as jest.Mock)
      .mockResolvedValueOnce(null)
      .mockResolvedValueOnce(pending);

    render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('guest'));
    fireEvent.press(screen.getByTestId('verify'));

    await waitFor(() => expect(screen.getByTestId('pending')).toHaveTextContent('pending'));
    expect(screen.getByTestId('state')).toHaveTextContent('guest');
  });

  it('authenticates only after the verify service returns a durably persisted token', async () => {
    (getToken as jest.Mock).mockResolvedValue(null);
    (verifyPhoneCode as jest.Mock).mockResolvedValue({
      outcome: 'authenticated',
      access_token: 'tok_verified',
      token_type: 'bearer',
      is_new_user: false,
      user: { id: 8, username: 'phone_8' },
    });

    render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('guest'));
    fireEvent.press(screen.getByTestId('verify'));

    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('auth+user'));
    expect(screen.getByTestId('pending')).toHaveTextContent('no-pending');
  });

  it('remains unauthenticated when secure pending persistence fails', async () => {
    (getToken as jest.Mock).mockResolvedValue(null);
    (verifyPhoneCode as jest.Mock).mockRejectedValue(
      new Error('待注册状态无法安全保存，请解锁设备后重试'),
    );

    render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('guest'));
    fireEvent.press(screen.getByTestId('verify'));

    await waitFor(() => expect(verifyPhoneCode).toHaveBeenCalled());
    expect(screen.getByTestId('state')).toHaveTextContent('guest');
    expect(screen.getByTestId('pending')).toHaveTextContent('no-pending');
  });

  it('moves from pending to authenticated only after invited registration completes', async () => {
    const pending = {
      version: 1 as const,
      verifiedPhoneTicket: 'T'.repeat(32),
      expiresAt: Date.now() + 300_000,
      idempotencyKey: 'registration-1234567890abcdef',
    };
    (getToken as jest.Mock).mockResolvedValue(null);
    (loadPendingRegistration as jest.Mock).mockResolvedValueOnce(pending);
    (completeInvitedRegistration as jest.Mock).mockResolvedValue({
      access_token: 'tok_invited',
      token_type: 'bearer',
      is_new_user: true,
      user: { id: 9, username: 'phone_9' },
    });

    render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId('pending')).toHaveTextContent('pending'));
    fireEvent.press(screen.getByTestId('complete'));

    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('auth+user'));
    expect(screen.getByTestId('pending')).toHaveTextContent('no-pending');
  });

  it('preserves pending state when invited registration fails so the code can be corrected', async () => {
    const pending = {
      version: 1 as const,
      verifiedPhoneTicket: 'T'.repeat(32),
      expiresAt: Date.now() + 300_000,
      idempotencyKey: 'registration-1234567890abcdef',
    };
    (getToken as jest.Mock).mockResolvedValue(null);
    (loadPendingRegistration as jest.Mock)
      .mockResolvedValueOnce(pending)
      .mockResolvedValueOnce(pending);
    (completeInvitedRegistration as jest.Mock).mockRejectedValue(new Error('INVITATION_INVALID'));

    render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId('pending')).toHaveTextContent('pending'));
    fireEvent.press(screen.getByTestId('complete'));

    await waitFor(() => expect(completeInvitedRegistration).toHaveBeenCalled());
    expect(screen.getByTestId('state')).toHaveTextContent('guest');
    expect(screen.getByTestId('pending')).toHaveTextContent('pending');
  });

  it('clears pending context immediately when completion reports a missing or expired ticket', async () => {
    const pending = {
      version: 1 as const,
      verifiedPhoneTicket: 'T'.repeat(32),
      expiresAt: Date.now() + 300_000,
      idempotencyKey: 'registration-1234567890abcdef',
    };
    (getToken as jest.Mock).mockResolvedValue(null);
    (loadPendingRegistration as jest.Mock).mockResolvedValueOnce(pending);
    (completeInvitedRegistration as jest.Mock).mockRejectedValue({
      name: 'RegistrationFlowError',
      code: 'VERIFIED_PHONE_TICKET_EXPIRED',
    });

    render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId('pending')).toHaveTextContent('pending'));
    fireEvent.press(screen.getByTestId('complete'));

    await waitFor(() => expect(screen.getByTestId('pending')).toHaveTextContent('no-pending'));
    expect(loadPendingRegistration).toHaveBeenCalledTimes(1);
  });

  it('clears pending context state on logout', async () => {
    (getToken as jest.Mock).mockResolvedValue(null);
    (loadPendingRegistration as jest.Mock).mockResolvedValue({
      version: 1,
      verifiedPhoneTicket: 'T'.repeat(32),
      expiresAt: Date.now() + 300_000,
      idempotencyKey: 'registration-1234567890abcdef',
    });
    (logout as jest.Mock).mockResolvedValue(undefined);

    render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId('pending')).toHaveTextContent('pending'));
    fireEvent.press(screen.getByTestId('logout'));

    await waitFor(() => expect(screen.getByTestId('pending')).toHaveTextContent('no-pending'));
  });

  it('keeps the authenticated UI when the durable logout barrier cannot be established', async () => {
    (getToken as jest.Mock).mockResolvedValue('tok_existing');
    (fetchCurrentUser as jest.Mock).mockResolvedValue({ id: 7, username: 'alice' });
    (logout as jest.Mock).mockRejectedValue({
      name: 'AuthLogoutError',
      code: 'LOGOUT_BARRIER_FAILED',
    });

    render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('auth+user'));
    fireEvent.press(screen.getByTestId('logout'));

    await waitFor(() => expect(logout).toHaveBeenCalledTimes(1));
    expect(screen.getByTestId('state')).toHaveTextContent('auth+user');
  });

  it('synchronously invalidates a delayed password login before awaiting a failing logout barrier', async () => {
    type GuardOptions = { isCurrent: () => boolean };
    const loginGate = makeDeferred<{
      access_token: string;
      token_type: string;
      user: { id: number; username: string };
    }>();
    const logoutGate = makeDeferred<void>();
    (getToken as jest.Mock).mockResolvedValue('tok_existing');
    (fetchCurrentUser as jest.Mock).mockResolvedValue({ id: 7, username: 'alice' });
    (login as jest.Mock)
      .mockImplementationOnce(async (
        _username: string,
        _password: string,
        options?: GuardOptions,
      ) => {
        const result = await loginGate.promise;
        if (!options?.isCurrent()) throw makeSupersededError();
        return result;
      })
      .mockResolvedValueOnce({
        access_token: 'tok_explicit_new',
        token_type: 'bearer',
        user: { id: 9, username: 'new-alice' },
      });
    (logout as jest.Mock).mockReturnValueOnce(logoutGate.promise);

    render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('auth+user'));
    fireEvent.press(screen.getByTestId('login'));
    await waitFor(() => expect(login).toHaveBeenCalledTimes(1));
    const oldGuard = (login as jest.Mock).mock.calls[0][2].isCurrent;

    fireEvent.press(screen.getByTestId('logout'));
    expect(oldGuard()).toBe(false);
    await act(async () => {
      loginGate.resolve({
        access_token: 'tok_stale_login',
        token_type: 'bearer',
        user: { id: 8, username: 'stale-alice' },
      });
      logoutGate.reject({ code: 'LOGOUT_BARRIER_FAILED' });
    });

    expect(screen.getByTestId('state')).toHaveTextContent('auth+user');
    fireEvent.press(screen.getByTestId('login'));
    await waitFor(() => expect(screen.getByTestId('username')).toHaveTextContent('new-alice'));
    expect(login).toHaveBeenCalledTimes(2);

    (logout as jest.Mock).mockResolvedValueOnce(undefined);
    fireEvent.press(screen.getByTestId('logout'));
    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('guest'));
  });

  it('synchronously invalidates delayed phone verification while a logout barrier is pending', async () => {
    type GuardOptions = { isCurrent: () => boolean };
    const verifyGate = makeDeferred<{
      outcome: 'invitation_required';
      verified_phone_ticket: string;
      expires_in_seconds: number;
    }>();
    const logoutGate = makeDeferred<void>();
    (getToken as jest.Mock).mockResolvedValue('tok_existing');
    (fetchCurrentUser as jest.Mock).mockResolvedValue({ id: 7, username: 'alice' });
    (verifyPhoneCode as jest.Mock).mockImplementationOnce(async (
      _phone: string,
      _code: string,
      options?: GuardOptions,
    ) => {
      const result = await verifyGate.promise;
      if (!options?.isCurrent()) throw makeSupersededError();
      return result;
    });
    (logout as jest.Mock).mockReturnValueOnce(logoutGate.promise);

    render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('auth+user'));
    fireEvent.press(screen.getByTestId('verify'));
    await waitFor(() => expect(verifyPhoneCode).toHaveBeenCalledTimes(1));
    const oldGuard = (verifyPhoneCode as jest.Mock).mock.calls[0][2].isCurrent;
    fireEvent.press(screen.getByTestId('logout'));

    expect(oldGuard()).toBe(false);
    await act(async () => {
      verifyGate.resolve({
        outcome: 'invitation_required',
        verified_phone_ticket: 'T'.repeat(32),
        expires_in_seconds: 300,
      });
      logoutGate.reject({ code: 'LOGOUT_BARRIER_FAILED' });
    });
    expect(screen.getByTestId('state')).toHaveTextContent('auth+user');
    expect(screen.getByTestId('pending')).toHaveTextContent('no-pending');
  });

  it('synchronously invalidates delayed invited completion without dropping pending UI on barrier failure', async () => {
    type GuardOptions = { isCurrent: () => boolean };
    const pending = {
      version: 1 as const,
      verifiedPhoneTicket: 'T'.repeat(32),
      expiresAt: Date.now() + 300_000,
      idempotencyKey: 'registration-1234567890abcdef',
    };
    const completionGate = makeDeferred<{
      access_token: string;
      token_type: string;
      is_new_user: boolean;
      user: { id: number; username: string };
    }>();
    const logoutGate = makeDeferred<void>();
    (getToken as jest.Mock).mockResolvedValue(null);
    (loadPendingRegistration as jest.Mock).mockResolvedValueOnce(pending);
    (completeInvitedRegistration as jest.Mock).mockImplementationOnce(async (
      _credential: unknown,
      options?: GuardOptions,
    ) => {
      const result = await completionGate.promise;
      if (!options?.isCurrent()) throw makeSupersededError();
      return result;
    });
    (logout as jest.Mock).mockReturnValueOnce(logoutGate.promise);

    render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId('pending')).toHaveTextContent('pending'));
    fireEvent.press(screen.getByTestId('complete'));
    await waitFor(() => expect(completeInvitedRegistration).toHaveBeenCalledTimes(1));
    const oldGuard = (completeInvitedRegistration as jest.Mock).mock.calls[0][1].isCurrent;
    fireEvent.press(screen.getByTestId('logout'));

    expect(oldGuard()).toBe(false);
    await act(async () => {
      completionGate.resolve({
        access_token: 'tok_stale_completion',
        token_type: 'bearer',
        is_new_user: true,
        user: { id: 10, username: 'stale-invite' },
      });
      logoutGate.reject({ code: 'LOGOUT_BARRIER_FAILED' });
    });
    expect(screen.getByTestId('state')).toHaveTextContent('guest');
    expect(screen.getByTestId('pending')).toHaveTextContent('pending');
  });

  it('clears authenticated UI when cleanup fails after the durable logout barrier', async () => {
    (getToken as jest.Mock).mockResolvedValue('tok_existing');
    (fetchCurrentUser as jest.Mock).mockResolvedValue({ id: 7, username: 'alice' });
    (logout as jest.Mock).mockRejectedValue({
      name: 'AuthLogoutError',
      code: 'LOGOUT_CLEANUP_INCOMPLETE',
    });

    render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('auth+user'));
    fireEvent.press(screen.getByTestId('logout'));

    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('guest'));
  });

  it('supersedes a delayed verify response when logout starts', async () => {
    type GuardOptions = { isCurrent: () => boolean };
    const gate = makeDeferred<{
      outcome: 'invitation_required';
      verified_phone_ticket: string;
      expires_in_seconds: number;
    }>();
    (getToken as jest.Mock).mockResolvedValue(null);
    (logout as jest.Mock).mockResolvedValue(undefined);
    (verifyPhoneCode as jest.Mock).mockImplementation(async (
      _phone: string,
      _code: string,
      options?: GuardOptions,
    ) => {
      const result = await gate.promise;
      if (!options?.isCurrent()) throw makeSupersededError();
      return result;
    });

    render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('guest'));
    fireEvent.press(screen.getByTestId('verify'));
    await waitFor(() => expect(verifyPhoneCode).toHaveBeenCalledTimes(1));
    expect((verifyPhoneCode as jest.Mock).mock.calls[0][2]?.isCurrent).toEqual(expect.any(Function));
    fireEvent.press(screen.getByTestId('logout'));
    await act(async () => {
      gate.resolve({
        outcome: 'invitation_required',
        verified_phone_ticket: 'T'.repeat(32),
        expires_in_seconds: 300,
      });
    });

    expect(screen.getByTestId('state')).toHaveTextContent('guest');
    expect(screen.getByTestId('pending')).toHaveTextContent('no-pending');
    expect(loadPendingRegistration).toHaveBeenCalledTimes(1);
  });

  it('supersedes a delayed completion when logout starts', async () => {
    type GuardOptions = { isCurrent: () => boolean };
    const pending = {
      version: 1 as const,
      verifiedPhoneTicket: 'T'.repeat(32),
      expiresAt: Date.now() + 300_000,
      idempotencyKey: 'registration-1234567890abcdef',
    };
    const gate = makeDeferred<{
      access_token: string;
      token_type: string;
      is_new_user: boolean;
      user: { id: number; username: string };
    }>();
    (getToken as jest.Mock).mockResolvedValue(null);
    (loadPendingRegistration as jest.Mock).mockResolvedValueOnce(pending);
    (logout as jest.Mock).mockResolvedValue(undefined);
    (completeInvitedRegistration as jest.Mock).mockImplementation(async (
      _credential: unknown,
      options?: GuardOptions,
    ) => {
      const result = await gate.promise;
      if (!options?.isCurrent()) throw makeSupersededError();
      return result;
    });

    render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId('pending')).toHaveTextContent('pending'));
    fireEvent.press(screen.getByTestId('complete'));
    await waitFor(() => expect(completeInvitedRegistration).toHaveBeenCalledTimes(1));
    expect((completeInvitedRegistration as jest.Mock).mock.calls[0][1]?.isCurrent)
      .toEqual(expect.any(Function));
    fireEvent.press(screen.getByTestId('logout'));
    await act(async () => {
      gate.resolve({
        access_token: 'tok_stale_complete',
        token_type: 'bearer',
        is_new_user: true,
        user: { id: 9, username: 'phone_9' },
      });
    });

    expect(screen.getByTestId('state')).toHaveTextContent('guest');
    expect(screen.getByTestId('pending')).toHaveTextContent('no-pending');
  });

  it('does not let an older verify response overwrite a newer successful login', async () => {
    type GuardOptions = { isCurrent: () => boolean };
    const gate = makeDeferred<{
      outcome: 'invitation_required';
      verified_phone_ticket: string;
      expires_in_seconds: number;
    }>();
    const pending = {
      version: 1 as const,
      verifiedPhoneTicket: 'T'.repeat(32),
      expiresAt: Date.now() + 300_000,
      idempotencyKey: 'registration-1234567890abcdef',
    };
    (getToken as jest.Mock).mockResolvedValue(null);
    (loadPendingRegistration as jest.Mock)
      .mockResolvedValueOnce(null)
      .mockResolvedValue(pending);
    (login as jest.Mock).mockResolvedValue({
      access_token: 'tok_new_login',
      token_type: 'bearer',
      user: { id: 7, username: 'alice' },
    });
    (verifyPhoneCode as jest.Mock).mockImplementation(async (
      _phone: string,
      _code: string,
      options?: GuardOptions,
    ) => {
      const result = await gate.promise;
      if (!options?.isCurrent()) throw makeSupersededError();
      return result;
    });

    render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('guest'));
    fireEvent.press(screen.getByTestId('verify'));
    await waitFor(() => expect(verifyPhoneCode).toHaveBeenCalledTimes(1));
    expect((verifyPhoneCode as jest.Mock).mock.calls[0][2]?.isCurrent)
      .toEqual(expect.any(Function));
    fireEvent.press(screen.getByTestId('login'));
    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('auth+user'));
    await act(async () => {
      gate.resolve({
        outcome: 'invitation_required',
        verified_phone_ticket: 'T'.repeat(32),
        expires_in_seconds: 300,
      });
    });

    expect(screen.getByTestId('state')).toHaveTextContent('auth+user');
    expect(screen.getByTestId('pending')).toHaveTextContent('no-pending');
  });

  it('applies only the latest of two out-of-order phone verifications', async () => {
    type GuardOptions = { isCurrent: () => boolean };
    type Outcome = {
      outcome: 'invitation_required';
      verified_phone_ticket: string;
      expires_in_seconds: number;
    } | {
      outcome: 'authenticated';
      access_token: string;
      token_type: string;
      is_new_user: false;
      user: { id: number; username: string };
    };
    const first = makeDeferred<Outcome>();
    const second = makeDeferred<Outcome>();
    (getToken as jest.Mock).mockResolvedValue(null);
    (verifyPhoneCode as jest.Mock).mockImplementation(async (
      phone: string,
      _code: string,
      options?: GuardOptions,
    ) => {
      const result = await (phone === '13800138000' ? first.promise : second.promise);
      if (!options?.isCurrent()) throw makeSupersededError();
      return result;
    });

    render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('guest'));
    fireEvent.press(screen.getByTestId('verify'));
    fireEvent.press(screen.getByTestId('verify-2'));
    await waitFor(() => expect(verifyPhoneCode).toHaveBeenCalledTimes(2));
    expect((verifyPhoneCode as jest.Mock).mock.calls[0][2]?.isCurrent)
      .toEqual(expect.any(Function));
    expect((verifyPhoneCode as jest.Mock).mock.calls[1][2]?.isCurrent)
      .toEqual(expect.any(Function));
    await act(async () => {
      second.resolve({
        outcome: 'authenticated',
        access_token: 'tok_latest',
        token_type: 'bearer',
        is_new_user: false,
        user: { id: 10, username: 'latest' },
      });
    });
    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('auth+user'));
    await act(async () => {
      first.resolve({
        outcome: 'invitation_required',
        verified_phone_ticket: 'T'.repeat(32),
        expires_in_seconds: 300,
      });
    });

    expect(screen.getByTestId('state')).toHaveTextContent('auth+user');
    expect(screen.getByTestId('pending')).toHaveTextContent('no-pending');
  });

  it('does not restore an old pending payload after a newer login completes', async () => {
    const pendingGate = makeDeferred<{
      version: 1;
      verifiedPhoneTicket: string;
      expiresAt: number;
      idempotencyKey: string;
    }>();
    (getToken as jest.Mock).mockResolvedValue(null);
    (loadPendingRegistration as jest.Mock).mockReturnValueOnce(pendingGate.promise);
    (login as jest.Mock).mockResolvedValue({
      access_token: 'tok_new_login',
      token_type: 'bearer',
      user: { id: 7, username: 'alice' },
    });

    render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(loadPendingRegistration).toHaveBeenCalledTimes(1));
    fireEvent.press(screen.getByTestId('login'));
    await waitFor(() => expect(login).toHaveBeenCalledTimes(1));
    await act(async () => {
      pendingGate.resolve({
        version: 1,
        verifiedPhoneTicket: 'T'.repeat(32),
        expiresAt: Date.now() + 300_000,
        idempotencyKey: 'registration-old-pending-1234',
      });
    });

    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('auth+user'));
    expect(screen.getByTestId('pending')).toHaveTextContent('no-pending');
  });

  it('does not restore an old pending payload after logout completes', async () => {
    const pendingGate = makeDeferred<{
      version: 1;
      verifiedPhoneTicket: string;
      expiresAt: number;
      idempotencyKey: string;
    }>();
    (getToken as jest.Mock).mockResolvedValue(null);
    (loadPendingRegistration as jest.Mock).mockReturnValueOnce(pendingGate.promise);
    (logout as jest.Mock).mockResolvedValue(undefined);

    render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(loadPendingRegistration).toHaveBeenCalledTimes(1));
    fireEvent.press(screen.getByTestId('logout'));
    await waitFor(() => expect(logout).toHaveBeenCalledTimes(1));
    await act(async () => {
      pendingGate.resolve({
        version: 1,
        verifiedPhoneTicket: 'T'.repeat(32),
        expiresAt: Date.now() + 300_000,
        idempotencyKey: 'registration-old-pending-1234',
      });
    });

    expect(screen.getByTestId('state')).toHaveTextContent('guest');
    expect(screen.getByTestId('pending')).toHaveTextContent('no-pending');
  });
});
