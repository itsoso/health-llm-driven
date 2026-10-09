import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import DailyInsightsPage from './page';

const mocks = vi.hoisted(() => ({
  userId: 7,
  fetch: vi.fn(),
  consent: vi.fn(),
}));
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => ({ user: { id: mocks.userId }, isAuthenticated: true, token: 'test' }) }));
vi.mock('@/components/ProtectedRoute', () => ({ default: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('@/services/aiConsent', () => ({ fetchWithAiSubject: mocks.fetch, requireAiConsent: mocks.consent }));
vi.mock('@/services/api/health', () => ({ dailyRecommendationApi: { getMyRecommendations: vi.fn(async () => ({ data: { one_day: { status: 'success' }, seven_day: { status: 'success' } } })) } }));
vi.mock('@/services/api/content', () => ({ externalRecommendationApi: { getMyToday: vi.fn(async () => ({ data: [] })), getMyRecommendationsPaginated: vi.fn() } }));
vi.mock('./components/MetricCards', () => ({ MetricCards: () => null }));
vi.mock('./components/AiInsightsSection', () => ({ AiInsightsSection: () => null }));
vi.mock('./components/EnvironmentSection', () => ({ EnvironmentSection: () => null }));
vi.mock('./components/HealthAnalysisGrid', () => ({ SmartRecommendations: () => null, DailyGoals: () => null, HealthAnalysisGrid: () => null }));

let client: QueryClient;
beforeEach(() => {
  mocks.userId = 7;
  mocks.fetch.mockReset();
  mocks.consent.mockReset().mockResolvedValue({ 'X-Reva-AI-Subject': '7' });
  client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
});
afterEach(() => { cleanup(); client.clear(); });
const ui = () => <QueryClientProvider client={client}><DailyInsightsPage /></QueryClientProvider>;

describe('daily analysis refresh', () => {
  it('discards a delayed response when the authenticated account changes', async () => {
    let resolve!: (value: Response) => void;
    mocks.fetch.mockReturnValue(new Promise<Response>((done) => { resolve = done; }));
    const view = render(ui());
    fireEvent.click(await screen.findByRole('button', { name: /刷新建议/ }));
    await waitFor(() => expect(mocks.fetch).toHaveBeenCalledOnce());
    expect(mocks.consent).toHaveBeenCalledWith('7');
    mocks.userId = 8;
    view.rerender(ui());
    await waitFor(() => expect(client.getQueryData(['daily-recommendations', 8])).toBeTruthy());
    const before = client.getQueryData(['daily-recommendations', 8]);
    await act(async () => resolve({ ok: true, json: async () => ({ one_day: { ai_insights: { health_summary: 'private account A' } } }) } as Response));
    await waitFor(() => expect(screen.queryByText('刷新中...')).toBeNull());
    expect(client.getQueryData(['daily-recommendations', 8])).toEqual(before);
    expect(screen.queryByText('✓ 建议已刷新')).toBeNull();
  });
  it('stores the returned result once and reports failed model analysis honestly', async () => {
    const result = { one_day: { status: 'success', llm_analysis: { available: false, provider: 'tokenplan' } }, seven_day: { status: 'no_data' } };
    mocks.fetch.mockResolvedValue({ ok: true, json: async () => result });
    render(ui());
    fireEvent.click(await screen.findByRole('button', { name: /刷新建议/ }));
    expect(await screen.findByText('Token Plan 分析暂不可用，请稍后重试')).toBeTruthy();
    expect(client.getQueryData(['daily-recommendations', 7])).toEqual({ data: result });
    expect(mocks.fetch).toHaveBeenCalledOnce();
  });
});
