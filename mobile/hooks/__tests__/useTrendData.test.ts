import { renderHook, waitFor } from '@testing-library/react-native';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useWeightHistory, useBPHistory, useIndicatorTrend } from '../useTrendData';

jest.mock('../../services/trends', () => ({
  fetchWeightTrend: jest.fn().mockResolvedValue([{ label: '体重', color: '#FF9F0A', data: [] }]),
  fetchBPTrend: jest.fn().mockResolvedValue([]),
  fetchIndicatorTrend: jest.fn().mockResolvedValue([]),
}));

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return React.createElement(QueryClientProvider, { client: qc }, children);
}

describe('useWeightHistory', () => {
  it('fetches weight trend data', async () => {
    const { result } = renderHook(() => useWeightHistory('1M'), { wrapper });
    expect(result.current.isLoading).toBe(true);
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(1);
    expect(result.current.data![0].label).toBe('体重');
  });
});

describe('useBPHistory', () => {
  it('uses correct query key', async () => {
    const { result } = renderHook(() => useBPHistory('3M'), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });
});

describe('useIndicatorTrend', () => {
  it('is disabled when name is empty', () => {
    const { result } = renderHook(() => useIndicatorTrend('', '1M'), { wrapper });
    expect(result.current.fetchStatus).toBe('idle');
  });

  it('fetches when name is provided', async () => {
    const { result } = renderHook(() => useIndicatorTrend('空腹血糖', '3M'), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });
});
