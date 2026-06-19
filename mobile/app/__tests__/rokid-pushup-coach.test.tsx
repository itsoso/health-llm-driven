/* eslint-disable import/first */
import React from 'react';
import { act, fireEvent, waitFor } from '@testing-library/react-native';

const mockBack = jest.fn();
const mockCloseRokidCustomView = jest.fn();
const mockOpenRokidCustomView = jest.fn();
const mockUpdateRokidCustomView = jest.fn();
const mockOpenRokidApp = jest.fn();
const mockQueryRokidApp = jest.fn();
const mockInstallBundledRokidApp = jest.fn();
const mockStopRokidApp = jest.fn();
const mockCreateRokidPushupSession = jest.fn();
const mockFinishRokidPushupSession = jest.fn();
const mockListRokidPushupEvents = jest.fn();
const mockPost = jest.fn();

jest.mock('expo-router', () => ({
  Stack: { Screen: () => null },
  useRouter: () => ({ back: mockBack }),
  useFocusEffect: jest.fn(),
}));

jest.mock('../../modules/rokid-bridge', () => ({
  closeRokidCustomView: (...args: any[]) => mockCloseRokidCustomView(...args),
  openRokidCustomView: (...args: any[]) => mockOpenRokidCustomView(...args),
  updateRokidCustomView: (...args: any[]) => mockUpdateRokidCustomView(...args),
  openRokidApp: (...args: any[]) => mockOpenRokidApp(...args),
  queryRokidApp: (...args: any[]) => mockQueryRokidApp(...args),
  installBundledRokidApp: (...args: any[]) => mockInstallBundledRokidApp(...args),
  stopRokidApp: (...args: any[]) => mockStopRokidApp(...args),
}));

jest.mock('../../services/rokidPushupSession', () => ({
  ROKID_PUSHUP_APK_RESOURCE_EXTENSION: 'apk',
  ROKID_PUSHUP_APK_RESOURCE_NAME: 'rokid-pushup-glasses',
  ROKID_PUSHUP_APP_ACTIVITY: '.MainActivity',
  ROKID_PUSHUP_APP_PACKAGE: 'life.executor.health.rokid.pushup',
  applyRokidPushupEventToCoach: (state: any) => state,
  createRokidPushupSession: (...args: any[]) => mockCreateRokidPushupSession(...args),
  finishRokidPushupSession: (...args: any[]) => mockFinishRokidPushupSession(...args),
  listRokidPushupEvents: (...args: any[]) => mockListRokidPushupEvents(...args),
}));

jest.mock('../../services/api', () => ({
  post: (...args: any[]) => mockPost(...args),
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
    mockQueryRokidApp
      .mockResolvedValueOnce({ ok: true, installed: false })
      .mockResolvedValueOnce({ ok: true, installed: true });
    mockInstallBundledRokidApp.mockResolvedValue({ ok: true, installed: true });
    mockOpenRokidApp.mockResolvedValue({ ok: true, opened: true });
    mockStopRokidApp.mockResolvedValue({ ok: true, stopped: true });
    mockListRokidPushupEvents.mockResolvedValue([]);
  });

  it('installs the bundled glasses APK before starting real pose recognition when the app is missing', async () => {
    const screen = renderWithProviders(<RokidPushupCoachScreen />);

    await act(async () => {
      fireEvent.press(screen.getByText('启动眼镜识别'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(mockInstallBundledRokidApp).toHaveBeenCalledWith({
        resourceName: 'rokid-pushup-glasses',
        resourceExtension: 'apk',
        packageName: 'life.executor.health.rokid.pushup',
      });
      expect(mockOpenRokidApp).toHaveBeenCalledWith({
        packageName: 'life.executor.health.rokid.pushup',
        activityName: '.MainActivity',
        url: 'reva://rokid/pushup?session_id=7',
      });
      expect(screen.getByText('眼镜端识别已启动, 等待姿态数据...')).toBeTruthy();
    });

    expect(mockQueryRokidApp).toHaveBeenCalledTimes(2);
  });
});
