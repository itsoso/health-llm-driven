import React from 'react';
import { render, fireEvent } from '@testing-library/react-native';
import OutcomeWinCard from '../OutcomeWinCard';

jest.mock('../../../hooks/useTheme', () => ({
  useTheme: () => ({
    c: {
      bgCard: '#fff', fill: '#f5f5f5',
      labelPrimary: '#111', labelSecondary: '#555', labelTertiary: '#999',
      separator: '#eee', brand: '#0A8F8F', brandLight: '#E6F7F7',
      green: '#16A34A', tintGreen: '#DCFCE7',
    },
    isDark: false,
  }),
}));

describe('OutcomeWinCard', () => {
  it('celebrates improvements when results have been graded', () => {
    const { getByText, getByLabelText } = render(
      <OutcomeWinCard improved={3} graded={5} totalSurfaced={8} />,
    );
    expect(getByText('AI 已帮你改善 3 项')).toBeTruthy();
    expect(getByText('已验证 5 项 · 3/5 改善')).toBeTruthy();
    expect(getByLabelText('AI 建议里已评估 5 项，其中 3 项指标改善')).toBeTruthy();
  });

  it('shows a verifying state when suggestions exist but nothing graded yet', () => {
    const { getByText, queryByText } = render(
      <OutcomeWinCard improved={0} graded={0} totalSurfaced={4} />,
    );
    expect(getByText('成果验证中')).toBeTruthy();
    expect(queryByText(/已帮你改善/)).toBeNull();
  });

  it('shows an empty invite when there are no suggestions at all', () => {
    const { getByText, queryByText } = render(
      <OutcomeWinCard improved={0} graded={0} totalSurfaced={0} />,
    );
    expect(getByText('还没有成果记录')).toBeTruthy();
    expect(queryByText('成果验证中')).toBeNull();
  });

  it('shows an honest error state instead of zero', () => {
    const { getByText, queryByText } = render(
      <OutcomeWinCard improved={null} graded={null} totalSurfaced={null} isError />,
    );
    expect(getByText('成果加载失败')).toBeTruthy();
    expect(queryByText('还没有成果记录')).toBeNull();
    expect(queryByText(/已帮你改善/)).toBeNull();
  });

  it('fires onPress when tapped', () => {
    const onPress = jest.fn();
    const { getByTestId } = render(
      <OutcomeWinCard improved={3} graded={5} totalSurfaced={8} onPress={onPress} />,
    );
    fireEvent.press(getByTestId('home-outcome-win-card'));
    expect(onPress).toHaveBeenCalledTimes(1);
  });
});
