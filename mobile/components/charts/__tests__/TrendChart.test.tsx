import React from 'react';
import { render, fireEvent } from '@testing-library/react-native';
import TrendChart from '../TrendChart';
import type { TrendSeries } from '../../../services/trends';

const mockSeries: TrendSeries[] = [
  {
    label: '体重',
    color: '#FF9F0A',
    data: [
      { date: '2026-04-15', value: 72, unit: 'kg' },
      { date: '2026-04-16', value: 71.5, unit: 'kg' },
      { date: '2026-04-17', value: 71.8, unit: 'kg' },
    ],
  },
  {
    label: 'BMI',
    color: '#64D2FF',
    data: [
      { date: '2026-04-15', value: 22.5, unit: '' },
      { date: '2026-04-16', value: 22.3, unit: '' },
      { date: '2026-04-17', value: 22.4, unit: '' },
    ],
    referenceRange: { low: 18.5, high: 24.9 },
  },
];

describe('TrendChart', () => {
  it('renders without crashing with data', () => {
    const { toJSON } = render(<TrendChart series={mockSeries} />);
    expect(toJSON()).toBeTruthy();
  });

  it('shows empty text when series have no data', () => {
    const empty: TrendSeries[] = [{ label: 'X', color: '#000', data: [] }];
    const { getByText } = render(<TrendChart series={empty} />);
    expect(getByText('暂无数据')).toBeTruthy();
  });

  it('renders legend when multiple series exist', () => {
    const { getByText } = render(<TrendChart series={mockSeries} />);
    expect(getByText('体重')).toBeTruthy();
    expect(getByText('BMI')).toBeTruthy();
  });

  it('renders data point touch targets', () => {
    const { getByTestId } = render(<TrendChart series={mockSeries} />);
    expect(getByTestId('point-体重-0')).toBeTruthy();
    expect(getByTestId('point-BMI-2')).toBeTruthy();
  });

  it('shows tooltip when data point is pressed', () => {
    const { getByTestId, queryByTestId } = render(<TrendChart series={mockSeries} />);
    expect(queryByTestId('data-point-tooltip')).toBeNull();
    fireEvent.press(getByTestId('point-体重-0'));
    expect(getByTestId('data-point-tooltip')).toBeTruthy();
  });

  it('renders with single series (no legend)', () => {
    const single: TrendSeries[] = [mockSeries[0]];
    const { queryByText } = render(<TrendChart series={single} />);
    // Legend only shows when >1 series
    expect(queryByText('BMI')).toBeNull();
  });
});
