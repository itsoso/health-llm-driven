import React from 'react';
import { render, fireEvent } from '@testing-library/react-native';
import StreakBadge from '../StreakBadge';

jest.mock('../../../hooks/useTheme', () => ({
  useTheme: () => ({
    c: {
      bgCard: '#fff', fill: '#f5f5f5',
      labelPrimary: '#111', labelSecondary: '#555', labelTertiary: '#999',
      separator: '#eee', brand: '#0A8F8F', orange: '#EA580C', tintOrange: '#FFEDD5',
    },
    isDark: false,
  }),
}));

describe('StreakBadge', () => {
  it('shows the live streak with best when current > 0', () => {
    const { getByText, getByLabelText } = render(<StreakBadge current={5} best={12} />);
    expect(getByText('连续 5 天')).toBeTruthy();
    expect(getByText('· 最佳 12')).toBeTruthy();
    expect(getByLabelText('已连续打卡 5 天，历史最佳 12 天')).toBeTruthy();
  });

  it('omits the best chip when best is 0 but current > 0', () => {
    const { getByText, queryByText } = render(<StreakBadge current={1} best={0} />);
    expect(getByText('连续 1 天')).toBeTruthy();
    expect(queryByText(/最佳/)).toBeNull();
  });

  it('shows an inviting zero state instead of faking a streak', () => {
    const { getByText, queryByText } = render(<StreakBadge current={0} best={0} />);
    expect(getByText('今天开始记录')).toBeTruthy();
    expect(getByText('· 完成一次打卡，开启连续天数')).toBeTruthy();
    expect(queryByText(/连续 0 天/)).toBeNull();
  });

  it('shows an honest error state instead of degrading to 0', () => {
    const { getByText, getByLabelText, queryByText } = render(
      <StreakBadge current={null} best={null} isError />,
    );
    expect(getByText('连续天数加载失败')).toBeTruthy();
    expect(getByLabelText('连续打卡天数加载失败，下拉重试')).toBeTruthy();
    expect(queryByText('今天开始记录')).toBeNull();
    expect(queryByText(/连续 0 天/)).toBeNull();
  });

  it('fires onPress when tapped', () => {
    const onPress = jest.fn();
    const { getByTestId } = render(<StreakBadge current={3} best={3} onPress={onPress} />);
    fireEvent.press(getByTestId('home-streak-badge'));
    expect(onPress).toHaveBeenCalledTimes(1);
  });
});
