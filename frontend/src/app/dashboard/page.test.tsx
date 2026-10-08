import { act, cleanup, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import DashboardPage from './page';
import { api } from '@/services/api/client';

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => ({ user: { id: 77 }, isAuthenticated: true }) }));
vi.mock('@/components/ProtectedRoute', () => ({ default: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('recharts', () => ({
  ResponsiveContainer: () => null, LineChart: () => null, Line: () => null,
  BarChart: () => null, Bar: () => null, XAxis: () => null, YAxis: () => null,
  CartesianGrid: () => null, Tooltip: () => null, Legend: () => null,
}));

let client: QueryClient;
let accountTimezone: string;

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date('2026-10-01T06:27:00Z'));
  accountTimezone = 'Asia/Taipei';
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  vi.spyOn(api, 'get').mockImplementation(async (url, config) => {
    if (url === '/profile/me/effective-timezone') {
      if (!accountTimezone) throw new Error('Timezone unavailable');
      return { data: { timezone: accountTimezone, source: 'manual' } };
    }
    if (url === '/daily-health/garmin/me') {
      const recordDate = config?.params.start_date;
      return { data: [{ record_date: recordDate, sleep_score: recordDate === '2026-10-01' ? 91 : 90 }] };
    }
    return { data: null };
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
