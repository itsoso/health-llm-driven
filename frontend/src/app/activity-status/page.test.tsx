import { cleanup, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { api } from '@/services/api/client';
import ActivityPage from './page';
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => ({ user: { id: 7 } }) }));
vi.mock('@/components/ProtectedRoute', () => ({ default: ({ children }: { children: React.ReactNode }) => children }));
let client: QueryClient;
beforeEach(() => { client = new QueryClient({ defaultOptions: { queries: { retry: false } } }); });
afterEach(() => { cleanup(); client.clear(); vi.restoreAllMocks(); });
const show = () => render(<QueryClientProvider client={client}><ActivityPage /></QueryClientProvider>);
it('reads current and historical records independently using user-scoped queries', async () => {
  vi.spyOn(api, 'get').mockImplementation(async url => ({ data: url.endsWith('current') ? null : [{ id: 1, status_text: 'Synthetic activity', category: 'working', start_time: '2026-10-09T09:00:00Z', is_active: false }] }));
  show();
  expect(await screen.findByText('暂无进行中的活动记录')).toBeTruthy();
  expect(await screen.findByText('Synthetic activity')).toBeTruthy();
  expect(client.getQueryData(['activity-status', 'history', 7])).toBeTruthy();
});
it('reports a retrieval error instead of an empty activity history', async () => {
  vi.spyOn(api, 'get').mockRejectedValue(new Error('offline')); show();
  expect(await screen.findAllByRole('alert')).toHaveLength(2);
  expect(screen.queryByText('暂无活动记录')).toBeNull();
});
