/* eslint-disable import/first, @typescript-eslint/no-require-imports */
import React from 'react';
import { Alert } from 'react-native';
import { act, fireEvent, render, waitFor } from '@testing-library/react-native';
import * as ImagePicker from 'expo-image-picker';

const mockRouteParams: Record<string, string> = { capture: 'photo' };
const mockMealForm = jest.fn();
const mockEstimate = jest.fn();
const mockRouterPush = jest.fn();
const mockPushChatWithContext = jest.fn();
const mockEmitClientEvent = jest.fn().mockResolvedValue(undefined);
const mockManipulateAsync = jest.fn();
const mockDeleteTemporaryImage = jest.fn().mockResolvedValue(undefined);
const mockLoadDietPhotoDraft = jest.fn().mockResolvedValue(null);
const mockSaveDietPhotoDraft = jest.fn().mockResolvedValue(undefined);
const mockClearDietPhotoDraft = jest.fn().mockResolvedValue(undefined);
const mockDailyMeals: any[] = [];
let mockAuthUserId: number | null = 7;

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
  requestMediaLibraryPermissionsAsync: jest.fn().mockResolvedValue({ granted: true }),
  launchCameraAsync: jest.fn().mockResolvedValue({ canceled: true, assets: [] }),
  launchImageLibraryAsync: jest.fn().mockResolvedValue({ canceled: true, assets: [] }),
}));

jest.mock('expo-image-manipulator', () => ({
  manipulateAsync: (...args: any[]) => mockManipulateAsync(...args),
  SaveFormat: { JPEG: 'jpeg', PNG: 'png', WEBP: 'webp' },
}));

jest.mock('expo-file-system/legacy', () => ({
  deleteAsync: (...args: any[]) => mockDeleteTemporaryImage(...args),
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
  useAuth: () => ({
    token: mockAuthUserId ? 'test-token' : null,
    user: mockAuthUserId ? { id: mockAuthUserId } : null,
    isLoading: false,
  }),
}));

