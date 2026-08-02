/* eslint-disable import/first, @typescript-eslint/no-require-imports */
import React from 'react';
import { Alert, Share } from 'react-native';
import { act, fireEvent, render, waitFor } from '@testing-library/react-native';
import * as ImagePicker from 'expo-image-picker';

const mockRouteParams: Record<string, string> = { capture: 'photo' };
const mockMealForm = jest.fn();
const mockEstimate = jest.fn();
const mockRouterPush = jest.fn();
const mockPushChatWithContext = jest.fn();
const mockDietShareComposer = jest.fn();
const mockMeals: any[] = [];
const mockToastShow = jest.fn();

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

jest.mock('react-native-gesture-handler/ReanimatedSwipeable', () => {
  const React = require('react');
  const { View } = require('react-native');
  const MockSwipeable = ({ children }: any) => <View>{children}</View>;
  MockSwipeable.displayName = 'MockSwipeable';
  return MockSwipeable;
});

jest.mock('../../hooks/useDiet', () => ({
  useDailyDiet: () => ({
    data: { meals: mockMeals, meals_count: mockMeals.length, total_calories: 0, total_protein: 0, total_carbs: 0, total_fat: 0 },
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
  dietRecordImageUrls: (record: any) => record.image_url ? [record.image_url] : [],
}));

jest.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({ token: 'diet-auth-token', user: { id: 1 }, isLoading: false }),
}));

jest.mock('../../hooks/useToast', () => ({
  useToast: () => ({ show: mockToastShow, showUndoable: jest.fn() }),
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

jest.mock('../../components/diet/DietShareComposer', () => {
  const React = require('react');
  const { View } = require('react-native');
  return {
    DietShareComposer: (props: any) => {
      mockDietShareComposer(props);
      return <View testID="mock-diet-share-composer" />;
    },
  };
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
    mockMeals.splice(0);
    Object.keys(mockRouteParams).forEach((key) => { delete mockRouteParams[key]; });
  });

  it('opens the same authenticated photo composer and shares the canonical diet caption', async () => {
    mockRouteParams.share_record_id = '88';
    mockMeals.push({
      id: 88,
      user_id: 1,
      record_date: '2026-08-01',
      meal_type: 'lunch',
      food_items: '番茄鸡蛋面',
      source: 'photo',
      calories: 520,
      protein: 24,
      carbs: 64,
      fat: 17,
      fiber: 4,
      image_url: '/api/v1/upload/files/diet/1/meal.jpg',
      health_tips: '下一餐补蔬菜',
      ai_confidence: 0.88,
    });
    const shareSpy = jest.spyOn(Share, 'share').mockResolvedValue({ action: Share.sharedAction });

    const view = render(<DietScreen />);

    await waitFor(() => expect(view.getByTestId('mock-diet-share-composer')).toBeTruthy());
    const props = mockDietShareComposer.mock.lastCall?.[0];
    expect(props).toEqual(expect.objectContaining({
      record: expect.objectContaining({ id: 88 }),
      photoSource: {
        uri: 'https://health.executor.life/api/v1/upload/files/diet/1/meal.jpg',
        headers: { Authorization: 'Bearer diet-auth-token' },
      },
    }));

    await act(async () => props.onShareText());
    expect(shareSpy).toHaveBeenCalledWith(expect.objectContaining({
      title: '分享饮食记录',
      message: expect.stringContaining('小巴饮食卡｜'),
    }));
    shareSpy.mockRestore();
  });

  it('falls back to canonical text sharing with feedback when a record has no accessible photo', async () => {
    mockRouteParams.share_record_id = '89';
    mockMeals.push({
      id: 89,
      user_id: 1,
      record_date: '2026-08-01',
      meal_type: 'dinner',
      food_items: '清炒时蔬和米饭',
      source: 'manual',
      calories: 430,
      protein: 12,
      carbs: 72,
      fat: 10,
      fiber: 7,
      image_url: null,
    });
    const pendingShare = new Promise<Awaited<ReturnType<typeof Share.share>>>(() => {});
    const shareSpy = jest.spyOn(Share, 'share').mockReturnValue(pendingShare);

    const view = render(<DietScreen />);

    await waitFor(() => expect(view.getByTestId('diet-share-text-fallback')).toBeTruthy());
    expect(view.getByText('这条记录没有可用照片')).toBeTruthy();
    expect(shareSpy).not.toHaveBeenCalled();
    const shareButton = view.getByRole('button', { name: '分享饮食正文' });
    fireEvent.press(shareButton);
    fireEvent.press(shareButton);
    await waitFor(() => expect(shareSpy).toHaveBeenCalledWith(expect.objectContaining({
      title: '分享饮食记录',
      message: expect.stringContaining('清炒时蔬和米饭'),
    })));
    expect(shareSpy).toHaveBeenCalledTimes(1);
    expect(view.getByRole('button', { name: '分享饮食正文' })).toBeDisabled();
    expect(view.getByText('分享中…')).toBeTruthy();
    expect(view.queryByTestId('mock-diet-share-composer')).toBeNull();
    shareSpy.mockRestore();
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
      error: null,
    });
    dietService.createDietRecord.mockResolvedValueOnce({ id: 88 });

    const { getByText, getByLabelText } = render(<DietScreen />);
    await waitFor(() => {
      expect(getByText('待确认饮食')).toBeTruthy();
    });

    fireEvent.press(getByLabelText('核对后确认饮食'));

    await waitFor(() => {
      expect(dietService.createDietRecord).toHaveBeenCalledWith(expect.objectContaining({
        source: 'ai_estimate',
        image_base64: 'photo-base64',
        image_type: 'jpeg',
        ai_recognized: 1,
        ai_raw_result: expect.objectContaining({
          meal_description: '煎牛肉能量碗 + 姜黄鲜柠维C茶',
        }),
      }));
      expect(mockPushChatWithContext).toHaveBeenCalledWith(
        expect.objectContaining({ push: expect.any(Function) }),
        expect.objectContaining({
          prompt: expect.stringContaining('请先查询今天数据库里的所有饮食记录'),
          badge: expect.stringContaining('刚记录饮食'),
          context: expect.objectContaining({
            from: 'diet/post_confirm',
            must_query_database: true,
            verify_record_id: 88,
            created_id: 88,
            database_verification: expect.objectContaining({
              required: true,
              verify_record_id: 88,
              totals_source: 'database',
            }),
            record: expect.objectContaining({
              food_items: '煎牛肉能量碗 + 姜黄鲜柠维C茶',
              calories: 770,
              protein: 30,
            }),
          }),
        }),
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

    const { getByText, getByLabelText } = render(<DietScreen />);
    await waitFor(() => {
      expect(getByText('待确认饮食')).toBeTruthy();
    });

    fireEvent.press(getByLabelText('核对后确认饮食'));

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
});
