/* eslint-disable @typescript-eslint/no-require-imports */
import React from 'react';
import { act, fireEvent, render, waitFor } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const mockRecordWater = jest.fn();
const mockDeleteWater = jest.fn();
const mockNavigate = jest.fn();
const mockPush = jest.fn();
const mockToastShow = jest.fn();

jest.mock('../../../services/records', () => ({
  recordWater: (...args: any[]) => mockRecordWater(...args),
  deleteWater: (...args: any[]) => mockDeleteWater(...args),
}));
jest.mock('../../../applib/queryKeys', () => ({
  invalidateRecordMutation: jest.fn().mockResolvedValue(undefined),
}));
jest.mock('expo-router', () => ({
  router: {
    navigate: (...args: any[]) => mockNavigate(...args),
    push: (...args: any[]) => mockPush(...args),
  },
}));
jest.mock('expo-haptics', () => ({
  impactAsync: jest.fn().mockResolvedValue(undefined),
  notificationAsync: jest.fn().mockResolvedValue(undefined),
  selectionAsync: jest.fn().mockResolvedValue(undefined),
  ImpactFeedbackStyle: { Medium: 'medium' },
  NotificationFeedbackType: { Error: 'error' },
}));
jest.mock('../../../hooks/useToast', () => ({
  useToast: () => ({ show: mockToastShow }),
}));

const RecordTray = require('../RecordTray').default;

function renderTray() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <RecordTray />
    </QueryClientProvider>,
  );
}

describe('RecordTray water quick-log', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('logs +250ml optimistically on a single tap and shows an inline undo bar', async () => {
    mockRecordWater.mockResolvedValue({ id: 42, amount: 250, drink_type: '水' });
    const { getByLabelText, findByText } = renderTray();

    await act(async () => {
      fireEvent.press(getByLabelText('记录饮水'));
    });

    expect(mockRecordWater).toHaveBeenCalledWith(250);
    expect(await findByText('+250ml 已记录')).toBeTruthy();
    // 一键饮水不导航到记录屏。
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it('deletes the just-logged water record when 撤销 is pressed', async () => {
    mockRecordWater.mockResolvedValue({ id: 77, amount: 250, drink_type: '水' });
    mockDeleteWater.mockResolvedValue(undefined);
    const { getByLabelText, queryByText } = renderTray();

    await act(async () => {
      fireEvent.press(getByLabelText('记录饮水'));
    });
    await waitFor(() => expect(getByLabelText('撤销饮水记录')).toBeTruthy());

    await act(async () => {
      fireEvent.press(getByLabelText('撤销饮水记录'));
    });

    expect(mockDeleteWater).toHaveBeenCalledWith(77);
    await waitFor(() => expect(queryByText('+250ml 已记录')).toBeNull());
  });

  it('fails loud on write error — no fake success, error toast shown', async () => {
    mockRecordWater.mockRejectedValue(new Error('network down'));
    const { getByLabelText, queryByText } = renderTray();

    await act(async () => {
      fireEvent.press(getByLabelText('记录饮水'));
    });

    await waitFor(() => expect(mockToastShow).toHaveBeenCalledWith('饮水记录失败，请重试', 'error'));
    // 失败 → 不出现"已记录"撤销条。
    expect(queryByText('+250ml 已记录')).toBeNull();
  });

  it('long-pressing 饮水 still opens the full record screen', async () => {
    const { getByLabelText } = renderTray();

    await act(async () => {
      fireEvent(getByLabelText('记录饮水'), 'longPress');
    });

    expect(mockNavigate).toHaveBeenCalledWith('/(tabs)/record');
    expect(mockRecordWater).not.toHaveBeenCalled();
  });

  it('stack routes use push so diet capture param re-fires (regression: navigate 复用旧实例不开相机)', async () => {
    const { getByLabelText } = renderTray();

    await act(async () => {
      fireEvent.press(getByLabelText('拍照记录餐食'));
    });
    expect(mockPush).toHaveBeenCalledWith('/diet?capture=photo');
    expect(mockNavigate).not.toHaveBeenCalledWith('/diet?capture=photo');
  });

  it('tab routes keep navigate (不叠 tab 实例)', async () => {
    const { getByLabelText } = renderTray();

    await act(async () => {
      fireEvent.press(getByLabelText('更多记录方式'));
    });
    expect(mockNavigate).toHaveBeenCalledWith('/(tabs)/record');
    expect(mockPush).not.toHaveBeenCalledWith('/(tabs)/record');
  });
});
