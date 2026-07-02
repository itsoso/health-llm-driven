/* eslint-disable import/first, @typescript-eslint/no-require-imports */
import React from 'react';
import { Alert } from 'react-native';
import { fireEvent, render, waitFor } from '@testing-library/react-native';
import * as ImagePicker from 'expo-image-picker';

const mockRouteParams: Record<string, string> = { capture: 'photo' };
const mockMealForm = jest.fn();
const mockEstimate = jest.fn();

jest.mock('expo-router', () => ({
  useRouter: () => ({ back: jest.fn() }),
  useLocalSearchParams: () => mockRouteParams,
}));

jest.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: jest.fn() }),
  useQuery: () => ({ data: [], isLoading: false, isError: false, isRefetching: false }),
}));

jest.mock('expo-haptics', () => ({
  impactAsync: jest.fn(),
  notificationAsync: jest.fn(),
  ImpactFeedbackStyle: { Light: 'light', Medium: 'medium' },
  NotificationFeedbackType: { Success: 'success' },
}));

jest.mock('expo-image-picker', () => ({
  requestCameraPermissionsAsync: jest.fn().mockResolvedValue({ granted: true }),
  launchCameraAsync: jest.fn().mockResolvedValue({ canceled: true, assets: [] }),
}));

jest.mock('react-native-gesture-handler/ReanimatedSwipeable', () => {
  const React = require('react');
  const { View } = require('react-native');
  const MockSwipeable = ({ children }: any) => <View>{children}</View>;
  MockSwipeable.displayName = 'MockSwipeable';
  return MockSwipeable;
});

jest.mock('../../hooks/useDiet', () => ({
  useDailyDiet: () => ({
    data: { meals: [], meals_count: 0, total_calories: 0, total_protein: 0, total_carbs: 0, total_fat: 0 },
    refetch: jest.fn(),
    isRefetching: false,
  }),
}));

jest.mock('../../hooks/useDietEstimate', () => ({
  useDietEstimate: () => ({
    estimate: mockEstimate,
    pendingIds: new Set(),
    failedIds: new Set(),
  }),
}));

jest.mock('../../services/diet', () => ({
  createDietRecord: jest.fn(),
  updateDietRecord: jest.fn(),
  deleteDietRecord: jest.fn(),
  estimateNutrition: jest.fn(),
  recognizeFood: jest.fn(),
  getFrequentFoods: jest.fn().mockResolvedValue([]),
}));

jest.mock('../../hooks/useToast', () => ({
  useToast: () => ({ show: jest.fn(), showUndoable: jest.fn() }),
}));

jest.mock('../../hooks/useTheme', () => ({
  useTheme: () => ({
    c: {
      bgPrimary: '#fff',
      bgCard: '#fff',
      fill: '#f5f5f5',
      labelPrimary: '#111',
      labelSecondary: '#555',
      labelTertiary: '#999',
      labelQuaternary: '#bbb',
      separator: '#eee',
      brand: '#0A8F8F',
      brandLight: '#E6F7F7',
      red: '#DC2626',
    },
  }),
}));

jest.mock('../../components/diet/MealForm', () => {
  const React = require('react');
  const { View } = require('react-native');
  const MockMealForm = (props: any) => {
    mockMealForm(props);
    return <View testID="meal-form" />;
  };
  MockMealForm.displayName = 'MockMealForm';
  return MockMealForm;
});

jest.mock('../../components/diet/DietFAB', () => {
  const React = require('react');
  const { Text, TouchableOpacity, View } = require('react-native');
  const MockDietFAB = ({ onPhoto, onText, onVoice }: any) => (
    <View>
      <TouchableOpacity testID="diet-fab-photo" onPress={onPhoto}><Text>拍照</Text></TouchableOpacity>
      <TouchableOpacity testID="diet-fab-text" onPress={onText}><Text>文字</Text></TouchableOpacity>
      <TouchableOpacity testID="diet-fab-voice" onPress={onVoice}><Text>语音</Text></TouchableOpacity>
    </View>
  );
  MockDietFAB.displayName = 'MockDietFAB';
  return MockDietFAB;
});

jest.mock('../../utils/agentContext', () => ({
  createDietAgentContext: jest.fn(() => ({})),
  pushChatWithContext: jest.fn(),
}));

import DietScreen from '../diet';