jest.mock('../../services/dietPhotoDraftStorage', () => ({
  loadDietPhotoDraft: (...args: any[]) => mockLoadDietPhotoDraft(...args),
  saveDietPhotoDraft: (...args: any[]) => mockSaveDietPhotoDraft(...args),
  clearDietPhotoDraft: (...args: any[]) => mockClearDietPhotoDraft(...args),
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
  getDietPhotoDraftStatus: jest.fn().mockResolvedValue({
    status: 'pending',
    expires_at: '2026-07-12T00:00:00Z',
  }),
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
  const MockDietFAB = ({ onPhoto, onLibrary, onText, onVoice }: any) => (
    <View>
      <TouchableOpacity testID="diet-fab-photo" onPress={onPhoto}><Text>拍照</Text></TouchableOpacity>
      <TouchableOpacity testID="diet-fab-library" onPress={onLibrary}><Text>相册</Text></TouchableOpacity>
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

import DietScreen, { buildEditedDietPatch } from '../diet';

describe('DietScreen capture deeplink', () => {
  beforeEach(() => {
    mockMealForm.mockClear();
    mockEstimate.mockClear();
    jest.clearAllMocks();
    (ImagePicker.requestCameraPermissionsAsync as jest.Mock).mockReset().mockResolvedValue({ granted: true });
    (ImagePicker.requestMediaLibraryPermissionsAsync as jest.Mock).mockReset().mockResolvedValue({ granted: true });
    (ImagePicker.launchCameraAsync as jest.Mock).mockReset().mockResolvedValue({ canceled: true, assets: [] });
    (ImagePicker.launchImageLibraryAsync as jest.Mock).mockReset().mockResolvedValue({ canceled: true, assets: [] });
    require('../../services/diet').recognizeFood.mockReset();
    mockLoadDietPhotoDraft.mockResolvedValue(null);
    mockSaveDietPhotoDraft.mockResolvedValue(undefined);
    mockClearDietPhotoDraft.mockResolvedValue(undefined);
    mockManipulateAsync.mockReset();
    mockManipulateAsync.mockResolvedValue({
      uri: 'file:///diet-photo-small.jpg',
      width: 1568,
      height: 1176,
      base64: 'photo-base64',
    });
    mockAuthUserId = 7;
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

  it('recognizes one meal photo selected from the library without opening the camera', async () => {
    const dietService = require('../../services/diet');
    (ImagePicker.launchImageLibraryAsync as jest.Mock).mockResolvedValueOnce({
      canceled: false,
      assets: [{ uri: 'file:///library-meal.heic', width: 3024, height: 4032 }],
    });
    mockManipulateAsync.mockResolvedValueOnce({
      uri: 'file:///library-meal-small.jpg',
      width: 1176,
      height: 1568,
      base64: 'TElCUkFSWQ==',
    });
    dietService.recognizeFood.mockResolvedValueOnce({
      success: true,
      foods: [{ name: '三文鱼能量碗', quantity: null }],
      meal_description: '三文鱼能量碗',
      total_calories: 620,
      total_protein: 34,
      total_carbs: 58,
      total_fat: 24,
      error: null,
    });

    const { getByTestId, getByText, getAllByText } = render(<DietScreen />);
    fireEvent.press(getByTestId('diet-fab-library'));

    await waitFor(() => {
      expect(ImagePicker.launchImageLibraryAsync).toHaveBeenCalledWith(expect.objectContaining({
        mediaTypes: ['images'],
        allowsMultipleSelection: false,
        base64: false,
      }));
      expect(dietService.recognizeFood).toHaveBeenCalledWith('TElCUkFSWQ==');
    });
    expect(ImagePicker.requestMediaLibraryPermissionsAsync).not.toHaveBeenCalled();
    expect(ImagePicker.requestCameraPermissionsAsync).not.toHaveBeenCalled();
    expect(getByText('待确认饮食')).toBeTruthy();
    expect(getAllByText('三文鱼能量碗').length).toBeGreaterThan(0);
  });

  it('returns to idle without recognition when the system photo picker is cancelled', async () => {
    const dietService = require('../../services/diet');

    const { getByTestId } = render(<DietScreen />);
    fireEvent.press(getByTestId('diet-fab-library'));

    await waitFor(() => {
      expect(ImagePicker.launchImageLibraryAsync).toHaveBeenCalled();
    });
    expect(ImagePicker.requestMediaLibraryPermissionsAsync).not.toHaveBeenCalled();
    expect(dietService.recognizeFood).not.toHaveBeenCalled();
    expect(getByTestId('diet-fab-photo')).toBeTruthy();
  });

  it('keeps backend-sanitized meal photos when a food name contains the generic character 片', async () => {
    const dietService = require('../../services/diet');
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation(() => {});
    mockRouteParams.capture = 'photo';
    (ImagePicker.launchCameraAsync as jest.Mock).mockResolvedValueOnce({
      canceled: false,
      assets: [{ uri: 'file:///orange-chicken-rice.jpg', width: 1568, height: 1176 }],
    });
    dietService.recognizeFood.mockResolvedValueOnce({
      success: true,
      foods: [
        { name: '橙子片', quantity: '3片' },
        { name: '鸡肉块（甜酸口味）', quantity: null },
        { name: '蛋炒饭', quantity: '1份' },
        { name: '青豆', quantity: null },
        { name: '红辣椒', quantity: null },
      ],
      meal_description: '橙子片、鸡肉块（甜酸口味）、蛋炒饭、青豆、红辣椒',
      total_calories: 920,
      error: null,
    });

    const { getByText, queryByTestId } = render(<DietScreen />);

    await waitFor(() => {
      expect(getByText('待确认饮食')).toBeTruthy();
    });
    expect(queryByTestId('diet-fab-photo')).toBeNull();
    expect(alertSpy).not.toHaveBeenCalledWith(
      '这不是饮食记录',
      expect.stringContaining('用药或补剂'),
    );
    alertSpy.mockRestore();
  });

  it('turns photo capture into a lightweight confirm card without auto-saving', async () => {
    const dietService = require('../../services/diet');
    mockRouteParams.capture = 'photo';
    (ImagePicker.launchCameraAsync as jest.Mock).mockResolvedValueOnce({
      canceled: false,
      assets: [{ uri: 'file:///diet-photo.heic', width: 4032, height: 3024 }],
    });
    mockManipulateAsync.mockResolvedValueOnce({
      uri: 'file:///diet-photo-small.jpg',
      width: 1568,
      height: 1176,
      base64: 'QUJDRA==',
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
      expect(dietService.recognizeFood).toHaveBeenCalledWith('QUJDRA==');
    });
    expect(ImagePicker.launchCameraAsync).toHaveBeenCalledWith(expect.objectContaining({
      mediaTypes: ['images'],
      base64: false,
    }));
    expect(ImagePicker.launchCameraAsync).toHaveBeenCalledWith(
      expect.not.objectContaining({ quality: expect.anything() }),
    );
    expect(mockManipulateAsync).toHaveBeenCalledWith(
      'file:///diet-photo.heic',
      [{ resize: { width: 1568 } }],
      { compress: 0.7, format: 'jpeg', base64: true },
    );
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
        client_prepare_ms: expect.any(Number),
        payload_bytes: 4,
        food_count: 1,
      }),
    );
    await waitFor(() => {
      expect(mockDeleteTemporaryImage).toHaveBeenCalledWith(
        'file:///diet-photo-small.jpg',
        { idempotent: true },
      );
    });
  });

  it('persists a server-backed photo draft without persisting base64 bytes', async () => {
    const dietService = require('../../services/diet');
    mockRouteParams.capture = 'photo';
    (ImagePicker.launchCameraAsync as jest.Mock).mockResolvedValueOnce({
      canceled: false,
      assets: [{ base64: 'private-photo-base64' }],
    });
    dietService.recognizeFood.mockResolvedValueOnce({
      success: true,
      foods: [{ name: '鸡胸肉', quantity: '200g' }],
      meal_description: '鸡胸肉 200g',
      total_calories: 330,
      photo_draft_token: 'photo-draft-persisted-88',
      error: null,
    });

    render(<DietScreen />);

    await waitFor(() => {
      expect(mockSaveDietPhotoDraft).toHaveBeenCalledWith(
        7,
        expect.objectContaining({
          photo_draft_token: 'photo-draft-persisted-88',
          image_base64: undefined,
          food_items: '鸡胸肉 200g',
        }),
      );
    });
    expect(JSON.stringify(mockSaveDietPhotoDraft.mock.calls[0])).not.toContain('private-photo-base64');
  });

  it('restores a pending photo draft before starting a new camera capture', async () => {
    mockLoadDietPhotoDraft.mockResolvedValueOnce({
      version: 1,
      saved_at: Date.now() - 1_000,
      expires_at: Date.now() + 60_000,
      record: {
        record_date: '2026-07-11',
        meal_type: 'lunch',
        food_items: '已恢复的鸡胸肉 200g',
        calories: 330,
        photo_draft_token: 'restored-photo-draft-88',
        idempotency_key: 'diet-photo:restored-photo-draft-88',
        ai_recognized: 1,
      },
    });
    mockRouteParams.capture = 'photo';

    const { getByText } = render(<DietScreen />);

    await waitFor(() => {
      expect(getByText('已恢复的鸡胸肉 200g')).toBeTruthy();
    });
    expect(ImagePicker.requestCameraPermissionsAsync).not.toHaveBeenCalled();
  });

  it('does not revive a terminal server draft when SecureStore deletion failed', async () => {
    mockLoadDietPhotoDraft.mockResolvedValueOnce({
      version: 1,
      saved_at: Date.now() - 1_000,
      expires_at: Date.now() + 60_000,
      record: {
        record_date: '2026-07-11',
        meal_type: 'lunch',
        food_items: '不应复活的餐食',
        photo_draft_token: 'terminal-photo-draft-88',
      },
    });
    const dietService = require('../../services/diet');
    dietService.getDietPhotoDraftStatus.mockRejectedValueOnce({ response: { status: 404 } });

    const { queryByText } = render(<DietScreen />);

    await waitFor(() => expect(mockClearDietPhotoDraft).toHaveBeenCalledWith(7));
    expect(queryByText('不应复活的餐食')).toBeNull();
  });

  it('clears stale macros and provenance when an existing meal identity changes', () => {
    expect(buildEditedDietPatch({
      id: 90,
      user_id: 7,
      record_date: '2026-07-11',
      meal_type: 'lunch',
      food_items: '鸡胸肉 200g',
      food_id: 'cfc:chicken_breast',
      source: 'china_food_composition',
      calories: 330,
      protein: 62,
      carbs: 0,
      fat: 7.2,
      fiber: 0,
      alcohol_units: null,
      image_url: null,
      notes: null,
      health_tips: '旧建议',
      ai_recognized: 1,
      ai_confidence: 0.9,
    }, {
      record_date: '2026-07-11',
      meal_type: 'lunch',
      food_items: '三文鱼 180g',
      calories: 330,
      protein: 62,
      carbs: 0,
      fat: 7.2,
    })).toEqual(expect.objectContaining({
      food_items: '三文鱼 180g',
      food_id: null,
      calories: null,
      protein: null,
      carbs: null,
      fat: null,
      fiber: null,
      source: 'user_corrected',
      ai_recognized: 0,
      ai_confidence: null,
      ai_raw_result: null,
      health_tips: null,
    }));
  });

  it('preserves fiber and provenance when an existing meal only changes meal type', () => {
    const patch = buildEditedDietPatch({
      id: 91,
      user_id: 7,
      record_date: '2026-07-11',
      meal_type: 'lunch',
      food_items: '鸡胸肉 200g',
      food_id: 'cfc:chicken_breast',
      source: 'china_food_composition',
      calories: 330,
      protein: 62,
      carbs: 0,
      fat: 7.2,
      fiber: 4,
      alcohol_units: null,
      image_url: null,
      notes: null,
      health_tips: '原建议',
      ai_recognized: 1,
      ai_confidence: 0.9,
    }, {
      record_date: '2026-07-11',
      meal_type: 'dinner',
      food_items: '鸡胸肉 200g',
      calories: 330,
      protein: 62,
      carbs: 0,
      fat: 7.2,
    });

    expect(patch.meal_type).toBe('dinner');
    expect(patch).not.toHaveProperty('fiber');
    expect(patch).not.toHaveProperty('source');
    expect(patch).not.toHaveProperty('ai_recognized');
    expect(patch).not.toHaveProperty('ai_confidence');
    expect(patch).not.toHaveProperty('ai_raw_result');
  });

  it('clears an in-memory photo draft when the authenticated owner changes', async () => {
    mockLoadDietPhotoDraft.mockResolvedValueOnce({
      version: 1,
      saved_at: Date.now() - 1_000,
      expires_at: Date.now() + 60_000,
      record: {
        record_date: '2026-07-11',
        meal_type: 'lunch',
        food_items: '账号一的私有餐食',
        photo_draft_token: 'owner-one-photo-draft-88',
      },
    });
    const { getByText, queryByText, rerender } = render(<DietScreen />);
    await waitFor(() => expect(getByText('账号一的私有餐食')).toBeTruthy());

    mockAuthUserId = 8;
    mockLoadDietPhotoDraft.mockResolvedValueOnce(null);
    rerender(<DietScreen />);

    await waitFor(() => expect(mockLoadDietPhotoDraft).toHaveBeenCalledWith(8));
    expect(queryByText('账号一的私有餐食')).toBeNull();
  });

  it('drops stale recognition provenance when a photo draft food is corrected', async () => {
    const dietService = require('../../services/diet');
    mockRouteParams.capture = 'photo';
    (ImagePicker.launchCameraAsync as jest.Mock).mockResolvedValueOnce({
      canceled: false,
      assets: [{ base64: 'photo-base64' }],
    });
    dietService.recognizeFood.mockResolvedValueOnce({
      success: true,
      foods: [{
        name: '鸡胸肉', quantity: '200g', food_id: 'cfc:chicken_breast',
        source: 'china_food_composition', nutrition_basis: 'food_table', confidence: 0.9,
      }],
      meal_description: '鸡胸肉 200g',
      total_calories: 330,
      total_fiber: 5,
      photo_draft_token: 'photo-draft-corrected-88',
      error: null,
    });
    dietService.createDietRecord.mockResolvedValueOnce({ id: 88 });

    const { getByText, getByTestId, getByLabelText } = render(<DietScreen />);
    await waitFor(() => expect(getByText('待确认饮食')).toBeTruthy());
    fireEvent.press(getByLabelText('修正饮食草稿'));
    await waitFor(() => expect(getByTestId('meal-form')).toBeTruthy());
    const formProps = mockMealForm.mock.calls[mockMealForm.mock.calls.length - 1][0];
    await act(async () => {
      await formProps.onSubmit({
        record_date: '2026-07-11', meal_type: 'lunch', food_items: '三文鱼 180g',
        calories: 360, protein: 38, carbs: 0, fat: 22,
      });
    });

    expect(dietService.createDietRecord).toHaveBeenCalledWith(expect.objectContaining({
      food_items: '三文鱼 180g',
      source: 'user_corrected',
      food_id: undefined,
      ai_raw_result: undefined,
      ai_confidence: undefined,
      ai_recognized: 0,
      fiber: undefined,
      photo_draft_token: 'photo-draft-corrected-88',
    }));
    expect(mockEmitClientEvent).toHaveBeenCalledWith(
      'diet_photo_confirmation_terminal',
      expect.objectContaining({ phase: 'completed', verified: true, corrected: true }),
    );
    expect(mockClearDietPhotoDraft).toHaveBeenCalledWith(7);
  });

  it('still confirms a corrected photo draft when SecureStore refresh fails', async () => {
    mockLoadDietPhotoDraft.mockResolvedValueOnce({
      version: 1,
      saved_at: Date.now() - 1_000,
      expires_at: Date.now() + 60_000,
      record: {
        record_date: '2026-07-11', meal_type: 'lunch', food_items: '鸡胸肉 200g',
        photo_draft_token: 'secure-store-failure-token-88',
      },
    });
    mockSaveDietPhotoDraft.mockRejectedValueOnce(new Error('keychain unavailable'));
    const dietService = require('../../services/diet');
    dietService.createDietRecord.mockResolvedValueOnce({ id: 89 });
    const { getByText, getByTestId, getByLabelText } = render(<DietScreen />);
    await waitFor(() => expect(getByText('鸡胸肉 200g')).toBeTruthy());
    fireEvent.press(getByLabelText('修正饮食草稿'));
    await waitFor(() => expect(getByTestId('meal-form')).toBeTruthy());
    const formProps = mockMealForm.mock.calls[mockMealForm.mock.calls.length - 1][0];

    await act(async () => {
      await formProps.onSubmit({
        record_date: '2026-07-11', meal_type: 'lunch', food_items: '鸡胸肉 180g',
        calories: 300, protein: 55, carbs: 0, fat: 7,
      });
    });

    expect(dietService.createDietRecord).toHaveBeenCalledWith(expect.objectContaining({
      photo_draft_token: 'secure-store-failure-token-88',
      food_items: '鸡胸肉 180g',
    }));
  });

  it('discards the server photo draft when correction form is cancelled', async () => {
    mockLoadDietPhotoDraft.mockResolvedValueOnce({
      version: 1,
      saved_at: Date.now() - 1_000,
      expires_at: Date.now() + 60_000,
      record: {
        record_date: '2026-07-11', meal_type: 'lunch', food_items: '鸡胸肉 200g',
        photo_draft_token: 'restored-cancel-token-88',
      },
    });
    const dietService = require('../../services/diet');
    const { getByText, getByTestId, getByLabelText } = render(<DietScreen />);
    await waitFor(() => expect(getByText('待确认饮食')).toBeTruthy());
    fireEvent.press(getByLabelText('修正饮食草稿'));
    await waitFor(() => expect(getByTestId('meal-form')).toBeTruthy());
    const formProps = mockMealForm.mock.calls[mockMealForm.mock.calls.length - 1][0];
    await act(async () => {
      await formProps.onCancel();
    });

    await waitFor(() => {
      expect(dietService.discardDietPhotoDraft).toHaveBeenCalledWith('restored-cancel-token-88');
      expect(mockClearDietPhotoDraft).toHaveBeenCalledWith(7);
    });
  });

  it('clears an expired restored draft instead of trapping the user in retries', async () => {
    mockLoadDietPhotoDraft.mockResolvedValueOnce({
      version: 1,
      saved_at: Date.now() - 1_000,
      expires_at: Date.now() + 60_000,
      record: {
        record_date: '2026-07-11', meal_type: 'lunch', food_items: '过期餐食',
        photo_draft_token: 'expired-server-token-88',
      },
    });
    const dietService = require('../../services/diet');
    dietService.createDietRecord.mockRejectedValueOnce({ response: { status: 410 } });
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation(() => {});
    const { getByText, queryByText } = render(<DietScreen />);
    await waitFor(() => expect(getByText('过期餐食')).toBeTruthy());

    fireEvent.press(getByText('确认记录'));

    await waitFor(() => {
      expect(mockClearDietPhotoDraft).toHaveBeenCalledWith(7);
      expect(alertSpy).toHaveBeenCalledWith('照片草稿已失效', '请重新拍照识别这一餐。');
      expect(queryByText('过期餐食')).toBeNull();
    });
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

  it('reassures the user when meal photo recognition takes longer', async () => {
    jest.useFakeTimers();
    try {
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

      act(() => {
        jest.advanceTimersByTime(6500);
      });

      await waitFor(() => {
        expect(getByText('仍在识别照片；完成后会先给你确认草稿，不会自动写入。')).toBeTruthy();
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
    } finally {
      jest.useRealTimers();
    }
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
          portion_basis: 'vision_estimate', portion_confidence: 0.74,
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
    expect(getByText('已带营养估算，确认后计入今日')).toBeTruthy();
    expect(getByText('鸡胸肉')).toBeTruthy();
    expect(getByText('200g · 330 kcal')).toBeTruthy();
    expect(getByText('表值 × 估算份量')).toBeTruthy();
    expect(getByText('识别较稳')).toBeTruthy();
    expect(getByText('杂粮饭')).toBeTruthy();
    expect(getByText('1碗 · 230 kcal')).toBeTruthy();
    expect(getByText('视觉估算')).toBeTruthy();
    expect(getByText('识别待核对')).toBeTruthy();
    expect(getAllByText('份量为估算').length).toBeGreaterThan(0);
    expect(getAllByText('请核对份量').length).toBeGreaterThan(0);
    expect(getByText('小巴建议先核对：鸡胸肉、杂粮饭的份量；确认后才写入今天饮食。')).toBeTruthy();
    expect(getByText('修正份量')).toBeTruthy();
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
    expect(getByText('确认后先记录，营养后台估算')).toBeTruthy();
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
    expect(getByText('确认后先记录，营养后台估算')).toBeTruthy();
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

  it('opens the premium share preview immediately after a direct quick diet confirmation', async () => {
    const dietService = require('../../services/diet');
    dietService.createDietRecord.mockResolvedValueOnce({
      id: 88,
      user_id: 1,
      record_date: '2026-07-11',
      meal_type: 'lunch',
      food_items: '鸡胸肉 200g + 糙米饭一碗',
      source: 'ai_estimate',
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
      expect(getByText('分享这一餐')).toBeTruthy();
      expect(getByText('高清 3:4 图片 · 微信与小红书')).toBeTruthy();
      expect(getByText('复制小红书文案')).toBeTruthy();
    });
    expect(mockPushChatWithContext).not.toHaveBeenCalled();
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

    const { getByText, queryByText } = render(<DietScreen />);
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
        expect.objectContaining({ phase: 'completed', verified: true, corrected: false }),
      );
    });
    expect(queryByText('分享这一餐')).toBeNull();
  });

  it('returns to chat with diet context after confirming a chat-originated library meal photo draft', async () => {
    const dietService = require('../../services/diet');
    mockRouteParams.capture = 'library';
    mockRouteParams.return_to = 'chat';
    (ImagePicker.launchImageLibraryAsync as jest.Mock).mockResolvedValueOnce({
      canceled: false,
      assets: [{ uri: 'file:///chat-library-meal.jpg', width: 1568, height: 1176 }],
    });
    dietService.recognizeFood.mockResolvedValueOnce({
      success: true,
      foods: [{ name: '三文鱼能量碗', quantity: null }],
      meal_description: '三文鱼能量碗',
      total_calories: 620,
      total_protein: 34,
      total_carbs: 58,
      total_fat: 22,
      photo_draft_token: 'library-draft-91',
      error: null,
    });
    dietService.createDietRecord.mockResolvedValueOnce({ id: 91 });

    const { getByText } = render(<DietScreen />);
    await waitFor(() => {
      expect(ImagePicker.launchImageLibraryAsync).toHaveBeenCalled();
      expect(getByText('待确认饮食')).toBeTruthy();
    });

    fireEvent.press(getByText('确认记录'));

    await waitFor(() => {
      expect(dietService.createDietRecord).toHaveBeenCalledWith(expect.objectContaining({
        photo_draft_token: 'library-draft-91',
        idempotency_key: 'diet-photo:library-draft-91',
        food_items: '三文鱼能量碗',
      }));
      expect(mockPushChatWithContext).toHaveBeenCalledWith(
        expect.objectContaining({ push: expect.any(Function) }),
        expect.objectContaining({
          prompt: expect.stringContaining('刚记录了一餐'),
          badge: '刚记录饮食',
          context: expect.objectContaining({
            from: 'diet/quick_capture',
            created_id: 91,
            record: expect.objectContaining({
              food_items: '三文鱼能量碗',
              calories: 620,
              protein: 34,
            }),
          }),
        }),
      );
    });
  });

  it('returns to chat with diet context after confirming a chat-originated text meal draft', async () => {
    const dietService = require('../../services/diet');
    mockRouteParams.capture = 'text';
    mockRouteParams.return_to = 'chat';
    const promptSpy = jest.spyOn(Alert, 'prompt').mockImplementationOnce((_title, _message, callback) => {
      if (typeof callback === 'function') callback('鸡胸肉 200g + 糙米饭一碗');
    });
    dietService.createDietRecord.mockResolvedValueOnce({ id: 92 });

    const { getByText } = render(<DietScreen />);
    await waitFor(() => {
      expect(promptSpy).toHaveBeenCalled();
      expect(getByText('待确认饮食')).toBeTruthy();
    });

    fireEvent.press(getByText('确认记录'));

    await waitFor(() => {
      expect(dietService.createDietRecord).toHaveBeenCalledWith(expect.objectContaining({
        food_items: '鸡胸肉 200g + 糙米饭一碗',
      }));
      expect(mockPushChatWithContext).toHaveBeenCalledWith(
        expect.objectContaining({ push: expect.any(Function) }),
        expect.objectContaining({
          prompt: expect.stringContaining('刚记录了一餐'),
          context: expect.objectContaining({
            from: 'diet/quick_capture',
            created_id: 92,
            record: expect.objectContaining({
              food_items: '鸡胸肉 200g + 糙米饭一碗',
            }),
          }),
        }),
      );
    });
    promptSpy.mockRestore();
  });

  it('returns to chat with diet context after confirming a chat-originated voice meal draft', async () => {
    const dietService = require('../../services/diet');
    mockRouteParams.capture = 'voice';
    mockRouteParams.return_to = 'chat';
    const promptSpy = jest.spyOn(Alert, 'prompt').mockImplementationOnce((_title, _message, callback) => {
      if (typeof callback === 'function') callback('晚饭吃了牛肉面');
    });
    dietService.createDietRecord.mockResolvedValueOnce({ id: 93 });

    const { getByText } = render(<DietScreen />);
    await waitFor(() => {
      expect(promptSpy).toHaveBeenCalled();
      expect(getByText('待确认饮食')).toBeTruthy();
    });

    fireEvent.press(getByText('确认记录'));

    await waitFor(() => {
      expect(dietService.createDietRecord).toHaveBeenCalledWith(expect.objectContaining({
        food_items: '晚饭吃了牛肉面',
      }));
      expect(mockPushChatWithContext).toHaveBeenCalledWith(
        expect.objectContaining({ push: expect.any(Function) }),
        expect.objectContaining({
          context: expect.objectContaining({
            from: 'diet/quick_capture',
            created_id: 93,
            record: expect.objectContaining({
              food_items: '晚饭吃了牛肉面',
            }),
          }),
        }),
      );
    });
    promptSpy.mockRestore();
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

  it('opens a premium share preview from a confirmed meal row', async () => {
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
    expect(getByText('蛋白质拉满的一餐')).toBeTruthy();
    await waitFor(() => expect(mockLoadDietPhotoDraft).toHaveBeenCalledWith(7));
  });
});
