import React from 'react';
import { act, renderHook, waitFor } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

let mockAuth = { user: { id: 7 }, token: 'synthetic-a', isLoading: false };
jest.mock('../useAuth', () => ({ useAuth: () => mockAuth }));
jest.mock('../../services/api', () => ({ __esModule: true, default: { get: jest.fn() } }));
import api from '../../services/api';
import { setAIConsentIdentity } from '../../services/aiConsentState';
import { useDailyDiet, useDietStats, useFrequentDietFoods } from '../useDiet';

const date = '2026-10-11';
const summary = (owner: number) => ({ record_date: date, total_calories: owner, meals: [{ id: 1, user_id: owner }] });
const get = api.get as jest.Mock;

describe('diet query account isolation', () => {
  let client: QueryClient;
  let wrapper: React.ComponentType<{ children: React.ReactNode }>;
  beforeEach(() => {
    mockAuth = { user: { id: 7 }, token: 'synthetic-a', isLoading: false };
    setAIConsentIdentity(null); setAIConsentIdentity(mockAuth.token);
    get.mockReset();
    client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
    wrapper = ({ children }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  });
  afterEach(() => client.clear());

  it('ignores legacy persisted unscoped data and immediately hides A when B opens the same date', async () => {
    client.setQueryData(['diet', date], summary(99));
    get.mockResolvedValueOnce({ data: summary(7) });
    const { result, rerender } = renderHook(() => useDailyDiet(date), { wrapper });
    expect(result.current.data).toBeUndefined();
    await waitFor(() => expect(result.current.data?.meals[0].user_id).toBe(7));
    let resolveB!: (value: unknown) => void;
    get.mockReturnValueOnce(new Promise(resolve => { resolveB = resolve; }));
    act(() => { mockAuth = { user: { id: 8 }, token: 'synthetic-b', isLoading: false }; setAIConsentIdentity(mockAuth.token); });
    rerender({});
    expect(result.current.data).toBeUndefined();
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    await act(async () => resolveB({ data: summary(8) }));
    await waitFor(() => expect(result.current.data?.meals[0].user_id).toBe(8));
    expect(get.mock.calls[1][1].headers['X-Reva-AI-Subject']).toBe('8');
    expect(client.getQueryCache().getAll().filter(q => q.queryKey.length > 2).every(q => q.meta?.persist === false)).toBe(true);
  });

  it('rejects late A responses after account switch instead of caching them as successful data', async () => {
    let resolveA!: (value: unknown) => void;
    get.mockReturnValueOnce(new Promise(resolve => { resolveA = resolve; }));
    const { result, rerender } = renderHook(() => useDailyDiet(date), { wrapper });
    await waitFor(() => expect(get).toHaveBeenCalledTimes(1));
    get.mockResolvedValueOnce({ data: summary(8) });
    act(() => { mockAuth = { user: { id: 8 }, token: 'synthetic-b', isLoading: false }; setAIConsentIdentity(mockAuth.token); });
    rerender({});
    await waitFor(() => expect(result.current.data?.meals[0].user_id).toBe(8));
    await act(async () => resolveA({ data: summary(7) }));
    expect(result.current.data?.meals[0].user_id).toBe(8);
    expect(client.getQueryCache().getAll().some(q => (q.state.data as any)?.meals?.[0]?.user_id === 7)).toBe(false);
  });

  it('hides diet stats on logout and refuses manual refetch without an authenticated session', async () => {
    get.mockResolvedValueOnce({ data: { total_records: 7 } });
    const { result, rerender } = renderHook(() => useDietStats(), { wrapper });
    await waitFor(() => expect(result.current.data?.total_records).toBe(7));
    act(() => { mockAuth = { user: null, token: null, isLoading: false } as any; setAIConsentIdentity(null); });
    rerender({});
    expect(result.current.data).toBeUndefined();
    await act(async () => { await result.current.refetch(); });
    expect(get).toHaveBeenCalledTimes(1);
  });

  it('rejects a mismatched record owner returned by the service', async () => {
    get.mockResolvedValueOnce({ data: summary(8) });
    const { result } = renderHook(() => useDailyDiet(date), { wrapper });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.data).toBeUndefined();
  });

  it('does not reuse frequent foods from the previous account or legacy persisted cache', async () => {
    client.setQueryData(['diet', 'frequent'], [{ food_items: 'legacy synthetic' }]);
    get.mockResolvedValueOnce({ data: [{ food_items: 'synthetic A' }] });
    const { result, rerender } = renderHook(() => useFrequentDietFoods(), { wrapper });
    expect(result.current.data).toBeUndefined();
    await waitFor(() => expect(result.current.data?.[0].food_items).toBe('synthetic A'));
    get.mockResolvedValueOnce({ data: [{ food_items: 'synthetic B' }] });
    act(() => { mockAuth = { user: { id: 8 }, token: 'synthetic-b', isLoading: false }; setAIConsentIdentity(mockAuth.token); });
    rerender({});
    expect(result.current.data).toBeUndefined();
    await waitFor(() => expect(result.current.data?.[0].food_items).toBe('synthetic B'));
  });

  it('refetches for a new login session of the same account rather than using old fresh data', async () => {
    get.mockResolvedValueOnce({ data: summary(7) });
    const { result, rerender } = renderHook(() => useDailyDiet(date), { wrapper });
    await waitFor(() => expect(result.current.data).toBeDefined());
    get.mockResolvedValueOnce({ data: { ...summary(7), total_calories: 70 } });
    act(() => { mockAuth = { user: { id: 7 }, token: 'synthetic-a-new-session', isLoading: false }; setAIConsentIdentity(mockAuth.token); });
    rerender({});
    expect(result.current.data).toBeUndefined();
    await waitFor(() => expect(result.current.data?.total_calories).toBe(70));
    expect(get).toHaveBeenCalledTimes(2);
  });
});
