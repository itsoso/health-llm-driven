import React from 'react';
import { Text } from 'react-native';
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
import { getToken, fetchCurrentUser } from '../../services/auth';

function Probe() {
  const auth = useAuth();
  return (
    <Text testID="state">
      {auth.isLoading ? 'loading' : auth.isAuthenticated ? 'auth' : 'guest'}
    </Text>
  );
}

describe('useAuth update resilience', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    unauthorizedHandler = null;
  });

  it('keeps the app authenticated when a saved token exists but user hydration gets a transient 401', async () => {
    (getToken as jest.Mock).mockResolvedValueOnce('tok_saved');
    (fetchCurrentUser as jest.Mock).mockRejectedValueOnce({ response: { status: 401 } });

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );

    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('auth'));
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

    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('auth'));
    expect(getToken).toHaveBeenCalledTimes(2);
  });

  it('does not force guest state from a global incidental 401 while a token is loaded', async () => {
    (getToken as jest.Mock).mockResolvedValueOnce('tok_saved');
    (fetchCurrentUser as jest.Mock).mockResolvedValueOnce({ id: 3, username: 'q' });

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );

    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('auth'));
    act(() => {
      unauthorizedHandler?.();
    });

    expect(screen.getByTestId('state')).toHaveTextContent('auth');
  });
});
