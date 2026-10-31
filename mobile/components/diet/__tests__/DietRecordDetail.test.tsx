import React from 'react';
import { fireEvent, render, within } from '@testing-library/react-native';
import { Modal } from 'react-native';
import DietRecordDetail from '../DietRecordDetail';
import type { DietRecord } from '../../../services/diet';

jest.mock('../../../services/api', () => ({ __esModule: true, default: {}, BASE_URL: 'https://health.example/api/v1' }));
jest.mock('expo-image', () => {
  const ReactModule = jest.requireActual('react');
  const { View } = jest.requireActual('react-native');
  return { Image: (props: object) => ReactModule.createElement(View, props) };
});

const record: DietRecord = {
  id: 88, user_id: 1, record_date: '2026-08-01', meal_type: 'lunch',
  food_items: '一份完整的食物描述，包含每种食物和实际吃下的份量。'.repeat(8),
  calories: 321.678, protein: 20.5, carbs: 0, fat: null, fiber: 3.14159,
  alcohol_units: null, image_url: null, notes: '本次记录的备注',
  health_tips: '不应自动重新展示的历史建议', source: 'photo',
};

function setup(overrides: Partial<DietRecord> = {}) {
  const callbacks = {
    onClose: jest.fn(), onEdit: jest.fn(), onDelete: jest.fn(), onShare: jest.fn(), onReview: jest.fn(),
  };
  const view = render(<DietRecordDetail record={{ ...record, ...overrides }} authToken="test-token" {...callbacks} />);
  return { ...view, ...callbacks };
}

describe('DietRecordDetail', () => {
  it('shows the full persisted meal, date and notes without promoting old advice', () => {
    const view = setup();
    expect(view.getByText('饮食详情')).toBeTruthy();
    expect(view.getByText('2026-08-01 · 午餐')).toBeTruthy();
    expect(view.getByText(record.food_items).props.numberOfLines).toBeUndefined();
    expect(view.getByText(record.notes!)).toBeTruthy();
    expect(view.queryByText(record.health_tips!)).toBeNull();
    expect(view.onReview).not.toHaveBeenCalled();
  });

  it('formats nutrition for display and keeps zero distinct from missing values', () => {
    const view = setup();
    expect(within(view.getByTestId('diet-detail-calories')).getByText('321.68')).toBeTruthy();
    expect(within(view.getByTestId('diet-detail-protein')).getByText('20.5')).toBeTruthy();
    expect(within(view.getByTestId('diet-detail-carbs')).getByText('0')).toBeTruthy();
    expect(within(view.getByTestId('diet-detail-fat')).getByText('未记录')).toBeTruthy();
    expect(within(view.getByTestId('diet-detail-fiber')).getByText('3.14')).toBeTruthy();
    expect(view.getByText('照片识别的营养为估算值，可修改食物或份量进行核对。')).toBeTruthy();
  });

  it('does not display invalid nutrition values', () => {
    const view = setup({ calories: NaN, protein: Infinity, carbs: -1 });
    expect(within(view.getByTestId('diet-detail-calories')).getByText('未记录')).toBeTruthy();
    expect(within(view.getByTestId('diet-detail-protein')).getByText('未记录')).toBeTruthy();
    expect(within(view.getByTestId('diet-detail-carbs')).getByText('未记录')).toBeTruthy();
  });

  it('shows all ordered photos and authenticates only the API origin', () => {
    const view = setup({ photo_assets: [
      { id: 'b', url: '/api/v1/upload/files/diet/b.jpg', ordinal: 2, captured_at: null, origin: 'camera' },
      { id: 'a', url: 'https://health.example/api/v1/upload/files/diet/a.jpg', ordinal: 1, captured_at: null, origin: 'camera' },
      { id: 'c', url: 'https://other.example/api/v1/upload/files/diet/c.jpg', ordinal: 3, captured_at: null, origin: 'camera' },
    ] });
    expect(view.getByTestId('diet-detail-photo-0').props.source).toEqual({
      uri: 'https://health.example/api/v1/upload/files/diet/a.jpg', headers: { Authorization: 'Bearer test-token' },
    });
    expect(view.getByTestId('diet-detail-photo-1').props.source).toEqual({
      uri: 'https://health.example/api/v1/upload/files/diet/b.jpg', headers: { Authorization: 'Bearer test-token' },
    });
    expect(view.queryByTestId('diet-detail-photo-2')).toBeNull();
    expect(view.getByText('照片暂不可用')).toBeTruthy();
  });

  it('reports image failures and lets the user retry without losing meal actions', () => {
    const view = setup({ image_url: '/api/v1/upload/files/diet/a.jpg' });
    fireEvent(view.getByTestId('diet-detail-photo-0'), 'error');
    expect(view.getByText('照片加载失败')).toBeTruthy();
    fireEvent.press(view.getByRole('button', { name: '重新加载照片 1' }));
    expect(view.queryByText('照片加载失败')).toBeNull();
    expect(view.getByRole('button', { name: '修改食物或份量' })).toBeTruthy();
  });

  it('routes explicit actions independently and supports system dismissal', () => {
    const view = setup();
    fireEvent.press(view.getByRole('button', { name: '修改食物或份量' }));
    fireEvent.press(view.getByRole('button', { name: '分享这餐' }));
    fireEvent.press(view.getByRole('button', { name: '复盘当天饮食' }));
    fireEvent.press(view.getByRole('button', { name: '删除这条记录' }));
    expect(view.onEdit).toHaveBeenCalledTimes(1);
    expect(view.onShare).toHaveBeenCalledTimes(1);
    expect(view.onReview).toHaveBeenCalledTimes(1);
    expect(view.onDelete).toHaveBeenCalledTimes(1);
    expect(view.onClose).not.toHaveBeenCalled();
    fireEvent.press(view.getByRole('button', { name: '关闭饮食详情' }));
    fireEvent(view.UNSAFE_getByType(Modal), 'requestClose');
    expect(view.onClose).toHaveBeenCalledTimes(2);
  });
});
