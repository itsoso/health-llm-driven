// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { api } from '@/services/api/client';
import SystemMapPage from './page';


const mocks = vi.hoisted(() => ({ push: vi.fn(), useAuth: vi.fn() }));

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: mocks.push }) }));
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => mocks.useAuth() }));
vi.mock('@/services/api/client', () => ({ api: { get: vi.fn() } }));

const graph = {
  schema_version: '2.0' as const,
  counts: { api_routers: 2 },
  coverage: {
    api: { source: 'backend/app/api/main.py', status: 'partial' as const, limitations: 'dynamic routes' },
  },
  entities: [
    {
      id: 'component.backend',
      kind: 'component' as const,
      name: 'Backend',
      coverage: 'declaration' as const,
      source: { type: 'declaration' as const, path: 'docs/system-map/declarations.json' },
      owner: 'backend',
    },
    {
      id: 'resource.postgresql',
      kind: 'resource' as const,
      name: 'PostgreSQL',
      coverage: 'partial' as const,
      source: { type: 'declaration' as const, path: 'docs/system-map/declarations.json' },
      owner: 'platform',
    },
  ],
  relations: [
    {
      from: 'component.backend',
      type: 'writesTo',
      to: 'resource.postgresql',
      coverage: 'declaration' as const,
      source: { type: 'declaration' as const, path: 'docs/system-map/declarations.json' },
      flows: ['health-record'],
    },
  ],
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <SystemMapPage />
    </QueryClientProvider>,
  );
}

describe('SystemMapPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows only the auth loading state while identity is unresolved', () => {
    mocks.useAuth.mockReturnValue({ user: null, isAuthenticated: false, isLoading: true });

    renderPage();

    expect(screen.getByText('验证管理员权限中…')).toBeInTheDocument();
    expect(screen.queryByRole('img', { name: '系统实体关系图' })).not.toBeInTheDocument();
    expect(api.get).not.toHaveBeenCalled();
  });

  it('redirects anonymous users without calling the API', async () => {
    mocks.useAuth.mockReturnValue({ user: null, isAuthenticated: false, isLoading: false });

    renderPage();

    await waitFor(() => expect(mocks.push).toHaveBeenCalledWith('/login'));
    expect(api.get).not.toHaveBeenCalled();
  });

  it('redirects non-admin users without calling the API', async () => {
    mocks.useAuth.mockReturnValue({ user: { id: 8, is_admin: false }, isAuthenticated: true, isLoading: false });

    renderPage();

    await waitFor(() => expect(mocks.push).toHaveBeenCalledWith('/'));
    expect(api.get).not.toHaveBeenCalled();
  });

  it('loads one graph for an administrator and exposes all views and filters', async () => {
    mocks.useAuth.mockReturnValue({ user: { id: 1, is_admin: true }, isAuthenticated: true, isLoading: false });
    vi.mocked(api.get).mockResolvedValue({ data: graph });

    renderPage();

    expect(await screen.findByRole('heading', { name: 'System Map' })).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith('/admin/system-map');
    expect(screen.getByRole('tab', { name: '系统总览' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '依赖关系' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '业务流' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '地图质量' })).toBeInTheDocument();
    expect(screen.getByLabelText('实体类型')).toBeInTheDocument();
    expect(screen.getByLabelText('覆盖度')).toBeInTheDocument();
    expect(screen.getByLabelText('负责人')).toBeInTheDocument();
    expect(screen.getByText('Backend', { selector: 'title' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: '业务流' }));
    expect(screen.getByText('health-record')).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledTimes(1);
  });

  it('renders a retryable safe error', async () => {
    mocks.useAuth.mockReturnValue({ user: { id: 1, is_admin: true }, isAuthenticated: true, isLoading: false });
    vi.mocked(api.get).mockRejectedValueOnce(new Error('SQL SELECT secret'));

    renderPage();

    expect(await screen.findByRole('alert')).toHaveTextContent('系统地图暂时不可用');
    expect(screen.queryByText(/SQL SELECT secret/)).not.toBeInTheDocument();
    vi.mocked(api.get).mockResolvedValueOnce({ data: graph });
    fireEvent.click(screen.getByRole('button', { name: '重新加载系统地图' }));
    expect(await screen.findByText('Backend', { selector: 'title' })).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledTimes(2);
  });
});
