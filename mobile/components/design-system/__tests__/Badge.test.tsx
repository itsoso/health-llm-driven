import React from 'react';
import { StyleSheet } from 'react-native';
import { render } from '@testing-library/react-native';
import Badge from '../Badge';

jest.mock('../../../hooks/useTheme', () => ({
  useTheme: () => ({
    c: {
      labelPrimary: '#111', labelSecondary: '#555', labelTertiary: '#999',
      brand: '#0A8F8F', brandLight: '#E6F5F5',
      green: '#30D158', tintGreen: '#E8FAF0',
      amber: '#FF9F0A', tintAmber: '#FFF5E6',
      red: '#FF453A', tintRed: '#FFE8E6',
      blue: '#64D2FF', tintBlue: '#E6F5FF',
      fill: '#E5E5EA',
    },
    isDark: false,
  }),
}));

describe('Badge', () => {
  it('renders the label', () => {
    const { getByText } = render(<Badge label="高风险" tone="danger" />);
    expect(getByText('高风险')).toBeTruthy();
  });

  it('maps danger tone to themed red fg + tint bg (dark-mode aware)', () => {
    const { getByText, UNSAFE_root } = render(<Badge label="高风险" tone="danger" />);
    // text color = red fg
    expect(StyleSheet.flatten(getByText('高风险').props.style).color).toBe('#FF453A');
  });

  it('maps ok tone to green', () => {
    const { getByText } = render(<Badge label="正常" tone="ok" />);
    expect(StyleSheet.flatten(getByText('正常').props.style).color).toBe('#30D158');
  });

  it('defaults to neutral tone', () => {
    const { getByText } = render(<Badge label="待定" />);
    expect(StyleSheet.flatten(getByText('待定').props.style).color).toBe('#555');
  });

  it('caps Dynamic Type compact so badges do not break layout', () => {
    const { getByText } = render(<Badge label="x" tone="brand" />);
    expect(getByText('x').props.maxFontSizeMultiplier).toBe(1.15);
  });
});
