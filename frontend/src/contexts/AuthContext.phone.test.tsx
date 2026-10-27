import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
const { consentUser, fetchMock } = vi.hoisted(() => ({ consentUser: vi.fn(), fetchMock: vi.fn() }));
vi.mock('@/services/api/client', () => ({ API_BASE_URL: '/api', WEB_SESSION_TOKEN: '__web_cookie_session__' }));
vi.mock('@/services/aiConsent', () => ({ setAiConsentUser: consentUser }));
import { AuthProvider, useAuth } from './AuthContext';

const user = { id: 42, name: 'Synthetic User', is_active: true, is_approved: true };
const response = (data: unknown, status = 200) => ({ ok: status < 400, status, headers: new Headers({ 'content-type': 'application/json' }), json: async () => data });
function Probe() {
  const auth = useAuth();
  const [error, setError] = React.useState('');
  return <><span>{auth.isAuthenticated ? auth.user?.name : 'signed out'}</span><button onClick={async () => { const r = await auth.verifyPhoneCode('+8613800138000', '123456'); setError(r.error || ''); }}>verify</button><button onClick={auth.logout}>logout</button><p role="alert">{error}</p></>;
}
beforeEach(() => { vi.clearAllMocks(); vi.stubGlobal('fetch', fetchMock); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('phone cookie authentication', () => {
  it('requests HttpOnly transport and verifies the cookie identity before authenticating', async () => {
    fetchMock.mockResolvedValueOnce(response({}, 401)).mockResolvedValueOnce(response({ outcome: 'authenticated', user, access_token: '__web_cookie_session__' })).mockResolvedValueOnce(response(user));
    const storage = vi.spyOn(Storage.prototype, 'setItem');
    render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByText('verify'));
    expect(await screen.findByText(user.name)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/auth/phone/verify', expect.objectContaining({ credentials: 'include', headers: expect.objectContaining({ 'X-Auth-Transport': 'web-cookie' }) }));
    expect(fetchMock).toHaveBeenNthCalledWith(3, '/api/auth/me', { credentials: 'include' });
    expect(storage).not.toHaveBeenCalled();
    expect(consentUser).toHaveBeenCalledWith(42);
    storage.mockRestore();
  });
  it('rejects an unknown outcome and does not establish a local session', async () => {
    fetchMock.mockResolvedValueOnce(response({}, 401)).mockResolvedValueOnce(response({ outcome: 'unexpected', user }));
    render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByText('verify'));
    expect(await screen.findByRole('alert')).toHaveTextContent('无法识别');
    expect(screen.getByText('signed out')).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
  it('does not claim success when the issued cookie cannot restore the verified identity', async () => {
    fetchMock.mockResolvedValueOnce(response({}, 401)).mockResolvedValueOnce(response({ outcome: 'authenticated', user })).mockResolvedValueOnce(response({}, 401));
    render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByText('verify'));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(screen.getByText('signed out')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('登录状态');
  });
  it('does not restore a session from a verification that finishes after logout', async () => {
    let finishVerification!: (value: unknown) => void;
    fetchMock.mockResolvedValueOnce(response({}, 401)).mockReturnValueOnce(new Promise(resolve => { finishVerification = resolve; })).mockResolvedValueOnce(response({})).mockResolvedValueOnce(response(user));
    render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByText('verify'));
    fireEvent.click(screen.getByText('logout'));
    finishVerification(response({ outcome: 'authenticated', user }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('登录状态已变化'));
    expect(screen.getByText('signed out')).toBeInTheDocument();
  });

});
