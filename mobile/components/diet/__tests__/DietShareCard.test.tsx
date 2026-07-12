import React from 'react';
import { PixelRatio, Share } from 'react-native';
import * as Clipboard from 'expo-clipboard';
import { act, fireEvent, render, waitFor } from '@testing-library/react-native';

const mockCaptureRef = jest.fn().mockResolvedValue('file:///meal-share.png');
const mockReleaseCapture = jest.fn();
const mockShareAsync = jest.fn().mockResolvedValue(undefined);
const mockSaveToLibraryAsync = jest.fn().mockResolvedValue(undefined);

jest.mock('react-native-view-shot', () => ({
  captureRef: (...args: any[]) => mockCaptureRef(...args),
  releaseCapture: (...args: any[]) => mockReleaseCapture(...args),
}));

jest.mock('expo-sharing', () => ({
  isAvailableAsync: jest.fn().mockResolvedValue(true),
  shareAsync: (...args: any[]) => mockShareAsync(...args),
}));

jest.mock('expo-media-library', () => ({
  saveToLibraryAsync: (...args: any[]) => mockSaveToLibraryAsync(...args),
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
  buildDietShareCaption,
  buildDietShareMomentsCaption,
  buildDietShareBalance,
  buildDietShareMacroSegments,
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
    expect(getByText('不是节食，是把身体照顾得更有章法')).toBeTruthy();
    expect(getByText('不含体重 / 用户 ID / 私密健康数据')).toBeTruthy();
    expect(queryByText('user_id')).toBeNull();
  });

  it('adds a share-native balance score to make the card feel worth posting', () => {
    const balance = buildDietShareBalance(record);
    const { getByText } = render(
      <DietShareCard record={record} dateLabel="7月11日 · 午餐" />,
    );

    expect(balance.score).toBe(96);
    expect(balance.label).toBe('高蛋白稳态餐');
    expect(getByText('均衡度')).toBeTruthy();
    expect(getByText('96')).toBeTruthy();
    expect(getByText('高蛋白稳态餐')).toBeTruthy();
  });

  it('derives macro energy structure for a more premium share image', () => {
    const segments = buildDietShareMacroSegments(record);

    expect(segments).toEqual([
      expect.objectContaining({ key: 'protein', label: '蛋白', grams: 67, percent: 50 }),
      expect.objectContaining({ key: 'carbs', label: '碳水', grams: 48, percent: 35 }),
      expect.objectContaining({ key: 'fat', label: '脂肪', grams: 9.2, percent: 15 }),
    ]);
    expect(segments.reduce((sum, segment) => sum + segment.percent, 0)).toBe(100);
  });

  it('renders macro energy structure on the share card', () => {
    const { getByText } = render(
      <DietShareCard record={record} dateLabel="7月11日 · 午餐" />,
    );

    expect(getByText('能量结构')).toBeTruthy();
    expect(getByText('蛋白 50%')).toBeTruthy();
    expect(getByText('碳水 35%')).toBeTruthy();
    expect(getByText('脂肪 15%')).toBeTruthy();
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

  it('writes a Xiaohongshu-native title and dynamic nutrition hashtags', async () => {
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
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('小巴饮食卡｜蛋白质拉满的一餐'));
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('不是节食，是把身体照顾得更有章法'));
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('晒得出，也复盘得清楚'));
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('能量结构: 蛋白 50% / 碳水 35% / 脂肪 15%'));
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('适合截图留档，也适合发给认真生活的朋友'));
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('#高蛋白饮食'));
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('#低脂餐'));
    });
  });

  it('keeps short meal descriptions unchanged in platform captions', () => {
    const xhsCaption = buildDietShareCaption(record, '7月11日 · 午餐');
    const momentsCaption = buildDietShareMomentsCaption(record, '7月11日 · 午餐');

    expect(xhsCaption).toContain('午餐: 鸡胸肉 200g、杂粮饭 1碗');
    expect(momentsCaption).toContain('午餐: 鸡胸肉 200g、杂粮饭 1碗');
  });

  it('compacts long meal descriptions for publish-ready captions', () => {
    const longRecord: DietRecord = {
      ...record,
      food_items: '机场国航贵宾厅番茄鸡蛋面一小份、鸭肉三小块、生菜30克、酸奶三分之二杯、蛋黄酥三分之二块、咖啡半杯',
    };

    const xhsCaption = buildDietShareCaption(longRecord, '7月11日 · 午餐');
    const momentsCaption = buildDietShareMomentsCaption(longRecord, '7月11日 · 午餐');

    expect(xhsCaption).toContain('午餐: 机场国航贵宾厅番茄鸡蛋面一小份、鸭肉三小块、生菜30克、酸奶三分之二杯…');
    expect(xhsCaption).not.toContain('蛋黄酥三分之二块');
    expect(momentsCaption).toContain('午餐: 机场国航贵宾厅番茄鸡蛋面一小份、鸭肉三小块、生菜30克、酸奶三分之二杯…');
    expect(momentsCaption).not.toContain('咖啡半杯');
  });

  it('labels user-corrected nutrition as manually confirmed', () => {
    const { getByText } = render(
      <DietShareCard record={{ ...record, source: 'user_corrected' }} dateLabel="7月11日 · 午餐" />,
    );
    expect(getByText('手动确认')).toBeTruthy();
  });

  it('adds a careful estimate disclosure to platform captions when nutrition is AI-estimated', async () => {
    const estimatedRecord = { ...record, source: 'ai_estimate' };
    const { getByText } = render(
      <DietShareSheet
        visible
        record={estimatedRecord}
        dateLabel="7月11日 · 午餐"
        onClose={jest.fn()}
      />,
    );

    fireEvent.press(getByText('复制小红书文案'));
    await waitFor(() => {
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('营养数据: 智能估算，已确认，可继续复盘'));
    });

    fireEvent.press(getByText('复制朋友圈文案'));
    await waitFor(() => {
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('营养数据: 智能估算，已确认，可继续复盘'));
    });
  });

  it('surfaces low AI recognition confidence before users share externally', async () => {
    const lowConfidenceRecord = {
      ...record,
      source: 'ai_estimate',
      ai_confidence: 0.42,
      food_items: '机场贵宾厅番茄鸡蛋面、鸭肉、生菜',
    };
    const { getByText, queryByText } = render(
      <DietShareSheet
        visible
        record={lowConfidenceRecord}
        dateLabel="7月11日 · 午餐"
        onClose={jest.fn()}
      />,
    );

    expect(getByText('识别置信度 42%')).toBeTruthy();
    expect(getByText('发布前建议核对食物和份量')).toBeTruthy();
    expect(getByText('待核对')).toBeTruthy();
    expect(getByText('谨慎分享')).toBeTruthy();
    expect(queryByText('已确认')).toBeNull();
    expect(queryByText('可分享')).toBeNull();
    expect(getByText('识别待核对，发布前确认食物和份量')).toBeTruthy();
    expect(queryByText('营养数据以本次确认记录为准')).toBeNull();

    fireEvent.press(getByText('复制小红书文案'));
    await waitFor(() => {
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('识别置信度: 42%，发布前建议核对食物和份量'));
    });

    fireEvent.press(getByText('复制朋友圈文案'));
    await waitFor(() => {
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('识别置信度: 42%，发布前建议核对食物和份量'));
    });
  });

  it('keeps pending nutrition share cards and captions polished without placeholder dashes', async () => {
    const pendingRecord: DietRecord = {
      ...record,
      source: 'ai_estimate',
      calories: null,
      protein: null,
      carbs: null,
      fat: null,
      fiber: null,
    };
    const { getAllByText, getByText, queryByText } = render(
      <DietShareSheet
        visible
        record={pendingRecord}
        dateLabel="7月11日 · 午餐"
        onClose={jest.fn()}
      />,
    );

    expect(getAllByText('营养估算中').length).toBeGreaterThan(0);
    expect(getByText('营养回填后用于复盘')).toBeTruthy();
    expect(queryByText('营养数据以本次确认记录为准')).toBeNull();
    expect(queryByText('--')).toBeNull();

    fireEvent.press(getByText('复制小红书文案'));
    await waitFor(() => {
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('营养估算中，稍后可继续复盘'));
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.not.stringContaining('--'));
    });
  });

  it('marks partially backfilled nutrition as still in progress instead of fully final', async () => {
    const partialRecord: DietRecord = {
      ...record,
      source: 'ai_estimate',
      calories: null,
      protein: 42,
      carbs: null,
      fat: null,
      fiber: null,
    };
    const { getByText, queryByText } = render(
      <DietShareSheet
        visible
        record={partialRecord}
        dateLabel="7月11日 · 午餐"
        onClose={jest.fn()}
      />,
    );

    expect(getByText('热量估算中')).toBeTruthy();
    expect(getByText('部分营养回填后用于复盘')).toBeTruthy();
    expect(buildDietShareMacroSegments(partialRecord)).toEqual([]);
    expect(queryByText('能量结构')).toBeNull();
    expect(queryByText('营养数据以本次确认记录为准')).toBeNull();

    fireEvent.press(getByText('复制朋友圈文案'));
    await waitFor(() => {
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('热量估算中'));
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('营养数据: 部分估算中，已确认部分可继续复盘'));
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.not.stringContaining('能量结构'));
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.not.stringContaining('--'));
    });
  });

  it('keeps photo share cards polished when calories are still pending', () => {
    const partialPhotoRecord: DietRecord = {
      ...record,
      source: 'ai_estimate',
      calories: null,
      protein: 42,
      carbs: null,
      fat: null,
      fiber: null,
      image_url: '/api/v1/upload/files/diet/1/meal.png',
    };

    const { getByTestId, getByText, queryByText } = render(
      <DietShareCard
        record={partialPhotoRecord}
        dateLabel="7月11日 · 午餐"
        imageSource={{ uri: 'https://health.executor.life/private-meal.png' }}
      />,
    );

    expect(getByTestId('diet-share-image')).toBeTruthy();
    expect(getByText('热量估算中')).toBeTruthy();
    expect(queryByText('--')).toBeNull();
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

    fireEvent.press(getByText('保存/分享图片'));

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

  it('saves the 1080x1440 share image directly to the photo library', async () => {
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

    fireEvent.press(getByText('保存到相册'));

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
      expect(mockSaveToLibraryAsync).toHaveBeenCalledWith('file:///meal-share.png');
      expect(onShareTerminal).toHaveBeenCalledWith(expect.objectContaining({
        phase: 'completed',
        has_photo: false,
        share_target: 'generic',
      }));
      expect(mockReleaseCapture).toHaveBeenCalledWith('file:///meal-share.png');
      expect(getByText('图片已保存到相册')).toBeTruthy();
      expect(getByText('去微信或小红书选择这张图片，再粘贴文案发布')).toBeTruthy();
    });
  });

  it('offers platform-first image sharing with matching captions', async () => {
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
      expect(onShareTerminal).toHaveBeenCalledWith(expect.objectContaining({
        phase: 'completed',
        share_target: 'xiaohongshu',
      }));
      expect(getByText('小红书图片已生成，文案已复制')).toBeTruthy();
      expect(getByText('去小红书选择图片后直接粘贴发布')).toBeTruthy();
    });
  });

  it('positions the generic action as save-or-share for screenshot workflows', () => {
    const { getByText, getByLabelText } = render(
      <DietShareSheet
        visible
        record={record}
        dateLabel="7月11日 · 午餐"
        onClose={jest.fn()}
      />,
    );

    expect(getByText('保存/分享图片')).toBeTruthy();
    expect(getByText('可在系统面板保存到相册')).toBeTruthy();
    expect(getByLabelText('保存或分享饮食图片')).toBeTruthy();
  });

  it('shows a platform-ready checklist before sharing', () => {
    const { getByText } = render(
      <DietShareSheet
        visible
        record={record}
        dateLabel="7月11日 · 午餐"
        onClose={jest.fn()}
      />,
    );

    expect(getByText('3:4 高清图')).toBeTruthy();
    expect(getByText('朋友圈文案')).toBeTruthy();
    expect(getByText('小红书话题')).toBeTruthy();
  });

  it('shows an optional Agent review CTA for post-confirmation flow', () => {
    const onAskReva = jest.fn();
    const { getByText, getByLabelText } = render(
      <DietShareSheet
        visible
        record={record}
        dateLabel="7月11日 · 午餐"
        onClose={jest.fn()}
        onAskReva={onAskReva}
      />,
    );

    expect(getByText('问小巴复盘今日饮食')).toBeTruthy();
    expect(getByText('先查数据库，再看全天热量和下一餐')).toBeTruthy();
    fireEvent.press(getByLabelText('问小巴复盘今日饮食'));
    expect(onAskReva).toHaveBeenCalledTimes(1);
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

    fireEvent.press(getByLabelText('保存或分享饮食图片'));
    expect(mockCaptureRef).not.toHaveBeenCalled();

    fireEvent(getByTestId('diet-share-image'), 'load');
    fireEvent.press(getByLabelText('保存或分享饮食图片'));
    await waitFor(() => expect(mockCaptureRef).toHaveBeenCalled());
  });

  it('reports successful local-photo shares as photo shares even before the server image url arrives', async () => {
    const onShareTerminal = jest.fn();
    const { getByLabelText, getByTestId } = render(
      <DietShareSheet
        visible
        record={{ ...record, image_url: null }}
        dateLabel="7月11日 · 午餐"
        imageSource={{ uri: 'file:///fresh-camera-meal.heic' }}
        onClose={jest.fn()}
        onShareTerminal={onShareTerminal}
      />,
    );

    fireEvent(getByTestId('diet-share-image'), 'load');
    fireEvent.press(getByLabelText('保存或分享饮食图片'));

    await waitFor(() => {
      expect(onShareTerminal).toHaveBeenCalledWith(expect.objectContaining({
        phase: 'completed',
        has_photo: true,
      }));
    });
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

    fireEvent.press(getByText('保存/分享图片'));

    await waitFor(() => {
      expect(Share.share).toHaveBeenCalledWith(expect.objectContaining({
        message: expect.stringContaining('鸡胸肉 200g、杂粮饭 1碗'),
      }));
      expect(onShareTerminal).toHaveBeenCalledWith(expect.objectContaining({
        phase: 'completed', has_photo: false,
      }));
    });
  });

  it('labels image-share failures as caption fallback instead of completed image share', async () => {
    mockShareAsync.mockRejectedValueOnce(new Error('share sheet failed'));
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

    fireEvent.press(getByText('发小红书'));

    await waitFor(() => {
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('#小巴记录'));
      expect(Share.share).toHaveBeenCalledWith(expect.objectContaining({
        message: expect.stringContaining('鸡胸肉 200g、杂粮饭 1碗'),
      }));
      expect(onShareTerminal).toHaveBeenCalledWith(expect.objectContaining({
        phase: 'failed',
        has_photo: false,
        share_target: 'xiaohongshu',
        error_code: 'image_share_fell_back_to_caption',
      }));
      expect(getByText('图片没生成，文案已复制')).toBeTruthy();
      expect(getByText('先发文案，或点“保存/分享图片”重试生成高清图')).toBeTruthy();
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
    expect(getByText('保存/分享图片')).toBeTruthy();
    fireEvent.press(getByLabelText('保存或分享饮食图片'));
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
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('能量结构: 蛋白 50% / 碳水 35% / 脂肪 15%'));
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('亮点: 高蛋白 / 低脂'));
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('#饮食打卡'));
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('#小巴记录'));
    });
    expect(getByText('已复制小红书文案')).toBeTruthy();
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
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('能量结构: 蛋白 50% / 碳水 35% / 脂肪 15%'));
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.not.stringContaining('#小巴记录'));
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.not.stringContaining('#饮食打卡'));
    });
    expect(getByText('已复制朋友圈文案')).toBeTruthy();
  });
});
