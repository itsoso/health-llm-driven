/* eslint-disable import/first */
import React from 'react';
import { act, fireEvent, waitFor } from '@testing-library/react-native';

const mockBack = jest.fn();
const mockPush = jest.fn();
const mockReplace = jest.fn();
let mockDetailId: unknown;
const mockGetLogs = jest.fn();
let mockUserId: number | null = 7;
jest.mock('../../hooks/useAuth', () => ({ useAuth: () => ({ user: mockUserId ? { id: mockUserId } : null, isAuthenticated: Boolean(mockUserId) }) }));

jest.mock('expo-router', () => ({
  useRouter: () => ({ back: mockBack, push: mockPush, replace: mockReplace }),
  useLocalSearchParams: () => ({ detailId: mockDetailId }),
}));

jest.mock('../../services/notifications', () => ({
  getLogs: (...args: any[]) => mockGetLogs(...args),
}));

import NotificationHistoryScreen from '../notification-history';
import { renderWithProviders } from '../../test-utils';

describe('NotificationHistoryScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUserId = 7;
    mockDetailId = undefined;
    mockGetLogs.mockResolvedValue([
      {
        id: 1,
        notification_type: 'workout_analysis',
        channel: 'ios_apns',
        title: '跑后教练: 跑步 (2.9km · 20分钟)',
        content: '指标 | 本次数 据 | 评价',
        status: 'sent',
        sent_at: '2026-05-21T12:00:00',
        created_at: '2026-05-21T12:00:00',
        deep_link: '/workout-detail?id=123',
        data: { workout_id: 123 },
        channels: [{ name: 'ios_apns', status: 'sent' }],
      },
    ]);
  });

  it('opens the notification deep link when a log row is pressed', async () => {
    const screen = renderWithProviders(<NotificationHistoryScreen />);

    await waitFor(() => {
      expect(screen.getByText('跑后教练: 跑步 (2.9km · 20分钟)')).toBeTruthy();
    });

    fireEvent.press(screen.getByText('跑后教练: 跑步 (2.9km · 20分钟)'));

    expect(mockPush).toHaveBeenCalledWith('/workout-detail?id=123');
  });

  it('opens today actions for a protocol history link without submitting completion', async () => {
    mockGetLogs.mockResolvedValue([{
      id: 2, notification_type: 'reminder', channel: 'ios_apns',
      title: '健康提醒', content: '完成后确认', status: 'sent',
      deep_link: '/agenda',
      data: { kind: 'protocol', category: 'AGENDA_ACTION',
        complete_ref: { object_type: 'health_protocol', object_id: 42 } },
    }]);
    const screen = renderWithProviders(<NotificationHistoryScreen />);
    const row = await screen.findByLabelText('打开 健康提醒');
    expect(row).not.toBeDisabled();
    fireEvent.press(row);
    expect(mockPush).toHaveBeenCalledTimes(1);
    expect(mockPush).toHaveBeenCalledWith('/agenda');
  });
  it('opens saved sleep advice without a legacy deep link', async () => {
    mockGetLogs.mockResolvedValue([{
      id: 81, notification_type: 'ai_advice', title: '睡眠质量明显下滑',
      content: '历史推送内容', status: 'sent', channel: 'ios_apns',
    }]);
    const screen = renderWithProviders(<NotificationHistoryScreen />);
    fireEvent.press(await screen.findByLabelText('打开 睡眠质量明显下滑'));
    expect(mockPush).toHaveBeenCalledWith('/notification-detail?id=81');
    expect(screen.queryClient.getQueryData(['notificationLogs', 7])).toBeTruthy();
  });

  it.each([undefined, '/notification-detail?id=82', '/notification-history?detailId=82'])('preserves legacy screen destinations before generic detail %p', async deep_link => {
    mockGetLogs.mockResolvedValue([{
      id: 82, notification_type: 'ai_advice', title: '睡眠建议',
      content: '内容', status: 'sent', channel: 'ios_apns', data: { screen: 'sleep' }, deep_link,
    }]);
    const screen = renderWithProviders(<NotificationHistoryScreen />);
    fireEvent.press(await screen.findByLabelText('打开 睡眠建议'));
    expect(mockPush).toHaveBeenCalledWith('/sleep');
  });

  it('hides the previous owner history when switching accounts', async () => {
    const screen = renderWithProviders(<NotificationHistoryScreen />);
    await screen.findByText('跑后教练: 跑步 (2.9km · 20分钟)');
    mockUserId = 8;
    mockGetLogs.mockReturnValue(new Promise(() => {}));
    screen.rerender(<NotificationHistoryScreen />);
    expect(screen.queryByText('跑后教练: 跑步 (2.9km · 20分钟)')).toBeNull();
  });

  it('bridges an authenticated compatibility link once, without fetching history', () => {
    mockDetailId = '81';
    const screen = renderWithProviders(<React.StrictMode><NotificationHistoryScreen /></React.StrictMode>);
    expect(mockReplace).toHaveBeenCalledWith('/notification-detail?id=81');
    screen.rerender(<React.StrictMode><NotificationHistoryScreen /></React.StrictMode>);
    expect(mockReplace).toHaveBeenCalledTimes(1);
    expect(mockPush).not.toHaveBeenCalled();
    expect(mockGetLogs).not.toHaveBeenCalled();
  });

  it('defers the bridge until authenticated and resets for another owner or id', () => {
    mockDetailId = '81'; mockUserId = null;
    const screen = renderWithProviders(<NotificationHistoryScreen />);
    expect(screen.getByText('请先登录后查看推送历史')).toBeTruthy();
    expect(mockReplace).not.toHaveBeenCalled();
    expect(mockGetLogs).not.toHaveBeenCalled();
    mockUserId = 7;
    screen.rerender(<NotificationHistoryScreen />);
    expect(mockReplace).toHaveBeenCalledTimes(1);
    mockUserId = 8;
    screen.rerender(<NotificationHistoryScreen />);
    expect(mockReplace).toHaveBeenCalledTimes(2);
    mockDetailId = '82';
    screen.rerender(<NotificationHistoryScreen />);
    expect(mockReplace).toHaveBeenLastCalledWith('/notification-detail?id=82');
    expect(mockReplace).toHaveBeenCalledTimes(3);
    expect(mockGetLogs).not.toHaveBeenCalled();
  });

  it.each(['0', '-1', '1.5', '81oops', '2147483648', ['81'], ['81', '82'], ''])('keeps malformed bridge id %p on safe history without looping', async detailId => {
    mockDetailId = detailId;
    const screen = renderWithProviders(<NotificationHistoryScreen />);
    await screen.findByText('跑后教练: 跑步 (2.9km · 20分钟)');
    screen.rerender(<NotificationHistoryScreen />);
    expect(mockReplace).not.toHaveBeenCalled();
    expect(mockGetLogs).toHaveBeenCalledTimes(1);
  });

  it('does not reveal a pending previous-owner history response while bridging', async () => {
    let resolveOld!: (value: unknown[]) => void;
    mockGetLogs.mockReturnValueOnce(new Promise(resolve => { resolveOld = resolve; }));
    const screen = renderWithProviders(<NotificationHistoryScreen />);
    mockUserId = 8; mockDetailId = '81';
    screen.rerender(<NotificationHistoryScreen />);
    await act(async () => { resolveOld([{ id: 1, title: '旧账号私密推送', content: '旧内容' }]); });
    expect(screen.queryByText('旧账号私密推送')).toBeNull();
    expect(mockGetLogs).toHaveBeenCalledTimes(1);
    expect(mockReplace).toHaveBeenCalledTimes(1);
  });

  it.each(['/notification-detail?id=83', '/notification-history?detailId=83'])('keeps workout destinations before generic payload link %s', async deep_link => {
    mockGetLogs.mockResolvedValue([{
      id: 83, notification_type: 'workout_analysis', title: '运动分析', content: '内容',
      status: 'sent', channel: 'ios_apns', data: { deep_link, workout_id: 123 }, deep_link,
    }]);
    const screen = renderWithProviders(<NotificationHistoryScreen />);
    fireEvent.press(await screen.findByLabelText('打开 运动分析'));
    expect(mockPush).toHaveBeenCalledWith('/workout-detail?id=123');
  });

  it('preserves legacy screen even when the generic compatibility link is inside data', async () => {
    mockGetLogs.mockResolvedValue([{
      id: 84, notification_type: 'ai_advice', title: '睡眠建议', content: '内容', status: 'sent',
      channel: 'ios_apns', data: { deep_link: '/notification-history?detailId=84', screen: 'sleep' },
    }]);
    const screen = renderWithProviders(<NotificationHistoryScreen />);
    fireEvent.press(await screen.findByLabelText('打开 睡眠建议'));
    expect(mockPush).toHaveBeenCalledWith('/sleep');
  });

});
