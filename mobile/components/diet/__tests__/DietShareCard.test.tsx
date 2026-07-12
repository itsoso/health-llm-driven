import React from 'react';
import { PixelRatio, Share } from 'react-native';
import * as Clipboard from 'expo-clipboard';
import { act, fireEvent, render, waitFor } from '@testing-library/react-native';

const mockCaptureRef = jest.fn().mockResolvedValue('file:///meal-share.png');
const mockReleaseCapture = jest.fn();
const mockShareAsync = jest.fn().mockResolvedValue(undefined);

jest.mock('react-native-view-shot', () => ({
  captureRef: (...args: any[]) => mockCaptureRef(...args),
  releaseCapture: (...args: any[]) => mockReleaseCapture(...args),
}));

jest.mock('expo-sharing', () => ({
  isAvailableAsync: jest.fn().mockResolvedValue(true),
  shareAsync: (...args: any[]) => mockShareAsync(...args),
}));

jest.mock('expo-clipboard', () => ({
  setStringAsync: jest.fn().mockResolvedValue(undefined),
}));

jest.mock('expo-haptics', () => ({
  notificationAsync: jest.fn(),
  NotificationFeedbackType: { Success: 'success' },
}));

import DietShareCard, {
  DIET_SHARE_IMAGE_TIMEOUT_MS,
  DietShareSheet,
  dietShareCaptureDimensions,
} from '../DietShareCard';
import type { DietRecord } from '../../../services/diet';

const record: DietRecord = {
  id: 88,
  user_id: 1,
  record_date: '2026-07-11',
  meal_type: 'lunch',
  food_items: '鸡胸肉 200g、杂粮饭 1碗',
  source: 'china_food_composition',
  calories: 560,
  protein: 67,
  carbs: 48,
  fat: 9.2,
  fiber: 3,
  alcohol_units: null,
  image_url: null,
  notes: null,
  health_tips: null,
};