describe('DietScreen capture deeplink', () => {
  beforeEach(() => {
    mockMealForm.mockClear();
    mockEstimate.mockClear();
    jest.clearAllMocks();
    Object.keys(mockRouteParams).forEach((key) => { delete mockRouteParams[key]; });
  });

  it('starts photo capture when opened with capture=photo', async () => {
    mockRouteParams.capture = 'photo';
    render(<DietScreen />);

    await waitFor(() => {
      expect(ImagePicker.requestCameraPermissionsAsync).toHaveBeenCalled();
    });
  });

  it('turns photo capture into a lightweight confirm card without auto-saving', async () => {
    const dietService = require('../../services/diet');
    mockRouteParams.capture = 'photo';
    (ImagePicker.launchCameraAsync as jest.Mock).mockResolvedValueOnce({
      canceled: false,
      assets: [{ base64: 'photo-base64' }],
    });
    dietService.recognizeFood.mockResolvedValueOnce({
      success: true,
      foods: [{ name: '煎牛肉能量碗', quantity: null }],
      meal_description: '煎牛肉能量碗 + 姜黄鲜柠维C茶',
      total_calories: 770,
      total_protein: 30,
      total_carbs: 70,
      total_fat: 17,
      error: null,
    });

    const { getByText } = render(<DietScreen />);

    await waitFor(() => {
      expect(dietService.recognizeFood).toHaveBeenCalledWith('photo-base64');
    });
    await waitFor(() => {
      expect(getByText('待确认饮食')).toBeTruthy();
    });
    expect(getByText('煎牛肉能量碗 + 姜黄鲜柠维C茶')).toBeTruthy();
    expect(getByText('770 kcal · 蛋白 30g')).toBeTruthy();
    expect(mockMealForm).not.toHaveBeenCalled();
    expect(dietService.createDietRecord).not.toHaveBeenCalled();
  });

  it('turns text entry into a lightweight confirm card without auto-saving', async () => {
    const dietService = require('../../services/diet');
    const promptSpy = jest.spyOn(Alert, 'prompt').mockImplementationOnce((_title, _message, callback) => {
      if (typeof callback === 'function') callback('鸡胸肉 200g + 糙米饭一碗');
    });

    const { getByTestId, getByText } = render(<DietScreen />);
    fireEvent.press(getByTestId('diet-fab-text'));

    await waitFor(() => {
      expect(getByText('待确认饮食')).toBeTruthy();
    });
    expect(getByText('鸡胸肉 200g + 糙米饭一碗')).toBeTruthy();
    expect(mockMealForm).not.toHaveBeenCalled();
    expect(dietService.createDietRecord).not.toHaveBeenCalled();
    promptSpy.mockRestore();
  });

  it('turns voice text into a lightweight confirm card without auto-saving', async () => {
    const dietService = require('../../services/diet');
    const promptSpy = jest.spyOn(Alert, 'prompt').mockImplementationOnce((_title, _message, callback) => {
      if (typeof callback === 'function') callback('晚饭吃了鸡胸肉和一碗米饭');
    });

    const { getByTestId, getByText } = render(<DietScreen />);
    fireEvent.press(getByTestId('diet-fab-voice'));

    await waitFor(() => {
      expect(getByText('待确认饮食')).toBeTruthy();
    });
    expect(getByText('晚饭吃了鸡胸肉和一碗米饭')).toBeTruthy();
    expect(mockMealForm).not.toHaveBeenCalled();
    expect(dietService.createDietRecord).not.toHaveBeenCalled();
    promptSpy.mockRestore();
  });

  it('saves a lightweight diet draft from the confirm card', async () => {
    const dietService = require('../../services/diet');
    dietService.createDietRecord.mockResolvedValueOnce({ id: 88 });
    const promptSpy = jest.spyOn(Alert, 'prompt').mockImplementationOnce((_title, _message, callback) => {
      if (typeof callback === 'function') callback('鸡胸肉 200g + 糙米饭一碗');
    });

    const { getByTestId, getByText } = render(<DietScreen />);
    fireEvent.press(getByTestId('diet-fab-text'));
    await waitFor(() => {
      expect(getByText('待确认饮食')).toBeTruthy();
    });

    fireEvent.press(getByText('确认记录'));

    await waitFor(() => {
      expect(dietService.createDietRecord).toHaveBeenCalledWith(expect.objectContaining({
        food_items: '鸡胸肉 200g + 糙米饭一碗',
        record_date: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
      }));
    });
    expect(mockEstimate).toHaveBeenCalledWith(88, { kind: 'text', description: '鸡胸肉 200g + 糙米饭一碗' });
    promptSpy.mockRestore();
  });

  it('opens the full meal form only when users choose to revise a draft', async () => {
    const promptSpy = jest.spyOn(Alert, 'prompt').mockImplementationOnce((_title, _message, callback) => {
      if (typeof callback === 'function') callback('鸡胸肉 200g + 糙米饭一碗');
    });

    const { getByTestId, getByText } = render(<DietScreen />);
    fireEvent.press(getByTestId('diet-fab-text'));
    await waitFor(() => {
      expect(getByText('待确认饮食')).toBeTruthy();
    });

    fireEvent.press(getByText('修正'));

    await waitFor(() => {
      expect(mockMealForm).toHaveBeenCalledWith(expect.objectContaining({
        initialDescription: '鸡胸肉 200g + 糙米饭一碗',
      }));
    });
    promptSpy.mockRestore();
  });

  it('opens a prefilled meal form from a diet draft deeplink without auto-saving', async () => {
    mockRouteParams.draft = 'diet';
    mockRouteParams.meal_type = 'lunch';
    mockRouteParams.food_items = '煎牛肉能量碗和姜黄鲜柠维C茶';
    mockRouteParams.calories = '770';
    mockRouteParams.protein = '30';
    mockRouteParams.carbs = '70';
    mockRouteParams.fat = '17';

    render(<DietScreen />);

    await waitFor(() => {
      expect(mockMealForm).toHaveBeenCalledWith(expect.objectContaining({
        initialMealType: 'lunch',
        initialDescription: '煎牛肉能量碗和姜黄鲜柠维C茶',
        initialCalories: 770,
        initialProtein: 30,
        initialCarbs: 70,
        initialFat: 17,
      }));
    });
    const dietService = require('../../services/diet');
    expect(dietService.createDietRecord).not.toHaveBeenCalled();
    expect(ImagePicker.requestCameraPermissionsAsync).not.toHaveBeenCalled();
  });
});
