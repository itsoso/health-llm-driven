import React from 'react';
import { PixelRatio, Share, StyleSheet } from 'react-native';
import * as Clipboard from 'expo-clipboard';
import { act, fireEvent, render, waitFor, within } from '@testing-library/react-native';

const mockCaptureRef = jest.fn().mockResolvedValue('file:///meal-share.png');
const mockReleaseCapture = jest.fn();
const mockShareAsync = jest.fn().mockResolvedValue(undefined);
const mockSaveToLibraryAsync = jest.fn().mockResolvedValue(undefined);
const mockRequestPermissionsAsync = jest.fn().mockResolvedValue({ status: 'granted', granted: true });

jest.mock('expo-image', () => {
  const ReactModule: any = jest.requireActual('react');
  const { View }: any = jest.requireActual('react-native');
  return {
    Image: ReactModule.forwardRef((props: unknown, ref: unknown) => (
      ReactModule.createElement(View, { ...(props as object), ref })
    )),
  };
});

jest.mock('react-native-view-shot', () => ({
  captureRef: (...args: any[]) => mockCaptureRef(...args),
  releaseCapture: (...args: any[]) => mockReleaseCapture(...args),
}));

jest.mock('expo-sharing', () => ({
  isAvailableAsync: jest.fn().mockResolvedValue(true),
  shareAsync: (...args: any[]) => mockShareAsync(...args),
}));

jest.mock('expo-media-library', () => ({
  requestPermissionsAsync: (...args: any[]) => mockRequestPermissionsAsync(...args),
  saveToLibraryAsync: (...args: any[]) => mockSaveToLibraryAsync(...args),
}));

jest.mock('expo-clipboard', () => ({
  setStringAsync: jest.fn().mockResolvedValue(undefined),
}));

jest.mock('expo-haptics', () => ({
  notificationAsync: jest.fn(),
  NotificationFeedbackType: { Success: 'success' },
}));

// Mocks must be registered before native-backed modules are loaded.
// eslint-disable-next-line import/first
import DietShareCard, {
  DIET_SHARE_IMAGE_TIMEOUT_MS,
  DietShareSheet,
  buildDietShareCaption,
  buildDietShareMomentsCaption,
  compactDietShareFoodItems,
  dietShareCaptureDimensions,
} from '../DietShareCard';
// eslint-disable-next-line import/first
import type { DietRecord } from '../../../services/diet';
// eslint-disable-next-line import/first
import type { DietShareRedaction } from '../dietShareImageEdit';

const imageSource = { uri: 'file:///private/edited-meal.jpg' };
const redactions: DietShareRedaction[] = [{
  points: [{ x: 0.1, y: 0.2 }, { x: 0.8, y: 0.2 }],
  width: 0.06,
}];
const record: DietRecord = {
  id: 88,
  user_id: 1,
  record_date: '2026-07-11',
  meal_type: 'lunch',
  food_items: '猪柳蛋麦满分 1个、脆香油条 1根、大杯优品豆乳 1杯',
  source: 'photo',
  calories: 900,
  protein: 36,
  carbs: 103,
  fat: 42,
  fiber: 5,
  alcohol_units: null,
  image_url: null,
  notes: null,
  health_tips: '下一餐补一份绿叶菜',
  ai_confidence: 0.88,
};

function renderCard(overrides: Partial<React.ComponentProps<typeof DietShareCard>> = {}) {
  return render(
    <DietShareCard
      record={record}
      dateLabel="7月11日"
      imageSource={imageSource}
      redactions={redactions}
      {...overrides}
    />,
  );
}

