import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { healthAnalysisApi } from '@/services/api/health';
import AnalysisPage from './page';
const session = vi.hoisted(() => ({ id: 7 }));
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => ({ user: { id: session.id }, isAuthenticated: true }) }));
vi.mock('@/services/aiConsent', () => ({ requireAiConsent: vi.fn(async () => ({})) }));
vi.mock('@/components/ProtectedRoute', () => ({ default: ({ children }: { children: React.ReactNode }) => children }));
let client: QueryClient;
beforeEach(() => { session.id = 7; client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } }); });
afterEach(() => { cleanup(); client.clear(); vi.restoreAllMocks(); });
const ui = () => <QueryClientProvider client={client}><AnalysisPage /></QueryClientProvider>;
it('never claims no health problems after a failed request', async () => {
  vi.spyOn(healthAnalysisApi, 'analyzeMyIssues').mockRejectedValue(new Error('offline'));
  render(ui());
  expect(await screen.findByRole('alert')).toBeTruthy();
  expect(screen.queryByText('暂无健康问题')).toBeNull();
});
it('refresh calls the forced API exactly once and retains the user-scoped result', async () => {
  const read = vi.spyOn(healthAnalysisApi, 'analyzeMyIssues').mockResolvedValue({ data: { summary: 'synthetic report' } } as any);
  render(ui());
  await screen.findByText('synthetic report');
  fireEvent.click(screen.getByRole('button', { name: '重新分析' }));
  await waitFor(() => expect(read).toHaveBeenCalledWith(true, 7));
  await act(async () => {});
  expect(read.mock.calls.filter(call => call[0] === true)).toHaveLength(1);
  expect(read).toHaveBeenCalledTimes(2);
  expect(client.getQueryData(['health-analysis', 7])).toBeTruthy();
});
it('does not write a delayed forced analysis into the next account cache', async () => {
  let resolve!: (value: any) => void;
  vi.spyOn(healthAnalysisApi, 'analyzeMyIssues').mockImplementation(async force => force
    ? new Promise(done => { resolve = done; })
    : ({ data: { summary: 'initial report' } } as any));
  const view = render(ui());
  await screen.findByText('initial report');
  fireEvent.click(screen.getByRole('button', { name: '重新分析' }));
  await waitFor(() => expect(resolve).toBeTruthy());
  session.id = 8; view.rerender(ui());
  await waitFor(() => expect(client.getQueryData(['health-analysis', 8])).toBeTruthy());
  await act(async () => resolve({ data: { summary: 'account A private result' } }));
  expect(JSON.stringify(client.getQueryData(['health-analysis', 8]))).not.toContain('private');
});
it('an empty successful payload is not a claim of good health', async () => {
  vi.spyOn(healthAnalysisApi, 'analyzeMyIssues').mockResolvedValue({ data: {} } as any);
  render(ui());
  expect(await screen.findByText('暂无可用分析')).toBeTruthy();
  expect(screen.queryByText('暂无健康问题')).toBeNull();
});
