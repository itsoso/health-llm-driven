/* eslint-disable import/first */
import React from 'react';
import { act, fireEvent, waitFor } from '@testing-library/react-native';

const mockBack = jest.fn();
const mockCloseRokidCustomView = jest.fn();
const mockOpenRokidCustomView = jest.fn();
const mockUpdateRokidCustomView = jest.fn();
const mockOpenRokidApp = jest.fn();
const mockQueryRokidApp = jest.fn();
const mockStopRokidApp = jest.fn();
const mockCreateRokidPushupSession = jest.fn();
const mockFinishRokidPushupSession = jest.fn();
const mockListRokidPushupEvents = jest.fn();
const mockPost = jest.fn();
const mockInvalidateRecordMutation = jest.fn();

jest.mock('expo-router', () => ({
  Stack: { Screen: () => null },
  useRouter: () => ({ back: mockBack }),
}));

jest.mock('expo-haptics', () => ({
  ImpactFeedbackStyle: { Light: 'Light', Medium: 'Medium' },
  impactAsync: jest.fn(),
}));

jest.mock('../../modules/rokid-bridge', () => ({
  closeRokidCustomView: (...args: any[]) => mockCloseRokidCustomView(...args),
  openRokidCustomView: (...args: any[]) => mockOpenRokidCustomView(...args),
  updateRokidCustomView: (...args: any[]) => mockUpdateRokidCustomView(...args),
  openRokidApp: (...args: any[]) => mockOpenRokidApp(...args),
  queryRokidApp: (...args: any[]) => mockQueryRokidApp(...args),
  stopRokidApp: (...args: any[]) => mockStopRokidApp(...args),
}));

jest.mock('../../services/rokidPushupSession', () => {
  const actual = jest.requireActual('../../services/rokidPushupSession');
  return {
    ...actual,
    ROKID_PUSHUP_APP_ACTIVITY: '.MainActivity',
    ROKID_PUSHUP_APP_PACKAGE: 'life.executor.health.rokid.pushup',
    createRokidPushupSession: (...args: any[]) => mockCreateRokidPushupSession(...args),
    finishRokidPushupSession: (...args: any[]) => mockFinishRokidPushupSession(...args),
    listRokidPushupEvents: (...args: any[]) => mockListRokidPushupEvents(...args),
  };
});

jest.mock('../../services/api', () => ({
  post: (...args: any[]) => mockPost(...args),
}));

jest.mock('../../applib/queryKeys', () => ({
  invalidateRecordMutation: (...args: any[]) => mockInvalidateRecordMutation(...args),
}));

import RokidPushupCoachScreen from '../rokid-pushup-coach';
import { renderWithProviders } from '../../test-utils';

const flushAsyncUpdates = () => new Promise((resolve) => setTimeout(resolve, 0));

describe('RokidPushupCoachScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockOpenRokidCustomView.mockResolvedValue({ ok: true });
    mockUpdateRokidCustomView.mockResolvedValue({ ok: true });
    mockCloseRokidCustomView.mockResolvedValue({ ok: true });
    mockCreateRokidPushupSession.mockResolvedValue({
      id: 7,
      target_reps: 20,
      open_url: 'reva://rokid/pushup?session_id=7',
      ingest_url: 'https://health.executor.life/api/v1/devices/rokid/pushup-sessions/7/events',
    });
    mockQueryRokidApp.mockResolvedValue({ ok: true, installed: true });
    mockOpenRokidApp.mockResolvedValue({ ok: true, opened: true });
    mockStopRokidApp.mockResolvedValue({ ok: true, stopped: true });
    mockListRokidPushupEvents.mockResolvedValue([]);
    mockPost.mockResolvedValue({ data: { id: 123 } });
    mockInvalidateRecordMutation.mockResolvedValue(undefined);
  });

  it('polls glasses reps, saves the exercise record, and stops the real session', async () => {
    mockListRokidPushupEvents
      .mockResolvedValueOnce([
        {
          id: 11,
          session_id: 7,
          user_id: 3,
          event_type: 'rep',
          reps: 5,
          phase: 'up',
          quality_score: 88,
          payload: { suggestion: '保持稳定节奏。' },
          occurred_at: '2026-06-19T12:00:00Z',
          created_at: '2026-06-19T12:00:00Z',
        },
      ])
      .mockResolvedValue([]);

    const screen = renderWithProviders(<RokidPushupCoachScreen />);

    await act(async () => {
      fireEvent.press(screen.getByText('启动眼镜识别'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(mockOpenRokidApp).toHaveBeenCalledWith({
        packageName: 'life.executor.health.rokid.pushup',
        activityName: '.MainActivity',
        url: 'reva://rokid/pushup?session_id=7',
      });
      expect(screen.getByText('已接收 1 条眼镜姿态事件')).toBeTruthy();
      expect(screen.getByText('5')).toBeTruthy();
    });

    await act(async () => {
      fireEvent.press(screen.getByText('保存本组'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith('/daily-health/exercise', expect.objectContaining({
        exercise_type: '俯卧撑',
        reps: 5,
        sets: 1,
        intensity: 'moderate',
        notes: expect.stringContaining('Rokid 俯卧撑计数: 5/20'),
      }));
      expect(screen.getByText('已保存')).toBeTruthy();
    });

    await act(async () => {
      fireEvent.press(screen.getByText('停止'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(mockFinishRokidPushupSession).toHaveBeenCalledWith(7);
      expect(mockStopRokidApp).toHaveBeenCalledWith('life.executor.health.rokid.pushup');
      expect(screen.getByText('眼镜端识别已停止')).toBeTruthy();
    });
  });
});