describe('DietShareCard', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.spyOn(Share, 'share').mockResolvedValue({ action: Share.sharedAction });
  });

  it('renders a privacy-safe 3:4 meal story with real record data', () => {
    const { getByText, queryByText } = render(
      <DietShareCard record={record} dateLabel="7月11日 · 午餐" />,
    );

    expect(getByText('小巴 / 今日饮食')).toBeTruthy();
    expect(getByText('蛋白质拉满的一餐')).toBeTruthy();
    expect(getByText('鸡胸肉 200g、杂粮饭 1碗')).toBeTruthy();
    expect(getByText('560')).toBeTruthy();
    expect(getByText('蛋白质')).toBeTruthy();
    expect(getByText('67g')).toBeTruthy();
    expect(getByText('营养表校准')).toBeTruthy();
    expect(getByText('今日状态：高蛋白 · 低脂')).toBeTruthy();
    expect(getByText('已确认')).toBeTruthy();
    expect(getByText('可分享')).toBeTruthy();
    expect(queryByText('user_id')).toBeNull();
  });

  it('turns confirmed high-protein meals into a shareable nutrition headline', async () => {
    const { getByText } = render(
      <DietShareSheet
        visible
        record={record}
        dateLabel="7月11日 · 午餐"
        onClose={jest.fn()}
      />,
    );

    expect(getByText('蛋白质拉满的一餐')).toBeTruthy();
    fireEvent.press(getByText('复制朋友圈文案'));

    await waitFor(() => {
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('蛋白质拉满的一餐'));
    });
  });

  it('shows nutrition highlight tags on the share card and WeChat caption', async () => {
    const { getByText } = render(
      <DietShareSheet
        visible
        record={record}
        dateLabel="7月11日 · 午餐"
        onClose={jest.fn()}
      />,
    );

    expect(getByText('高蛋白')).toBeTruthy();
    expect(getByText('低脂')).toBeTruthy();
    fireEvent.press(getByText('复制朋友圈文案'));

    await waitFor(() => {
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('亮点: 高蛋白 / 低脂'));
    });
  });

  it('labels user-corrected nutrition as manually confirmed', () => {
    const { getByText } = render(
      <DietShareCard record={{ ...record, source: 'user_corrected' }} dateLabel="7月11日 · 午餐" />,
    );
    expect(getByText('手动确认')).toBeTruthy();
  });

  it('captures exactly 1080x1440 and opens the system image share sheet', async () => {
    const onShareTerminal = jest.fn();
    const { getByText } = render(
      <DietShareSheet
        visible
        record={record}
        dateLabel="7月11日 · 午餐"
        onClose={jest.fn()}
        onShareTerminal={onShareTerminal}
      />,
    );

    fireEvent.press(getByText('分享图片'));

    await waitFor(() => {
      expect(mockCaptureRef).toHaveBeenCalledWith(
        expect.anything(),
        expect.objectContaining({
          format: 'png',
          quality: 1,
          width: 1080 / PixelRatio.get(),
          height: 1440 / PixelRatio.get(),
        }),
      );
      expect(mockShareAsync).toHaveBeenCalledWith(
        'file:///meal-share.png',
        expect.objectContaining({ mimeType: 'image/png', UTI: 'public.png' }),
      );
      expect(onShareTerminal).toHaveBeenCalledWith(expect.objectContaining({
        phase: 'completed',
        duration_ms: expect.any(Number),
        has_photo: false,
      }));
      expect(mockReleaseCapture).toHaveBeenCalledWith('file:///meal-share.png');
    });
  });

  it('offers platform-first image sharing with matching captions', async () => {
    const { getByText } = render(
      <DietShareSheet
        visible
        record={record}
        dateLabel="7月11日 · 午餐"
        onClose={jest.fn()}
      />,
    );

    expect(getByText('发微信/朋友圈')).toBeTruthy();
    expect(getByText('发小红书')).toBeTruthy();

    fireEvent.press(getByText('发小红书'));

    await waitFor(() => {
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('#小巴记录'));
      expect(mockCaptureRef).toHaveBeenCalledWith(
        expect.anything(),
        expect.objectContaining({
          format: 'png',
          quality: 1,
          width: 1080 / PixelRatio.get(),
          height: 1440 / PixelRatio.get(),
        }),
      );
      expect(mockShareAsync).toHaveBeenCalledWith(
        'file:///meal-share.png',
        expect.objectContaining({ dialogTitle: '发小红书' }),
      );
    });
  });

  it('uses native pixel units on Android and point units on iOS', () => {
    expect(dietShareCaptureDimensions('android', 3)).toEqual({ width: 1080, height: 1440 });
    expect(dietShareCaptureDimensions('ios', 3)).toEqual({ width: 360, height: 480 });
  });

  it('waits for the protected meal image before enabling capture', async () => {
    const { getByLabelText, getByTestId } = render(
      <DietShareSheet
        visible
        record={{ ...record, image_url: '/api/v1/upload/files/diet/1/meal.png' }}
        dateLabel="7月11日 · 午餐"
        imageSource={{ uri: 'https://health.executor.life/private-meal.png' }}
        onClose={jest.fn()}
      />,
    );

    fireEvent.press(getByLabelText('分享饮食图片'));
    expect(mockCaptureRef).not.toHaveBeenCalled();

    fireEvent(getByTestId('diet-share-image'), 'load');
    fireEvent.press(getByLabelText('分享饮食图片'));
    await waitFor(() => expect(mockCaptureRef).toHaveBeenCalled());
  });

  it('falls back to privacy-safe text sharing when image sharing is unavailable', async () => {
    const Sharing = require('expo-sharing');
    Sharing.isAvailableAsync.mockResolvedValueOnce(false);
    const onShareTerminal = jest.fn();
    const { getByText } = render(
      <DietShareSheet
        visible
        record={record}
        dateLabel="7月11日 · 午餐"
        onClose={jest.fn()}
        onShareTerminal={onShareTerminal}
      />,
    );

    fireEvent.press(getByText('分享图片'));

    await waitFor(() => {
      expect(Share.share).toHaveBeenCalledWith(expect.objectContaining({
        message: expect.stringContaining('鸡胸肉 200g、杂粮饭 1碗'),
      }));
      expect(onShareTerminal).toHaveBeenCalledWith(expect.objectContaining({
        phase: 'completed', has_photo: false,
      }));
    });
  });

  it('falls back to the metric card when a protected image never settles', async () => {
    jest.useFakeTimers();
    const { getByLabelText, getByText, queryByTestId } = render(
      <DietShareSheet
        visible
        record={{ ...record, image_url: '/api/v1/upload/files/diet/1/meal.png' }}
        dateLabel="7月11日 · 午餐"
        imageSource={{ uri: 'https://health.executor.life/private-meal.png' }}
        onClose={jest.fn()}
      />,
    );

    await act(async () => {
      jest.advanceTimersByTime(DIET_SHARE_IMAGE_TIMEOUT_MS);
    });
    expect(queryByTestId('diet-share-image')).toBeNull();
    expect(getByText('分享图片')).toBeTruthy();
    fireEvent.press(getByLabelText('分享饮食图片'));
    await waitFor(() => expect(mockCaptureRef).toHaveBeenCalled());
    jest.useRealTimers();
  });

  it('copies a Xiaohongshu-ready caption from the meal share sheet', async () => {
    const { getByText } = render(
      <DietShareSheet
        visible
        record={record}
        dateLabel="7月11日 · 午餐"
        onClose={jest.fn()}
      />,
    );

    fireEvent.press(getByText('复制小红书文案'));

    await waitFor(() => {
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('今天这餐打卡'));
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('蛋白质拉满的一餐'));
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('鸡胸肉 200g、杂粮饭 1碗'));
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('今日状态: 高蛋白 / 低脂'));
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('蛋白质 67g'));
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('亮点: 高蛋白 / 低脂'));
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('#饮食打卡'));
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('#小巴记录'));
    });
  });

  it('copies a WeChat Moments-ready caption without Xiaohongshu hashtags', async () => {
    const { getByText } = render(
      <DietShareSheet
        visible
        record={record}
        dateLabel="7月11日 · 午餐"
        onClose={jest.fn()}
      />,
    );

    fireEvent.press(getByText('复制朋友圈文案'));

    await waitFor(() => {
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('7月11日 · 午餐'));
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('鸡胸肉 200g、杂粮饭 1碗'));
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('今日状态: 高蛋白 / 低脂'));
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('560 kcal'));
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.not.stringContaining('#小巴记录'));
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.not.stringContaining('#饮食打卡'));
    });
  });
});
