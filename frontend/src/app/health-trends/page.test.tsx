import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { healthTrendApi } from '@/services/api/health';
import TrendsPage from './page';
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => ({ user: { id: 7 } }) }));
vi.mock('@/components/ProtectedRoute', () => ({ default: ({ children }: { children: React.ReactNode }) => children }));
let client: QueryClient;
beforeEach(() => { client = new QueryClient({ defaultOptions: { queries: { retry: false } } }); });
afterEach(() => { cleanup(); client.clear(); vi.restoreAllMocks(); });
const show = () => render(<QueryClientProvider client={client}><TrendsPage /></QueryClientProvider>);
it('separates failed retrieval from no trend records', async () => {
  vi.spyOn(healthTrendApi, 'getLatest').mockRejectedValue(new Error('offline'));
  show();
  expect(await screen.findByRole('alert')).toBeTruthy();
  expect(screen.queryByText('暂无趋势数据')).toBeNull();
});
it('does not label an unknown trend as stable', async () => {
  vi.spyOn(healthTrendApi, 'getLatest').mockResolvedValue({ data: { dimensions: [{ dimension: 'sleep', trend_direction: null }] } } as any);
  show();
  expect(await screen.findByText(/暂无判断/)).toBeTruthy();
  expect(screen.queryByText('平稳')).toBeNull();
});
it('reports a detail failure with a retry instead of showing an empty report', async () => {
  vi.spyOn(healthTrendApi, 'getLatest').mockResolvedValue({ data: { dimensions: [{ dimension: 'sleep', trend_direction: 'improving' }] } } as any);
  vi.spyOn(healthTrendApi, 'getDimension').mockRejectedValue(new Error('offline'));
  show();
  fireEvent.click(await screen.findByRole('button', { name: /睡眠质量/ }));
  expect(await screen.findByRole('alert')).toBeTruthy();
  expect(screen.getByRole('button', { name: '重试详细报告' })).toBeTruthy();
});
