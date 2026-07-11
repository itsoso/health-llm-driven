/* eslint-disable import/first, @typescript-eslint/no-require-imports */
import React from 'react';
import { Alert } from 'react-native';
import { fireEvent, render, waitFor } from '@testing-library/react-native';
import * as ImagePicker from 'expo-image-picker';

const mockRouteParams: Record<string, string> = { capture: 'photo' };
const mockMealForm = jest.fn();
const mockEstimate = jest.fn();
const mockRouterPush = jest.fn();
const mockPushChatWithContext = jest.fn();
const mockEmitClientEvent = jest.fn().mockResolvedValue(undefined);
const mockDailyMeals: any[] = [];

jest.mock('expo-router', () => ({
  useRouter: () => ({ back: jest.fn(), push: (...args: any[]) => mockRouterPush(...args) }),
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

jest.mock('react-native-view-shot', () => ({ captureRef: jest.fn() }));
jest.mock('expo-sharing', () => ({ isAvailableAsync: jest.fn(), shareAsync: jest.fn() }));

jest.mock('react-native-gesture-handler/ReanimatedSwipeable', () => {
  const React = require('react');
  const { View } = require('react-native');
  const MockSwipeable = ({ children }: any) => <View>{children}</View>;
  MockSwipeable.displayName = 'MockSwipeable';
  return MockSwipeable;
});

jest.mock('../../hooks/useDiet', () => ({
  useDailyDiet: () => ({
    data: { meals: mockDailyMeals, meals_count: mockDailyMeals.length, total_calories: 0, total_protein: 0, total_carbs: 0, total_fat: 0 },
    refetch: jest.fn(),
    isRefetching: false,
  }),
}));

jest.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({ token: 'test-token' }),
}));

jest.mock('../../services/clientEvents', () => ({
  emitClientEvent: (...args: any[]) => mockEmitClientEvent(...args),
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
  discardDietPhotoDraft: jest.fn().mockResolvedValue(undefined),
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
  pushChatWithContext: (...args: any[]) => mockPushChatWithContext(...args),
}));

import DietScreen from '../diet';

