import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import DashboardPage from './page';
import { api } from '@/services/api/client';

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => ({ user: { id: 77 }, isAuthenticated: true }) }));
vi.mock('@/components/ProtectedRoute', () => ({ default: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('@/services/api/devices', () => ({ dataCollectionApi: { syncGarmin: vi.fn().mockResolvedValue({}) } }));
vi.mock('recharts', () => ({
  ResponsiveContainer: () => null, LineChart: () => null, Line: () => null,
  BarChart: () => null, Bar: () => null, XAxis: () => null, YAxis: () => null,
  CartesianGrid: () => null, Tooltip: () => null, Legend: () => null,
}));

let client: QueryClient;
let accountTimezone: string;
let hasGarmin: boolean;
let failedEndpoints: Set<string>;
let waterAmount: number;

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date('2026-10-01T06:27:00Z'));
  accountTimezone = 'Asia/Taipei';
  hasGarmin = true;
  failedEndpoints = new Set();
  waterAmount = 1234;
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  vi.spyOn(api, 'get').mockImplementation(async (url, config) => {
    if (failedEndpoints.has(url)) throw new Error('Request unavailable');
    if (url === '/profile/me/effective-timezone') {
      if (!accountTimezone) throw new Error('Timezone unavailable');
      return { data: { timezone: accountTimezone, source: 'manual' } };
    }
    if (url === '/daily-health/garmin/me') {
      if (!hasGarmin) return { data: [] };
      const recordDate = config?.params.start_date;
      return { data: [{ record_date: recordDate, sleep_score: recordDate === '2026-10-01' ? 91 : 90 }] };
    }
    if (url === '/water/records/me/date/2026-10-01') return { data: { total_amount: waterAmount, target_amount: 2000 } };
    if (url === '/diet/records/me/date/2026-10-01') return { data: { meals_count: 3, total_calories: 1567, meals: [] } };
    if (url === '/weight/records/me?limit=1') return { data: [{ weight: 72.5, record_date: '2026-09-29' }] };
    if (url === '/health-trends/latest') return { data: { report_date: null, dimensions: [] } };
    return { data: null };
  });
});

describe('dashboard completeness', () => {
  it('keeps manual records visible alongside Garmin data', async () => {
    await openDashboard();
    expect(await screen.findByText('今日饮水')).toBeInTheDocument();
    expect(screen.getByText('1234')).toBeInTheDocument();
    expect(screen.getByText('今日饮食')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('1567 kcal')).toBeInTheDocument();
    expect(screen.getByText('72.5')).toBeInTheDocument();
  });

  it('uses the real water endpoint and diet summary contract without Garmin', async () => {
    hasGarmin = false;
    await openDashboard();
    expect(await screen.findByText('1234')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('1567 kcal')).toBeInTheDocument();
  });

  it('shows failed reads instead of a fabricated zero or a disappearing trend section', async () => {
    failedEndpoints.add('/water/records/me/date/2026-10-01');
    failedEndpoints.add('/health-trends/latest');
    await openDashboard();
    expect(await screen.findByText('饮水数据加载失败')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '健康趋势' })).toBeInTheDocument();
    expect(screen.getByText('健康趋势加载失败，请重试')).toBeInTheDocument();
  });

  it('keeps an explicit empty report state and does not call an unknown trend stable', async () => {
    await openDashboard();
    expect(await screen.findByText('暂无趋势报告')).toBeInTheDocument();
    client.setQueryData(['health-trends-latest', 77], { data: { dimensions: [{ dimension: 'sleep', trend_direction: null, insights: [] }] } });
    expect(await screen.findByText('暂无判断')).toBeInTheDocument();
  });

  it('refreshes manual records and reports as well as Garmin', async () => {
    await openDashboard();
    await screen.findByText('1234');
    const before = vi.mocked(api.get).mock.calls.length;
    waterAmount = 1456;
    fireEvent.click(screen.getByRole('button', { name: /手动刷新/ }));
    expect(await screen.findByText('1456', {}, { timeout: 4000 })).toBeInTheDocument();
    const refreshed = vi.mocked(api.get).mock.calls.slice(before).map(([url]) => url);
    for (const endpoint of ['/water/records/me/date/2026-10-01', '/diet/records/me/date/2026-10-01', '/weight/records/me?limit=1', '/health-trends/latest', '/health-score/daily/me', '/data-health/status']) {
      expect(refreshed).toContain(endpoint);
    }
  });

  it('surfaces a failed refresh while retaining existing data', async () => {
    await openDashboard();
    await screen.findByText('1234');
    failedEndpoints.add('/water/records/me/date/2026-10-01');
    fireEvent.click(screen.getByRole('button', { name: /手动刷新/ }));
    await waitFor(() => expect(screen.getByText(/部分数据刷新失败/)).toBeInTheDocument(), { timeout: 4000 });
    expect(screen.getByText('1234')).toBeInTheDocument();
  });
});

afterEach(() => { cleanup(); client.clear(); vi.restoreAllMocks(); vi.useRealTimers(); });

async function openDashboard() {
  await act(async () => {
    render(<QueryClientProvider client={client}><DashboardPage /></QueryClientProvider>);
  });
}

describe('dashboard date and freshness', () => {
  it('selects the account calendar day rather than the browser day', async () => {
    await openDashboard();
    expect(await screen.findByText('91')).toBeInTheDocument();
    expect(screen.getByText(/记录日期: 2026-10-01.*Asia\/Taipei/)).toBeInTheDocument();
    expect(screen.getByText(/页面读取: 2026-10-01 14:27:00/)).toBeInTheDocument();
    expect(screen.queryByText(/最后更新:/)).not.toBeInTheDocument();
    expect(screen.getByText(/设备同步时间未提供/)).toBeInTheDocument();
  });

  it('honors an account west of UTC without a hardcoded China date', async () => {
    accountTimezone = 'America/Los_Angeles';
    await openDashboard();
    expect(await screen.findByText('90')).toBeInTheDocument();
    expect(screen.getByText(/记录日期: 2026-09-30.*America\/Los_Angeles/)).toBeInTheDocument();
  });

  it('shows timezone failure instead of silently selecting a browser date', async () => {
    accountTimezone = '';
    await openDashboard();
    expect(await screen.findByRole('alert')).toHaveTextContent('无法读取账户时区');
    expect(screen.queryByText('91')).not.toBeInTheDocument();
    expect(screen.queryByText('90')).not.toBeInTheDocument();
  });
});
