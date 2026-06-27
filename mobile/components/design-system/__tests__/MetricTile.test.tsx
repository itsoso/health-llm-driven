import React from 'react';
import { StyleSheet } from 'react-native';
import { render } from '@testing-library/react-native';
import MetricTile from '../MetricTile';
import { revaColors } from '../../../constants/revaTheme';

// P1 设计统一:MetricTile 已迁到 Reva 静态 token(不再走 useTheme),
// neutral 文字色固定为 ink2(label)/ink3(subtitle)。

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

  it('uses Reva neutral ink tokens for neutral text', () => {
    const { getByText } = render(<MetricTile {...defaultProps} subtitle="正常范围" />);

    expect(StyleSheet.flatten(getByText('心率').props.style).color).toBe(revaColors.ink2);
    expect(StyleSheet.flatten(getByText('正常范围').props.style).color).toBe(revaColors.ink3);
  });
});
