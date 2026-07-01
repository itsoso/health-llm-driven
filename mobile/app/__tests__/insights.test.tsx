/* eslint-disable import/first */
import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';

const mockBack = jest.fn();
const mockPush = jest.fn();

jest.mock('expo-router', () => ({
  useRouter: () => ({ back: mockBack, push: mockPush }),
}));

import InsightsScreen from '../insights';

describe('InsightsScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('groups health analysis routes into one navigable hub', () => {
    const { getByText } = render(<InsightsScreen />);

    expect(getByText('健康分析')).toBeTruthy();
    expect(getByText('进展与闭环')).toBeTruthy();
    expect(getByText('代谢与抗衰')).toBeTruthy();
    expect(getByText('指标与趋势')).toBeTruthy();
    expect(getByText('我的进度')).toBeTruthy();
    expect(getByText('代谢健康画像')).toBeTruthy();
    expect(getByText('肝脏趋势')).toBeTruthy();

    fireEvent.press(getByText('我的进度'));
    fireEvent.press(getByText('代谢健康画像'));
    fireEvent.press(getByText('肝脏趋势'));

    expect(mockPush).toHaveBeenCalledWith('/my-progress');
    expect(mockPush).toHaveBeenCalledWith('/metabolic-profile');
    expect(mockPush).toHaveBeenCalledWith('/liver-trend');
  });

  it('keeps longitudinal and recap views reachable from the hub', () => {
    const { getByText } = render(<InsightsScreen />);

    fireEvent.press(getByText('本周建议'));
    fireEvent.press(getByText('月度复盘'));
    fireEvent.press(getByText('指标趋势'));

    expect(mockPush).toHaveBeenCalledWith('/weekly-briefing');
    expect(mockPush).toHaveBeenCalledWith('/monthly-reports');
    expect(mockPush).toHaveBeenCalledWith('/indicator-history');
  });
});
