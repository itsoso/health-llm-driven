import React from 'react';
import { act, renderHook, waitFor } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useMyProgress } from '../useMyProgress';
import { fetchMyProgress } from '../../services/myProgress';
import { fetchHealthOperatingReview } from '../../services/healthOperatingReview';
import { aiConsentRevision, invalidateAIConsent, setAIConsentIdentity } from '../../services/aiConsentState';

let mockAuth: { user: { id: number } | null; token: string | null; isLoading: boolean };
let mockTransport: { generation: number; token: string | null; initialized: boolean };
const mockListeners = new Set<() => void>();
jest.mock('../useAuth', () => ({ useAuth: () => mockAuth }));
jest.mock('../../services/api', () => ({
  getAuthSessionSnapshot: () => mockTransport,
  subscribeAuthSessionChange: (callback: () => void) => {
    mockListeners.add(callback);
    return () => mockListeners.delete(callback);
  },
}));
jest.mock('../../services/myProgress', () => ({ fetchMyProgress: jest.fn() }));
jest.mock('../../services/healthOperatingReview', () => ({ fetchHealthOperatingReview: jest.fn() }));
const mockProgress = fetchMyProgress as jest.Mock;
const mockReview = fetchHealthOperatingReview as jest.Mock;
let client: QueryClient;
function wrapper({ children }: { children: React.ReactNode }) {
  return React.createElement(QueryClientProvider, { client }, children);
}

beforeEach(() => {
  mockAuth = { user: { id: 9 }, token: 'progress-test-credential', isLoading: false };
  mockTransport = { generation: 7, token: mockAuth.token, initialized: true };
  setAIConsentIdentity(null);
  setAIConsentIdentity(mockAuth.token);
  mockProgress.mockReset().mockResolvedValue({ marker: 'progress-owner-9' });
  mockReview.mockReset().mockResolvedValue({ marker: 'review-owner-9' });
  client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
});
afterEach(() => { client.clear(); });

it('binds both queries to owner, consent and transport generation without persisting tokens', async () => {
  const { result } = renderHook(() => useMyProgress(30), { wrapper });
  await waitFor(() => expect(result.current.progress.isSuccess && result.current.review.isSuccess).toBe(true));
  expect(result.current.canRead).toBe(true);
  const session = { owner: 9, revision: aiConsentRevision(), generation: 7 };
  expect(mockProgress).toHaveBeenCalledWith(30, session);
  expect(mockReview).toHaveBeenCalledWith(30, session);
  const queries = client.getQueryCache().getAll();
  expect(queries).toHaveLength(2);
  for (const query of queries) {
    expect(query.queryKey).toEqual([expect.any(String), 'owner', 9, session.revision, 7, 30]);
    expect(query.meta).toEqual({ persist: false });
    expect(query.gcTime).toBe(0);
    expect(JSON.stringify(query.queryKey)).not.toContain(mockAuth.token!);
  }
});

it.each(['logout', 'owner', 'token', 'consent', 'window'] as const)('immediately hides previous data on %s changes', async change => {
  const { result, rerender } = renderHook(({ days }: { days: 7 | 30 | 90 }) => useMyProgress(days), { wrapper, initialProps: { days: 30 } });
  await waitFor(() => expect(result.current.progress.isSuccess && result.current.review.isSuccess).toBe(true));
  mockProgress.mockImplementation(() => new Promise(() => {}));
  mockReview.mockImplementation(() => new Promise(() => {}));
  act(() => {
    if (change === 'logout') {
      mockAuth = { user: null, token: null, isLoading: false };
      mockTransport = { ...mockTransport, generation: 8, token: null };
      setAIConsentIdentity(null);
    } else if (change === 'owner') {
      mockAuth = { ...mockAuth, user: { id: 10 } };
    } else if (change === 'token') {
      mockTransport = { ...mockTransport, generation: 8, token: 'new-credential' };
      mockAuth = { ...mockAuth, token: 'new-credential' };
      mockListeners.forEach(callback => callback());
    } else if (change === 'consent') {
      invalidateAIConsent(true);
    }
    rerender({ days: change === 'window' ? 7 : 30 });
  });
  expect(result.current.progress.data).toBeUndefined();
  expect(result.current.review.data).toBeUndefined();
  if (change === 'logout') expect(result.current.canRead).toBe(false);
});

it('does not read while auth context and transport belong to different tokens', () => {
  mockTransport = { ...mockTransport, token: 'different-credential' };
  const { result } = renderHook(() => useMyProgress(30), { wrapper });
  expect(result.current.canRead).toBe(false);
  expect(mockProgress).not.toHaveBeenCalled();
  expect(mockReview).not.toHaveBeenCalled();
});

it.each(['generation', 'consent'] as const)('makes a stale refresh callback a no-op after %s changes', async change => {
  const { result } = renderHook(() => useMyProgress(30), { wrapper });
  await waitFor(() => expect(result.current.progress.isSuccess && result.current.review.isSuccess).toBe(true));
  const staleRefresh = result.current.refresh;
  const progressRefetch = jest.spyOn(result.current.progress, 'refetch');
  const reviewRefetch = jest.spyOn(result.current.review, 'refetch');
  await act(async () => {
    if (change === 'generation') {
      mockTransport = { ...mockTransport, generation: 8, token: 'new-credential' };
    } else {
      invalidateAIConsent(true);
    }
  });
  await waitFor(() => expect(result.current.progress.isSuccess && result.current.review.isSuccess).toBe(true));
  mockProgress.mockClear();
  mockReview.mockClear();
  await expect(staleRefresh()).resolves.toBeUndefined();
  expect(progressRefetch).not.toHaveBeenCalled();
  expect(reviewRefetch).not.toHaveBeenCalled();
  expect(mockProgress).not.toHaveBeenCalled();
  expect(mockReview).not.toHaveBeenCalled();
});

it('refreshes both queries and preserves a partial failure as an error', async () => {
  const { result } = renderHook(() => useMyProgress(30), { wrapper });
  await waitFor(() => expect(result.current.progress.isSuccess && result.current.review.isSuccess).toBe(true));
  let resolveProgress!: (value: unknown) => void;
  mockProgress.mockImplementation(() => new Promise(done => { resolveProgress = done; }));
  mockReview.mockRejectedValue(new Error('review unavailable'));
  let refreshing!: Promise<void>;
  act(() => { refreshing = result.current.refresh(); });
  await waitFor(() => expect(result.current.refreshing).toBe(true));
  await act(async () => {
    resolveProgress({ marker: 'fresh-progress' });
    await refreshing;
  });
  await waitFor(() => expect(result.current.review.isError).toBe(true));
  expect(mockProgress).toHaveBeenCalledTimes(2);
  expect(mockReview).toHaveBeenCalledTimes(2);
  await waitFor(() => {
    expect(result.current.progress.data).toEqual({ marker: 'fresh-progress' });
    expect(result.current.refreshing).toBe(false);
  });
});