describe('DietScreen capture deeplink', () => {
  beforeEach(() => {
    mockMealForm.mockClear();
    mockEstimate.mockClear();
    jest.clearAllMocks();
    Object.keys(mockRouteParams).forEach((key) => { delete mockRouteParams[key]; });
    mockDailyMeals.splice(0, mockDailyMeals.length);
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
    expect(mockEmitClientEvent).toHaveBeenCalledWith(
      'diet_photo_recognition_terminal',
      expect.objectContaining({
        phase: 'completed',
        duration_ms: expect.any(Number),
        food_count: 1,
      }),
    );
  });

  it('shows recognition progress while a meal photo is being analyzed', async () => {
    const dietService = require('../../services/diet');
    mockRouteParams.capture = 'photo';
    let resolveRecognition: (value: any) => void = () => {};
    const recognitionPromise = new Promise((resolve) => {
      resolveRecognition = resolve;
    });
    (ImagePicker.launchCameraAsync as jest.Mock).mockResolvedValueOnce({
      canceled: false,
      assets: [{ base64: 'photo-base64' }],
    });
    dietService.recognizeFood.mockReturnValueOnce(recognitionPromise);

    const { getByText } = render(<DietScreen />);

    await waitFor(() => {
      expect(getByText('正在识别餐食')).toBeTruthy();
    });

    resolveRecognition({
      success: true,
      foods: [{ name: '煎牛肉能量碗', quantity: null }],
      meal_description: '煎牛肉能量碗 + 姜黄鲜柠维C茶',
      total_calories: 770,
      total_protein: 30,
      total_carbs: 70,
      total_fat: 17,
      error: null,
    });

    await waitFor(() => {
      expect(getByText('待确认饮食')).toBeTruthy();
    });
  });

  it('shows explainable per-food sources and flags uncertain photo portions', async () => {
    const dietService = require('../../services/diet');
    mockRouteParams.capture = 'photo';
    (ImagePicker.launchCameraAsync as jest.Mock).mockResolvedValueOnce({
      canceled: false,
      assets: [{ base64: 'photo-base64' }],
    });
    dietService.recognizeFood.mockResolvedValueOnce({
      success: true,
      foods: [
        {
          name: '鸡胸肉', quantity: '200g', quantity_grams: 200,
          calories: 330, protein: 62, carbs: 0, fat: 7.2, fiber: 0,
          confidence: 0.91, food_id: 'cfc:chicken_breast',
          source: 'china_food_composition', nutrition_basis: 'food_table',
        },
        {
          name: '杂粮饭', quantity: '1碗', calories: 230, protein: 5,
          carbs: 48, fat: 2, fiber: 3, confidence: 0.62,
          source: 'ai_estimate', nutrition_basis: 'vision_estimate',
        },
      ],
      meal_description: '鸡胸肉 200g、杂粮饭 1碗',
      total_calories: 560,
      total_protein: 67,
      total_carbs: 48,
      total_fat: 9.2,
      total_fiber: 3,
      error: null,
    });

    const { getByText, getAllByText } = render(<DietScreen />);

    await waitFor(() => {
      expect(getByText('识别明细')).toBeTruthy();
    });
    expect(getByText('鸡胸肉')).toBeTruthy();
    expect(getByText('200g · 330 kcal')).toBeTruthy();
    expect(getByText('营养表校准')).toBeTruthy();
    expect(getByText('置信 91%')).toBeTruthy();
    expect(getByText('杂粮饭')).toBeTruthy();
    expect(getByText('1碗 · 230 kcal')).toBeTruthy();
    expect(getByText('视觉估算')).toBeTruthy();
    expect(getByText('置信 62%')).toBeTruthy();
    expect(getAllByText('请核对份量').length).toBeGreaterThan(0);
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

  it('does not submit the same quick draft twice while saving', async () => {
    const dietService = require('../../services/diet');
    let resolveSave: (value: any) => void = () => {};
    dietService.createDietRecord.mockReturnValueOnce(new Promise((resolve) => {
      resolveSave = resolve;
    }));
    const promptSpy = jest.spyOn(Alert, 'prompt').mockImplementationOnce((_title, _message, callback) => {
      if (typeof callback === 'function') callback('鸡胸肉 200g + 糙米饭一碗');
    });

    const { getByTestId, getByText } = render(<DietScreen />);
    fireEvent.press(getByTestId('diet-fab-text'));
    await waitFor(() => {
      expect(getByText('待确认饮食')).toBeTruthy();
    });

    const confirmButton = getByText('确认记录');
    fireEvent.press(confirmButton);
    fireEvent.press(confirmButton);

    expect(dietService.createDietRecord).toHaveBeenCalledTimes(1);
    expect(getByText('保存中')).toBeTruthy();
    resolveSave({ id: 88 });
    await waitFor(() => {
      expect(mockEstimate).toHaveBeenCalledWith(88, { kind: 'text', description: '鸡胸肉 200g + 糙米饭一碗' });
    });
    promptSpy.mockRestore();
  });

  it('returns to chat with diet context after confirming a chat-originated meal photo draft', async () => {
    const dietService = require('../../services/diet');
    mockRouteParams.capture = 'photo';
    mockRouteParams.return_to = 'chat';
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
      photo_draft_token: 'photo-draft-88',
      error: null,
    });
    dietService.createDietRecord.mockResolvedValueOnce({ id: 88 });

    const { getByText } = render(<DietScreen />);
    await waitFor(() => {
      expect(getByText('待确认饮食')).toBeTruthy();
    });

    fireEvent.press(getByText('确认记录'));

    await waitFor(() => {
      expect(dietService.createDietRecord).toHaveBeenCalledWith(expect.objectContaining({
        source: 'ai_estimate',
        image_base64: undefined,
        image_type: 'jpeg',
        photo_draft_token: 'photo-draft-88',
        idempotency_key: 'diet-photo:photo-draft-88',
        ai_recognized: 1,
        ai_raw_result: expect.objectContaining({
          meal_description: '煎牛肉能量碗 + 姜黄鲜柠维C茶',
        }),
      }));
      expect(mockPushChatWithContext).toHaveBeenCalledWith(
        expect.objectContaining({ push: expect.any(Function) }),
        expect.objectContaining({
          prompt: expect.stringContaining('刚记录了一餐'),
          badge: expect.stringContaining('刚记录饮食'),
          context: expect.objectContaining({
            from: 'diet/quick_capture',
            created_id: 88,
            record: expect.objectContaining({
              food_items: '煎牛肉能量碗 + 姜黄鲜柠维C茶',
              calories: 770,
              protein: 30,
            }),
          }),
        }),
      );
      expect(mockEmitClientEvent).toHaveBeenCalledWith(
        'diet_photo_confirmation_terminal',
        expect.objectContaining({ phase: 'completed', verified: true }),
      );
    });
  });

  it('keeps the photo draft open when confirmation does not return a persisted record id', async () => {
    const dietService = require('../../services/diet');
    mockRouteParams.capture = 'photo';
    mockRouteParams.return_to = 'chat';
    (ImagePicker.launchCameraAsync as jest.Mock).mockResolvedValueOnce({
      canceled: false,
      assets: [{ base64: 'photo-base64' }],
    });
    dietService.recognizeFood.mockResolvedValueOnce({
      success: true,
      foods: [{ name: '牛肉面', quantity: null }],
      meal_description: '牛肉面',
      total_calories: 650,
      total_protein: 28,
      total_carbs: 80,
      total_fat: 18,
      error: null,
    });
    dietService.createDietRecord.mockResolvedValueOnce({ ok: true });
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation(() => {});

    const { getByText } = render(<DietScreen />);
    await waitFor(() => {
      expect(getByText('待确认饮食')).toBeTruthy();
    });

    fireEvent.press(getByText('确认记录'));

    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith('保存失败', '请稍后再试');
    });
    expect(getByText('待确认饮食')).toBeTruthy();
    expect(mockPushChatWithContext).not.toHaveBeenCalled();
    alertSpy.mockRestore();
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

  it('rejects medication-looking diet draft deeplinks before opening the meal form', async () => {
    mockRouteParams.draft = 'diet';
    mockRouteParams.meal_type = 'lunch';
    mockRouteParams.food_items = '替普瑞酮胶囊（施维舒）';

    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation(() => {});
    render(<DietScreen />);

    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith(
        '这不是饮食记录',
        '这条内容更像用药或补剂,请从用药/补剂入口确认。',
      );
    });
    expect(mockMealForm).not.toHaveBeenCalled();
    const dietService = require('../../services/diet');
    expect(dietService.createDietRecord).not.toHaveBeenCalled();
    expect(ImagePicker.requestCameraPermissionsAsync).not.toHaveBeenCalled();
    alertSpy.mockRestore();
  });

  it('opens a premium share preview from a confirmed meal row', () => {
    mockDailyMeals.push({
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
    });

    const { getByLabelText, getByText } = render(<DietScreen />);
    fireEvent.press(getByLabelText('分享午餐饮食'));

    expect(getByText('分享这一餐')).toBeTruthy();
    expect(getByText('高清 3:4 图片 · 微信与小红书')).toBeTruthy();
    expect(getByText('这一餐，有据可查')).toBeTruthy();
  });
});