describe('DietShareCard Xiaohongshu poster', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.spyOn(Share, 'share').mockResolvedValue({ action: Share.sharedAction });
  });

  it('renders the edited meal photo as the dominant 55% layer and uses the presentation contract once', () => {
    const view = renderCard();
    const photoFrameStyle = StyleSheet.flatten(view.getByTestId('diet-share-photo-frame').props.style);

    expect(photoFrameStyle.height).toBe('55%');
    expect(view.getByTestId('diet-share-image').props).toEqual(expect.objectContaining({
      source: imageSource,
      contentFit: 'cover',
    }));
    expect(view.getByText('7月11日')).toBeTruthy();
    expect(view.getByText('午餐')).toBeTruthy();
    expect(view.getByText('今天的午餐，能量很足')).toBeTruthy();
    expect(view.getByText(record.food_items)).toBeTruthy();
    expect(view.getByText('约 900 kcal · 蛋白质 36g')).toBeTruthy();
    expect(view.getByText('碳水 103g · 脂肪 42g')).toBeTruthy();
    expect(view.getByText('高蛋白')).toBeTruthy();
    expect(view.getByText('含纤维')).toBeTruthy();
    expect(view.getByText('下一餐补一份绿叶菜')).toBeTruthy();
    expect(view.getByText('营养由图片估算')).toBeTruthy();
  });

  it('keeps the public poster restrained and free of operational report language', () => {
    const { queryByText } = renderCard();

    [
      '数据库已保存',
      '来源：',
      '来源:',
      '识别置信度',
      '均衡度',
      '可直接分享至微信 / 小红书',
      '小巴生成',
      '不是节食，是把身体照顾得更有章法',
      '不含体重 / 用户 ID / 私密健康数据',
      '能量结构',
    ].forEach(text => expect(queryByText(text)).toBeNull());
    expect(queryByText('900')).toBeNull();
  });

  it('limits poster tags to three and the action to one', () => {
    const manyHighlights = {
      ...record,
      calories: 420,
      protein: 38,
      fat: 9,
      fiber: 8,
      health_tips: '下一餐按目标补足蛋白和蔬菜',
    };
    const view = renderCard({ record: manyHighlights });

    expect(view.getAllByTestId(/^diet-share-tag-/)).toHaveLength(3);
    expect(view.getAllByTestId('diet-share-next-action')).toHaveLength(1);
  });

  it('hides every exact nutrition value when image recognition confidence is low', () => {
    const lowConfidenceRecord = { ...record, source: 'photo', ai_confidence: 0.42 };
    const { getByText, queryByText } = renderCard({ record: lowConfidenceRecord });

    expect(getByText('营养待核对')).toBeTruthy();
    ['900', '36', '103', '42', '约 900 kcal · 蛋白质 36g', '碳水 103g · 脂肪 42g']
      .forEach(text => expect(queryByText(text)).toBeNull());
  });

  it('reports photo failure explicitly without rendering or declaring a metric-only poster ready', () => {
    const onImageReady = jest.fn();
    const onImageError = jest.fn();
    const view = renderCard({ onImageReady, onImageError });

    fireEvent(view.getByTestId('diet-share-image'), 'error', { error: 'load failed' });

    expect(onImageError).toHaveBeenCalledTimes(1);
    expect(onImageReady).not.toHaveBeenCalled();
    expect(view.getByTestId('diet-share-image')).toBeTruthy();
    expect(view.queryByTestId('diet-share-metric-fallback')).toBeNull();
  });

  it('keeps the privacy overlay immediately above the image in the same capture tree', () => {
    const view = renderCard();
    const photo = view.getByTestId('diet-share-image');
    const overlay = view.getByTestId('diet-share-privacy-overlay');
    const photoFrame = view.getByTestId('diet-share-photo-frame');
    const captureTree = view.getByTestId('diet-share-poster');

    expect(within(photoFrame).getByTestId('diet-share-image')).toBe(photo);
    expect(within(photoFrame).getByTestId('diet-share-privacy-overlay')).toBe(overlay);
    expect(within(captureTree).getByTestId('diet-share-photo-frame')).toBe(photoFrame);
  });
});

