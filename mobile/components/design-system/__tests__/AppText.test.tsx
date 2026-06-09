import React from 'react';
import { StyleSheet } from 'react-native';
import { render } from '@testing-library/react-native';
import AppText from '../AppText';
import { typography, FONT_SIZE_CAPS } from '../../../constants/theme';

jest.mock('../../../hooks/useTheme', () => ({
  useTheme: () => ({
    c: {
      labelPrimary: '#111111',
      labelSecondary: '#555555',
      labelTertiary: '#999999',
      brand: '#0A8F8F',
    },
    isDark: false,
  }),
}));

function flatStyle(node: any) {
  return StyleSheet.flatten(node.props.style);
}

describe('AppText', () => {
  it('applies the typography variant', () => {
    const { getByText } = render(<AppText variant="titleSmall">标题</AppText>);
    const s = flatStyle(getByText('标题'));
    expect(s.fontSize).toBe(typography.titleSmall.fontSize);
    expect(s.fontWeight).toBe(typography.titleSmall.fontWeight);
  });

  it('defaults to bodyMedium + primary tone', () => {
    const { getByText } = render(<AppText>正文</AppText>);
    const s = flatStyle(getByText('正文'));
    expect(s.fontSize).toBe(typography.bodyMedium.fontSize);
    expect(s.color).toBe('#111111');
  });

  it('maps tone to the themed color (dark-mode aware via useTheme)', () => {
    const { getByText } = render(<AppText tone="secondary">副</AppText>);
    expect(flatStyle(getByText('副')).color).toBe('#555555');
    const { getByText: g2 } = render(<AppText tone="brand">品牌</AppText>);
    expect(flatStyle(g2('品牌')).color).toBe('#0A8F8F');
  });

  it('applies the default Dynamic Type cap', () => {
    const { getByText } = render(<AppText>x</AppText>);
    expect(getByText('x').props.maxFontSizeMultiplier).toBe(FONT_SIZE_CAPS.default);
  });

  it('uses the metric cap when requested', () => {
    const { getByText } = render(<AppText variant="metric" cap="metric">2,967</AppText>);
    expect(getByText('2,967').props.maxFontSizeMultiplier).toBe(FONT_SIZE_CAPS.metric);
  });

  it('lets an explicit maxFontSizeMultiplier override the cap', () => {
    const { getByText } = render(<AppText maxFontSizeMultiplier={2}>y</AppText>);
    expect(getByText('y').props.maxFontSizeMultiplier).toBe(2);
  });

  it('lets style override the tone color', () => {
    const { getByText } = render(<AppText tone="primary" style={{ color: '#FF0000' }}>z</AppText>);
    expect(flatStyle(getByText('z')).color).toBe('#FF0000');
  });
});
