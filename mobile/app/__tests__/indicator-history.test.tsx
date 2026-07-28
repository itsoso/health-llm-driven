/* eslint-disable import/first */
import React from 'react';
import { render } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

jest.mock('expo-router', () => ({
  useRouter: () => ({ push: jest.fn(), back: jest.fn() }),
  useLocalSearchParams: jest.fn().mockReturnValue({ type: 'weight' }),
}));

jest.mock('../../hooks/useTrendData', () => ({
  useWeightHistory: jest.fn().mockReturnValue({
    data: [{ label: '体重', color: '#FF9F0A', data: [{ date: '2026-04-20', value: 72, unit: 'kg' }] }],
    isLoading: false,
    refetch: jest.fn(),
  }),
  useBPHistory: jest.fn().mockReturnValue({
    data: [{ label: '收缩压', color: '#FF453A', data: [] }],
    isLoading: false,
    refetch: jest.fn(),
  }),
  useIndicatorTrend: jest.fn().mockReturnValue({
    data: [],
    isLoading: false,
    refetch: jest.fn(),
  }),
  useGarminMetricTrend: jest.fn().mockReturnValue({
    data: [],
    isLoading: false,
    refetch: jest.fn(),
  }),
  isGarminMetric: jest.fn((name: string) => ['heart_rate', 'hrv', 'body_battery', 'sleep'].includes(name)),
}));

import { useLocalSearchParams } from 'expo-router';
import IndicatorHistoryScreen from '../indicator-history';

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return React.createElement(QueryClientProvider, { client: qc }, children);
}

describe('IndicatorHistoryScreen', () => {
  it('renders weight title for type=weight', () => {
    (useLocalSearchParams as jest.Mock).mockReturnValue({ type: 'weight' });
    const { getByText } = render(<IndicatorHistoryScreen />, { wrapper });
    expect(getByText('体重趋势')).toBeTruthy();
  });

  it('renders blood pressure title for type=blood_pressure', () => {
    (useLocalSearchParams as jest.Mock).mockReturnValue({ type: 'blood_pressure' });
    const { getByText } = render(<IndicatorHistoryScreen />, { wrapper });
    expect(getByText('血压趋势')).toBeTruthy();
  });

  it('renders custom indicator title', () => {
    (useLocalSearchParams as jest.Mock).mockReturnValue({ type: '空腹血糖' });
    const { getByText } = render(<IndicatorHistoryScreen />, { wrapper });
    expect(getByText('空腹血糖趋势')).toBeTruthy();
  });

  it('shows latest value summary card', () => {
    (useLocalSearchParams as jest.Mock).mockReturnValue({ type: 'weight' });
    const { getByText } = render(<IndicatorHistoryScreen />, { wrapper });
    expect(getByText('最新记录')).toBeTruthy();
    expect(getByText('72')).toBeTruthy();
    expect(getByText('kg')).toBeTruthy();
  });

  it('has a back button', () => {
    (useLocalSearchParams as jest.Mock).mockReturnValue({ type: 'weight' });
    const { getByTestId } = render(<IndicatorHistoryScreen />, { wrapper });
    expect(getByTestId('back-button')).toBeTruthy();
  });
});
