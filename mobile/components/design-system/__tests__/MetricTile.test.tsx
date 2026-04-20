import React from 'react';
import { render } from '@testing-library/react-native';
import MetricTile from '../MetricTile';

describe('MetricTile', () => {
  const defaultProps = {
    label: '心率',
    value: '72',
    unit: 'bpm',
    icon: 'heart' as const,
    color: '#FF375F',
    tintColor: '#FFE6EE',
  };

  it('renders without crashing', () => {
    const { getByText } = render(<MetricTile {...defaultProps} />);
    expect(getByText('心率')).toBeTruthy();
    expect(getByText('72')).toBeTruthy();
    expect(getByText('bpm')).toBeTruthy();
  });

  it('renders subtitle when provided', () => {
    const { getByText } = render(
      <MetricTile {...defaultProps} subtitle="正常范围" />,
    );
    expect(getByText('正常范围')).toBeTruthy();
  });

  it('does not render unit when not provided', () => {
    const { queryByText } = render(
      <MetricTile {...defaultProps} unit={undefined} />,
    );
    expect(queryByText('bpm')).toBeNull();
  });

  it('renders numeric value', () => {
    const { getByText } = render(
      <MetricTile {...defaultProps} value={120} />,
    );
    expect(getByText('120')).toBeTruthy();
  });
});
