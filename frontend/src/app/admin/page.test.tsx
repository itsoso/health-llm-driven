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
  });
});
