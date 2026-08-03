// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import AdminPage from './page';

const mocks = vi.hoisted(() => ({ push: vi.fn(), useAuth: vi.fn() }));

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: mocks.push }) }));
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => mocks.useAuth() }));

describe('AdminPage access gate', () => {
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
});
