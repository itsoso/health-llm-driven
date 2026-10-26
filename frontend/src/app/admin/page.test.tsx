// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '@/services/api/client';
import AdminPage from './page';

const mocks = vi.hoisted(() => ({ push: vi.fn(), useAuth: vi.fn() }));

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: mocks.push }) }));
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => mocks.useAuth() }));
vi.mock('@/services/api/client', () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
  WEB_SESSION_TOKEN: '__web_cookie_session__',
}));

describe('AdminPage access gate', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.get).mockImplementation(async (path: string) => ({
      data: path === '/admin/stats'
        ? {
            total_users: 0,
            active_users: 0,
            admin_users: 0,
            users_with_garmin: 0,
            total_health_records: 0,
            total_medical_exams: 0,
            new_users_today: 0,
            new_users_week: 0,
          }
        : path === '/admin/decisions'
          ? { enabled: false, revision: 0, effective_mode: 'off', configured: true, provider: 'laya', updated_at: '2026-09-24T00:00:00Z' }
          : { users: [], total: 0, page: 1, page_size: 15 },
    }));
  });

  it('redirects an authenticated non-admin without rendering registration invitations', async () => {
    mocks.useAuth.mockReturnValue({
      user: { id: 41, is_admin: false },
      isAuthenticated: true,
      isLoading: false,
    });
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(<QueryClientProvider client={queryClient}><AdminPage /></QueryClientProvider>);

    expect(screen.getByText('验证权限中...')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '手机号注册邀请' })).not.toBeInTheDocument();
    await waitFor(() => expect(mocks.push).toHaveBeenCalledWith('/'));
  });

  it('links administrators to the independent System Map path', () => {
    mocks.useAuth.mockReturnValue({
      user: { id: 1, is_admin: true },
      isAuthenticated: true,
      isLoading: false,
    });
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(<QueryClientProvider client={queryClient}><AdminPage /></QueryClientProvider>);
    fireEvent.click(screen.getByRole('button', { name: /系统地图/ }));

    expect(mocks.push).toHaveBeenCalledWith('/admin/system-map');
    expect(screen.queryByRole('heading', { name: '意图决策服务' })).not.toBeInTheDocument();
  });

  it('shows decision control only to administrator three', () => {
    mocks.useAuth.mockReturnValue({ user: { id: 3, is_admin: true }, isAuthenticated: true, isLoading: false });
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={queryClient}><AdminPage /></QueryClientProvider>);
    expect(screen.getByRole('heading', { name: '意图决策服务' })).toBeInTheDocument();
  });
  it('offers direct registration and admin creation without an invitation navigation entry', () => {
    mocks.useAuth.mockReturnValue({ user: { id: 1, is_admin: true }, isAuthenticated: true, isLoading: false });
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={queryClient}><AdminPage /></QueryClientProvider>);
    expect(screen.queryByRole('button', { name: /邀请码管理/ })).not.toBeInTheDocument();
    expect(screen.getByText('用户可用手机号验证码直接注册；管理员也可直接创建账号。')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '+ 创建用户' }));
    expect(screen.getByPlaceholderText('初始密码')).toHaveAttribute('type', 'password');
  });

  it('shows structured creation errors as a readable message', async () => {
    mocks.useAuth.mockReturnValue({ user: { id: 1, is_admin: true }, isAuthenticated: true, isLoading: false });
    vi.mocked(api.post).mockRejectedValue({ response: { data: { detail: { code: 'INPUT_INVALID', message: '邮箱已存在' } } } });
    const alert = vi.spyOn(window, 'alert').mockImplementation(() => {});
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    render(<QueryClientProvider client={queryClient}><AdminPage /></QueryClientProvider>);
    fireEvent.click(screen.getByRole('button', { name: '+ 创建用户' }));
    fireEvent.change(screen.getByPlaceholderText('用户名（登录用）'), { target: { value: 'synthetic' } });
    fireEvent.change(screen.getByPlaceholderText('邮箱地址'), { target: { value: 'synthetic@example.com' } });
    fireEvent.change(screen.getByPlaceholderText('显示名称'), { target: { value: 'Synthetic' } });
    fireEvent.change(screen.getByPlaceholderText('初始密码'), { target: { value: 'synthetic-password' } });
    fireEvent.click(screen.getByRole('button', { name: '确认创建' }));
    await waitFor(() => expect(alert).toHaveBeenCalledWith('❌ 邮箱已存在'));
    alert.mockRestore();
  });

});
