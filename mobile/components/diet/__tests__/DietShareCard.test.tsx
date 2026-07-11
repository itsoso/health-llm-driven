import React from 'react';
import { fireEvent, render, waitFor } from '@testing-library/react-native';

const mockCaptureRef = jest.fn().mockResolvedValue('file:///meal-share.png');
const mockShareAsync = jest.fn().mockResolvedValue(undefined);

jest.mock('react-native-view-shot', () => ({
  captureRef: (...args: any[]) => mockCaptureRef(...args),
}));

jest.mock('expo-sharing', () => ({
  isAvailableAsync: jest.fn().mockResolvedValue(true),
  shareAsync: (...args: any[]) => mockShareAsync(...args),
}));

jest.mock('expo-haptics', () => ({
  notificationAsync: jest.fn(),
  NotificationFeedbackType: { Success: 'success' },
}));

import DietShareCard, { DietShareSheet } from '../DietShareCard';
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
  });

  it('renders a privacy-safe 3:4 meal story with real record data', () => {
    const { getByText, queryByText } = render(
      <DietShareCard record={record} dateLabel="7月11日 · 午餐" />,
    );

    expect(getByText('小巴 / 今日饮食')).toBeTruthy();
    expect(getByText('这一餐，有据可查')).toBeTruthy();
    expect(getByText('鸡胸肉 200g、杂粮饭 1碗')).toBeTruthy();
    expect(getByText('560')).toBeTruthy();
    expect(getByText('蛋白质')).toBeTruthy();
    expect(getByText('67g')).toBeTruthy();
    expect(getByText('营养表校准')).toBeTruthy();
    expect(queryByText('user_id')).toBeNull();
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
        expect.objectContaining({ format: 'png', quality: 1, width: 1080, height: 1440 }),
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
    });
  });
});
