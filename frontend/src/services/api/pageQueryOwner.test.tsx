import { cleanup, render } from '@testing-library/react';
import { QueryClient } from '@tanstack/react-query';
import { afterEach, expect, it, vi } from 'vitest';
import api from './client';
import { queryOwnerHeaders } from './queryOwner';
import { setAiConsentUser } from '@/services/aiConsent';
import Dashboard from '@/app/dashboard/page';
import DailyInsights from '@/app/daily-insights/page';
import Environment from '@/app/environment/page';
import Activity from '@/app/activity-status/page';
import Products from '@/app/supplement-products/page';
import Trends from '@/app/health-trends/page';

type QueuedQuery = { queryKey: readonly unknown[]; queryFn: () => Promise<unknown> };
const queued = vi.hoisted(() => [] as QueuedQuery[]);
vi.mock('@tanstack/react-query', async importOriginal => ({
  ...await importOriginal<typeof import('@tanstack/react-query')>(),
  useQuery: (options: QueuedQuery) => {
    queued.push(options);
    return { isLoading: true, data: options.queryKey[0] === 'effective-timezone' ? { timezone: 'Asia/Shanghai' } : undefined, refetch: vi.fn() };
  },
  useMutation: () => ({ mutate: vi.fn(), isPending: false }),
  useQueryClient: () => ({ invalidateQueries: vi.fn(), setQueryData: vi.fn() }),
}));
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => ({ user: { id: 101 }, isAuthenticated: true, token: '__web_cookie_session__' }) }));
vi.mock('@/components/ProtectedRoute', () => ({ default: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('recharts', () => Object.fromEntries(['LineChart', 'Line', 'BarChart', 'Bar', 'XAxis', 'YAxis', 'CartesianGrid', 'Tooltip', 'Legend', 'ResponsiveContainer'].map(name => [name, () => null])));
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }));

const originalAdapter = api.defaults.adapter;
afterEach(() => { cleanup(); queued.length = 0; api.defaults.adapter = originalAdapter; setAiConsentUser(null); vi.unstubAllGlobals(); });

it.each([
  ['dashboard', Dashboard, 11], ['daily-insights', DailyInsights, 3],
  ['environment', Environment, 2], ['activity-status', Activity, 2],
  ['supplement-products', Products, 1], ['health-trends', Trends, 2],
] as const)('%s binds queued A queries to A even when B signs in before dispatch', async (_name, Page, count) => {
  setAiConsentUser(101);
  render(<Page />);
  expect(queued).toHaveLength(count);
  // Auth cookie and the interceptor's current subject change after creation, before dispatch.
  setAiConsentUser(202);
  const subjects: string[] = [];
  api.defaults.adapter = async config => {
    const subject = String(config.headers.get('X-Reva-AI-Subject'));
    subjects.push(subject);
    if (subject !== '202') throw { response: { status: 409, data: { detail: { code: 'auth_session_changed' } } } };
    return { data: { owner: 202, weather: { owner: 202 }, timezone: 'Asia/Shanghai' }, status: 200, statusText: 'OK', headers: {}, config };
  };
  vi.stubGlobal('fetch', vi.fn(async (_url: string, init: RequestInit) => {
    const subject = new Headers(init.headers).get('X-Reva-AI-Subject')!;
    subjects.push(subject);
    return subject === '202'
      ? new Response(JSON.stringify({ owner: 202 }), { status: 200 })
      : new Response(JSON.stringify({ detail: { code: 'auth_session_changed' } }), { status: 409 });
  }));
  const cache = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  try {
    for (const options of queued) {
      // Today's external preview is currently a network-free empty stub; still isolate its cache.
      if (options.queryKey[0] === 'external-recommendations-today') {
        expect(options.queryKey).toContain(101);
        continue;
      }
      expect(options.queryKey).toContain(101);
      await expect(cache.fetchQuery(options)).rejects.toThrow('账号已变化');
      expect(cache.getQueryData(options.queryKey)).toBeUndefined();
    }
    expect(subjects.length).toBe(count - (_name === 'daily-insights' ? 1 : 0));
    expect(subjects.every(subject => subject === '101')).toBe(true);
  } finally { cache.clear(); }
});

it('allows the captured owner to read when the session still matches', async () => {
  setAiConsentUser(101);
  render(<Environment />);
  api.defaults.adapter = async config => {
    expect(config.headers.get('X-Reva-AI-Subject')).toBe('101');
    return { data: { weather: { owner: 101 } }, status: 200, statusText: 'OK', headers: {}, config };
  };
  const cache = new QueryClient();
  try {
    await cache.fetchQuery(queued[0]);
    expect(cache.getQueryData(queued[0].queryKey)).toEqual({ owner: 101 });
  } finally { cache.clear(); }
});

it.each([undefined, 0, -1, NaN, 1.5])('rejects an invalid query owner %s', owner => {
  expect(() => queryOwnerHeaders(owner)).toThrow('未发送');
});
