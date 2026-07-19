import React from 'react';
import { fireEvent, render, waitFor } from '@testing-library/react-native';

import LocalDietScreen from '../LocalDietScreen';
import type { DietRepository } from '../../../services/dietRepository';

jest.mock('@expo/vector-icons', () => ({ Ionicons: () => null }));
jest.mock('expo-image-picker', () => ({
  requestMediaLibraryPermissionsAsync: jest.fn().mockResolvedValue({ granted: true }),
  launchImageLibraryAsync: jest.fn().mockResolvedValue({
    canceled: false,
    assets: [{ uri: 'file:///private/local-photo.jpg' }],
  }),
}));
jest.mock('../../../modules/local-health-kernel', () => ({
  recognizeLocalFoodPhoto: jest.fn().mockResolvedValue({
    decision: 'candidate',
    candidates: [{
      canonicalFoodId: 'food.staple.rice.white',
      displayName: '白米饭',
      category: 'staple',
      score: 0.7,
      evidence: 'whole_image',
    }],
    manualConfirmationRequired: true,
    canAutoSave: false,
    estimatesPortion: false,
  }),
}));

function repository(): jest.Mocked<DietRepository> {
  return {
    getDailyDiet: jest.fn().mockResolvedValue({
      record_date: '2026-07-19',
      total_calories: 0,
      total_protein: 0,
      total_carbs: 0,
      total_fat: 0,
      total_fiber: 0,
      meals_count: 0,
      meals: [],
    }),
    getDietStats: jest.fn(),
    getFrequentFoods: jest.fn(),
    createDietRecord: jest.fn().mockResolvedValue({ id: 1 }),
    updateDietRecord: jest.fn(),
    deleteDietRecord: jest.fn(),
  } as unknown as jest.Mocked<DietRepository>;
}

describe('LocalDietScreen', () => {
  it('creates a local confirmation draft and persists only after confirmation', async () => {
    const localRepository = repository();
    const screen = render(<LocalDietScreen repository={localRepository} onBack={jest.fn()} />);

    await waitFor(() => expect(localRepository.getDailyDiet).toHaveBeenCalled());
    fireEvent.changeText(screen.getByPlaceholderText('输入吃了什么和大致份量'), '午饭半碗米饭两个鸡蛋');
    fireEvent.press(screen.getByText('生成本地草稿'));

    expect(screen.getByText('待你确认')).toBeTruthy();
    expect(localRepository.createDietRecord).not.toHaveBeenCalled();

    fireEvent.press(screen.getByText('确认记录'));
    await waitFor(() => expect(localRepository.createDietRecord).toHaveBeenCalledWith(
      expect.objectContaining({
        meal_type: 'lunch',
        food_items: '半碗米饭、两个鸡蛋',
        source: 'local_deterministic_usda',
      }),
    ));
  });

  it('shows local photo candidates but never creates a record before manual confirmation', async () => {
    const localRepository = repository();
    const screen = render(<LocalDietScreen repository={localRepository} onBack={jest.fn()} />);

    await waitFor(() => expect(localRepository.getDailyDiet).toHaveBeenCalled());
    fireEvent.press(screen.getByText('从照片识别'));

    await waitFor(() => expect(screen.getByText('可能是什么')).toBeTruthy());
    expect(screen.getByText('白米饭')).toBeTruthy();
    expect(screen.getByText('只给候选，不会估算份量或自动保存')).toBeTruthy();
    expect(localRepository.createDietRecord).not.toHaveBeenCalled();

    fireEvent.press(screen.getByText('白米饭'));
    expect(screen.getByDisplayValue('白米饭')).toBeTruthy();
    expect(localRepository.createDietRecord).not.toHaveBeenCalled();
  });

  it('shows unknown nutrition as unknown instead of zero', async () => {
    const localRepository = repository();
    localRepository.getDailyDiet.mockResolvedValue({
      record_date: '2026-07-19',
      total_calories: 0,
      total_protein: 0,
      total_carbs: 0,
      total_fat: 0,
      total_fiber: 0,
      meals_count: 1,
      meals: [{
        id: 1,
        user_id: 0,
        record_date: '2026-07-19',
        meal_type: 'lunch',
        food_items: '家常菜',
        calories: null,
        protein: null,
        carbs: null,
        fat: null,
        fiber: null,
        alcohol_units: null,
        source: 'local_user_confirmed',
        notes: null,
        image_url: null,
        health_tips: null,
      }],
    });

    const screen = render(<LocalDietScreen repository={localRepository} onBack={jest.fn()} />);

    await waitFor(() => expect(screen.getAllByText('营养未知')).toHaveLength(1));
    expect(screen.getAllByText('—')).toHaveLength(4);
  });
});
