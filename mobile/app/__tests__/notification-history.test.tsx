/* eslint-disable import/first */
import React from 'react';
import { fireEvent, waitFor } from '@testing-library/react-native';

const mockBack = jest.fn();
const mockPush = jest.fn();
const mockGetLogs = jest.fn();

jest.mock('expo-router', () => ({
  useRouter: () => ({ back: mockBack, push: mockPush }),
}));

jest.mock('../../services/notifications', () => ({
  getLogs: (...args: any[]) => mockGetLogs(...args),
}));

import NotificationHistoryScreen from '../notification-history';
import { renderWithProviders } from '../../test-utils';

describe('NotificationHistoryScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
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
});
