import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import HealthConnectionPage from './page';
import { metadata, dynamic, revalidate } from './layout';

const mocks = vi.hoisted(() => ({
  query: '',
  user: { id: 7, name: '测试账户' } as { id: number; name: string } | null,
  authLoading: false,
  replace: vi.fn(),
  fetch: vi.fn(),
  refreshUser: vi.fn(),
}));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: mocks.replace }),
  useSearchParams: () => new URLSearchParams(mocks.query),
}));
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ user: mocks.user, isLoading: mocks.authLoading, refreshUser: mocks.refreshUser }),
}));

const request = 'a'.repeat(43);
const consent = {
  client_name: '健康查询助手', scope: 'health:read', expires_in_days: 30,
  data_categories: ['sleep', 'diet', 'exercise'], user_id: 7,
};
const reply = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status }));

beforeEach(() => {
  mocks.query = `request=${request}`;
  mocks.user = { id: 7, name: '测试账户' };
  mocks.authLoading = false;
  mocks.replace.mockReset();
  mocks.refreshUser.mockReset().mockResolvedValue(undefined);
  mocks.fetch.mockReset().mockImplementation(() => reply(consent));
  vi.stubGlobal('fetch', mocks.fetch);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('first-party health consent', () => {
  it('shows the exact account and read-only consent without approving automatically', async () => {
    render(<HealthConnectionPage />);
    expect(await screen.findByRole('button', { name: '允许只读访问' })).toBeEnabled();
    expect(screen.getByText('测试账户')).toBeInTheDocument();
    expect(screen.getByText('账户 #7')).toBeInTheDocument();
    expect(screen.getByText('健康查询助手')).toBeInTheDocument();
    expect(screen.getByText(/睡眠、饮食和运动/)).toBeInTheDocument();
    expect(screen.getByText(/30 天/)).toBeInTheDocument();
    expect(mocks.fetch).toHaveBeenCalledTimes(1);
    expect(mocks.fetch).toHaveBeenCalledWith(`/api/v1/remote-health/consent?request=${request}`, expect.objectContaining({
      credentials: 'include', cache: 'no-store',
    }));
    expect(mocks.replace).not.toHaveBeenCalled();
    expect(document.body.textContent).not.toContain(request);
  });

  it.each([['允许只读访问', true], ['拒绝', false]])('submits only an explicit %s decision', async (label, approved) => {
    mocks.fetch.mockResolvedValueOnce(new Response(JSON.stringify(consent))).mockImplementation(() => reply({ redirect_uri: 'https://chatgpt.com/connector_platform_oauth_redirect?state=opaque' }));
    render(<HealthConnectionPage />);
    fireEvent.click(await screen.findByRole('button', { name: label as string }));
    await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith('https://chatgpt.com/connector_platform_oauth_redirect?state=opaque'));
    expect(mocks.fetch).toHaveBeenLastCalledWith('/api/v1/remote-health/consent', expect.objectContaining({
      method: 'POST', credentials: 'include', cache: 'no-store',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ request, expected_user_id: 7, approved }),
    }));
  });

  it('returns through the existing login with an internal path and no persistent storage', async () => {
    mocks.user = null;
    const localWrite = vi.spyOn(Storage.prototype, 'setItem');
    render(<HealthConnectionPage />);
    expect(await screen.findByRole('link', { name: '登录后继续' })).toHaveAttribute(
      'href', `/login?redirect=${encodeURIComponent(`/connect/health?request=${request}`)}`,
    );
    expect(mocks.fetch).not.toHaveBeenCalled();
    expect(localWrite).not.toHaveBeenCalled();
    localWrite.mockRestore();
  });

  it('rejects malformed or duplicate request parameters without making a request', async () => {
    mocks.query = 'request=invalid&request=duplicate';
    render(<HealthConnectionPage />);
    expect(await screen.findByRole('alert')).toHaveTextContent('连接请求无效');
    expect(mocks.fetch).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: '允许只读访问' })).not.toBeInTheDocument();
  });

  it('does not allow consent if the cookie and displayed accounts differ', async () => {
    mocks.fetch.mockImplementation(() => reply({ ...consent, user_id: 8 }));
    render(<HealthConnectionPage />);
    expect(await screen.findByRole('alert')).toHaveTextContent('登录账户已变化');
    expect(screen.queryByRole('button', { name: '允许只读访问' })).not.toBeInTheDocument();
  });

  it('clears the previous consent while a changed account is revalidated', async () => {
    const view = render(<HealthConnectionPage />);
    await screen.findByRole('button', { name: '允许只读访问' });
    mocks.user = { id: 8, name: '另一个账户' };
    mocks.fetch.mockImplementation(() => new Promise(() => {}));
    view.rerender(<HealthConnectionPage />);
    expect(screen.queryByRole('button', { name: '允许只读访问' })).not.toBeInTheDocument();
    expect(screen.queryByText('测试账户')).not.toBeInTheDocument();
  });

  it('shows a generic error and requires a fresh review after account-change rejection', async () => {
    mocks.fetch.mockResolvedValueOnce(new Response(JSON.stringify(consent))).mockImplementation(() => reply({ detail: 'SECRET_INTERNAL_VALUE' }, 409));
    render(<HealthConnectionPage />);
    fireEvent.click(await screen.findByRole('button', { name: '允许只读访问' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('登录账户已变化或连接请求已过期');
    expect(document.body.textContent).not.toContain('SECRET_INTERNAL_VALUE');
    expect(screen.queryByRole('button', { name: '允许只读访问' })).not.toBeInTheDocument();
    expect(mocks.replace).not.toHaveBeenCalled();
  });

  it('never executes a non-HTTPS callback returned by a failed boundary', async () => {
    mocks.fetch.mockResolvedValueOnce(new Response(JSON.stringify(consent))).mockImplementation(() => reply({ redirect_uri: 'javascript:alert(1)' }));
    render(<HealthConnectionPage />);
    fireEvent.click(await screen.findByRole('button', { name: '允许只读访问' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('未能完成连接');
    expect(mocks.replace).not.toHaveBeenCalled();
  });

  it('offers login when the first-party cookie expires', async () => {
    mocks.fetch.mockImplementation(() => reply({}, 401));
    render(<HealthConnectionPage />);
    expect(await screen.findByRole('link', { name: '登录后继续' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '允许只读访问' })).not.toBeInTheDocument();
    expect(mocks.refreshUser).toHaveBeenCalledTimes(1);
  });

  it('does not navigate a stale approval response after account change', async () => {
    let complete: (response: Response) => void = () => {};
    mocks.fetch.mockResolvedValueOnce(new Response(JSON.stringify(consent)))
      .mockImplementationOnce(() => new Promise<Response>(resolve => { complete = resolve; }))
      .mockImplementation(() => new Promise(() => {}));
    const view = render(<HealthConnectionPage />);
    fireEvent.click(await screen.findByRole('button', { name: '允许只读访问' }));
    mocks.user = { id: 8, name: '另一个账户' };
    view.rerender(<HealthConnectionPage />);
    complete(new Response(JSON.stringify({ redirect_uri: 'https://chatgpt.com/connector_platform_oauth_redirect?code=secret' })));
    await waitFor(() => expect(mocks.fetch).toHaveBeenCalledTimes(3));
    expect(mocks.replace).not.toHaveBeenCalled();
    expect(document.body.textContent).not.toContain('secret');
  });
});

describe('connection management', () => {
  it('lists grants and removes one only after a successful explicit revoke', async () => {
    mocks.query = '';
    const connection = { id: 'grant-1', client_name: '健康查询助手', scope: 'health:read', created_at: 1760000000, expires_at: 1762592000 };
    mocks.fetch.mockImplementationOnce(() => reply([connection])).mockImplementation(() => Promise.resolve(new Response(null, { status: 204 })));
    render(<HealthConnectionPage />);
    expect(await screen.findByText('健康查询助手')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '撤销 健康查询助手 的访问' }));
    expect(await screen.findByText('暂无已授权的连接')).toBeInTheDocument();
    expect(mocks.fetch).toHaveBeenLastCalledWith('/api/v1/remote-health/connections/grant-1', expect.objectContaining({ method: 'DELETE', credentials: 'include', cache: 'no-store' }));
  });

  it('preserves the connection on revoke failure and does not claim success', async () => {
    mocks.query = '';
    mocks.fetch.mockImplementationOnce(() => reply([{ id: 'grant-1', client_name: '健康查询助手', scope: 'health:read', created_at: 1760000000, expires_at: 1762592000 }])).mockImplementation(() => reply({}, 500));
    render(<HealthConnectionPage />);
    fireEvent.click(await screen.findByRole('button', { name: '撤销 健康查询助手 的访问' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('未能撤销');
    expect(screen.getByText('健康查询助手')).toBeInTheDocument();
  });

  it('disables indexing, referrers and server caching', () => {
    expect(metadata.robots).toEqual({ index: false, follow: false });
    expect(metadata.referrer).toBe('no-referrer');
    expect(dynamic).toBe('force-dynamic');
    expect(revalidate).toBe(0);
  });
});