describe('DietShareSheet image and text behavior', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.spyOn(Share, 'share').mockResolvedValue({ action: Share.sharedAction });
  });

  it('captures exactly 1080x1440 after the photo is ready and opens the system image share sheet', async () => {
    const view = render(
      <DietShareSheet
        visible
        record={record}
        dateLabel="7月11日"
        imageSource={imageSource}
        redactions={redactions}
        onClose={jest.fn()}
      />,
    );
    fireEvent(view.getByTestId('diet-share-image'), 'load');
    fireEvent.press(view.getByRole('button', { name: '发小红书' }));

    await waitFor(() => expect(mockCaptureRef).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({
        format: 'png',
        quality: 1,
        ...dietShareCaptureDimensions(),
        result: 'tmpfile',
      }),
    ));
    expect(mockShareAsync).toHaveBeenCalledWith('file:///meal-share.png', expect.objectContaining({
      mimeType: 'image/png',
      UTI: 'public.png',
    }));
  });

  it('does not construct or capture a metric-only image when no photo is available', () => {
    const view = render(
      <DietShareSheet
        visible
        record={record}
        dateLabel="7月11日"
        onClose={jest.fn()}
      />,
    );

    expect(view.queryByTestId('diet-share-poster')).toBeNull();
    expect(view.getByText('没有可编辑的餐食照片，当前只能分享正文')).toBeTruthy();
    expect(view.getByRole('button', { name: '发小红书' }).props.accessibilityState).toEqual({ disabled: true });
    expect(view.getByRole('button', { name: '复制小红书文案' })).toBeTruthy();
    expect(mockCaptureRef).not.toHaveBeenCalled();
  });

  it('keeps image capture disabled after a protected photo times out', () => {
    jest.useFakeTimers();
    try {
      const view = render(
        <DietShareSheet
          visible
          record={record}
          dateLabel="7月11日"
          imageSource={imageSource}
          onClose={jest.fn()}
        />,
      );

      act(() => jest.advanceTimersByTime(DIET_SHARE_IMAGE_TIMEOUT_MS));

      expect(view.getByText('照片加载失败，请重试或改为分享正文')).toBeTruthy();
      expect(view.getByRole('button', { name: '发小红书' }).props.accessibilityState).toEqual({ disabled: true });
      expect(view.queryByTestId('diet-share-metric-fallback')).toBeNull();
      expect(mockCaptureRef).not.toHaveBeenCalled();
    } finally {
      jest.useRealTimers();
    }
  });

  it('copies Xiaohongshu and Moments captions without changing their platform behavior', async () => {
    const view = render(
      <DietShareSheet
        visible
        record={record}
        dateLabel="7月11日"
        imageSource={imageSource}
        onClose={jest.fn()}
      />,
    );

    fireEvent.press(view.getByRole('button', { name: '复制小红书文案' }));
    await waitFor(() => expect(Clipboard.setStringAsync).toHaveBeenCalledWith(
      buildDietShareCaption(record, '7月11日'),
    ));
    expect(buildDietShareCaption(record, '7月11日')).toContain('#小巴记录');

    fireEvent.press(view.getByRole('button', { name: '复制朋友圈文案' }));
    await waitFor(() => expect(Clipboard.setStringAsync).toHaveBeenCalledWith(
      buildDietShareMomentsCaption(record, '7月11日'),
    ));
    expect(buildDietShareMomentsCaption(record, '7月11日')).not.toContain('#小巴记录');
  });

  it('compacts long food descriptions while keeping short captions unchanged', () => {
    expect(compactDietShareFoodItems('鸡蛋、豆浆')).toBe('鸡蛋、豆浆');
    expect(compactDietShareFoodItems(
      '机场国航贵宾厅番茄鸡蛋面一小份、鸭肉三小块、生菜30克、酸奶三分之二杯、蛋黄酥三分之二块、咖啡半杯',
    )).toMatch(/…$/);
  });
});

describe('dietShareCaptureDimensions', () => {
  it('uses native pixel units on Android and point units on iOS', () => {
    expect(dietShareCaptureDimensions('android', 3)).toEqual({ width: 1080, height: 1440 });
    expect(dietShareCaptureDimensions('ios', 3)).toEqual({ width: 360, height: 480 });
    expect(dietShareCaptureDimensions('ios', 0)).toEqual({ width: 1080, height: 1440 });
    expect(dietShareCaptureDimensions('ios', PixelRatio.get())).toEqual({
      width: 1080 / Math.max(PixelRatio.get(), 1),
      height: 1440 / Math.max(PixelRatio.get(), 1),
    });
  });
});
