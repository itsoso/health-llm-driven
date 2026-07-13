import React from 'react';
import { PixelRatio, Share } from 'react-native';
import * as Clipboard from 'expo-clipboard';
import { act, fireEvent, render, waitFor } from '@testing-library/react-native';

const mockCaptureRef = jest.fn().mockResolvedValue('file:///meal-share.png');
const mockReleaseCapture = jest.fn();
const mockShareAsync = jest.fn().mockResolvedValue(undefined);
const mockSaveToLibraryAsync = jest.fn().mockResolvedValue(undefined);
const mockRequestPermissionsAsync = jest.fn().mockResolvedValue({ status: 'granted', granted: true });

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

  it('does not show a high balance score before low-confidence estimates are reviewed', () => {
    const lowConfidenceRecord = { ...record, source: 'ai_estimate', ai_confidence: 0.42 };
    const balance = buildDietShareBalance(lowConfidenceRecord);
    const { getAllByText, getByText, queryByText } = render(
      <DietShareCard record={lowConfidenceRecord} dateLabel="7月11日 · 午餐" />,
    );

    expect(balance.score).toBeNull();
    expect(balance.label).toBe('核对后生成均衡度');
    expect(getByText('均衡度')).toBeTruthy();
    expect(getAllByText('待核对').length).toBeGreaterThan(0);
    expect(getByText('核对后生成均衡度')).toBeTruthy();
    expect(queryByText('待回填')).toBeNull();
    expect(queryByText('96')).toBeNull();
    expect(queryByText('高蛋白稳态餐')).toBeNull();
  });

  it('does not render exact macro values on low-confidence share images', () => {
    const lowConfidenceRecord = { ...record, source: 'ai_estimate', ai_confidence: 0.42 };
    const { getByText, queryByText } = render(
      <DietShareCard record={lowConfidenceRecord} dateLabel="7月11日 · 午餐" />,
    );

    expect(getByText('营养估算待核对')).toBeTruthy();
    expect(getByText('确认后再显示热量和三大营养')).toBeTruthy();
    expect(queryByText('560')).toBeNull();
    expect(queryByText('67g')).toBeNull();
    expect(queryByText('48g')).toBeNull();
    expect(queryByText('9.2g')).toBeNull();
    expect(queryByText('能量结构')).toBeNull();
    expect(queryByText('蛋白 50%')).toBeNull();
  });

  it('does not derive macro energy structure for low-confidence diet estimates', () => {
    const lowConfidenceRecord = { ...record, source: 'ai_estimate', ai_confidence: 0.42 };

    expect(buildDietShareMacroSegments(lowConfidenceRecord)).toEqual([]);
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

  it('treats user-corrected records as confirmed even when stale AI confidence remains low', () => {
    const correctedRecord = { ...record, source: 'user_corrected', ai_confidence: 0.42 };
    const { getByText, queryByText } = render(
      <DietShareSheet
        visible
        record={correctedRecord}
        dateLabel="7月11日 · 午餐"
        onClose={jest.fn()}
      />,
    );

    expect(getByText('高清 3:4 图片 · 微信与小红书')).toBeTruthy();
    expect(getByText('蛋白质拉满的一餐')).toBeTruthy();
    expect(getByText('已确认')).toBeTruthy();
    expect(getByText('可分享')).toBeTruthy();
    expect(getByText('手动确认')).toBeTruthy();
    expect(getByText('营养数据以本次确认记录为准')).toBeTruthy();
    expect(getByText('560')).toBeTruthy();
    expect(queryByText('待核对')).toBeNull();
    expect(queryByText('谨慎分享')).toBeNull();
    expect(queryByText('识别置信度 42%')).toBeNull();
    expect(queryByText('发布前建议核对食物和份量')).toBeNull();
  });

  it('uses manually reviewed wording in platform captions for user-corrected meals', () => {
    const correctedRecord = { ...record, source: 'user_corrected' };
    expect(buildDietShareCaption(correctedRecord, '7月11日 · 午餐')).toContain('营养数据: 手动核对，可继续复盘');
    expect(buildDietShareMomentsCaption(correctedRecord, '7月11日 · 午餐')).toContain('营养数据: 手动核对，可继续复盘');
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

    fireEvent.press(getByText('复制小红书复盘文案'));
    await waitFor(() => {
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('营养数据: 智能估算，可继续复盘'));
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.not.stringContaining('营养数据: 智能估算，已确认'));
    });

    fireEvent.press(getByText('复制朋友圈复盘文案'));
    await waitFor(() => {
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('营养数据: 智能估算，可继续复盘'));
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.not.stringContaining('营养数据: 智能估算，已确认'));
    });
  });

  it('frames copied AI-estimated captions as review copy in feedback', async () => {
    const estimatedRecord = { ...record, source: 'ai_estimate', ai_confidence: 0.84 };
    const onShareFeedback = jest.fn();
    const { getByText } = render(
      <DietShareSheet
        visible
        record={estimatedRecord}
        dateLabel="7月11日 · 午餐"
        onClose={jest.fn()}
        onShareFeedback={onShareFeedback}
      />,
    );

    fireEvent.press(getByText('复制小红书复盘文案'));

    await waitFor(() => {
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('营养数据: 智能估算，可继续复盘'));
      expect(getByText('已复制小红书复盘文案')).toBeTruthy();
      expect(onShareFeedback).toHaveBeenCalledWith(expect.objectContaining({
        title: '复盘文案已复制',
        detail: '可继续核对后，再去小红书正文框粘贴',
        tone: 'success',
      }));
      expect(onShareFeedback).not.toHaveBeenCalledWith(expect.objectContaining({
        detail: '去小红书正文框直接粘贴发布',
      }));
    });
  });

  it('does not overstate AI-estimated meals as fully share-ready on the card badge', () => {
    const estimatedRecord = { ...record, source: 'ai_estimate', ai_confidence: 0.84 };
    const { getAllByText, getByText, queryByText } = render(
      <DietShareCard record={estimatedRecord} dateLabel="7月11日 · 午餐" />,
    );

    expect(getAllByText('智能估算').length).toBeGreaterThan(0);
    expect(getByText('可复盘')).toBeTruthy();
    expect(queryByText('可分享')).toBeNull();
  });

  it('keeps high-confidence AI share cards careful on the image itself', () => {
    const estimatedRecord = { ...record, source: 'ai_estimate', ai_confidence: 0.84 };
    const { getByText, queryByText } = render(
      <DietShareCard record={estimatedRecord} dateLabel="7月11日 · 午餐" />,
    );

    expect(getByText('识别结果较稳定')).toBeTruthy();
    expect(getByText('智能估算用于复盘，核对后更准确')).toBeTruthy();
    expect(queryByText('识别结果已确认')).toBeNull();
    expect(queryByText('营养数据以本次确认记录为准')).toBeNull();
  });

  it('labels high-confidence AI share actions as review copy instead of automatic posting', () => {
    const estimatedRecord = { ...record, source: 'ai_estimate', ai_confidence: 0.84 };
    const { getByText, queryByText } = render(
      <DietShareSheet
        visible
        record={estimatedRecord}
        dateLabel="7月11日 · 午餐"
        onClose={jest.fn()}
      />,
    );

    expect(getByText('复盘朋友圈文案')).toBeTruthy();
    expect(getByText('复盘小红书文案')).toBeTruthy();
    expect(getByText('复制复盘朋友圈文案')).toBeTruthy();
    expect(getByText('复制带话题复盘文案')).toBeTruthy();
    expect(getByText('保存复盘图到相册')).toBeTruthy();
    expect(getByText('用于复盘或核对，确认后再发布')).toBeTruthy();
    expect(getByText('保存/分享复盘图')).toBeTruthy();
    expect(getByText('系统面板里保存或发给自己复盘')).toBeTruthy();
    expect(getByText('复制朋友圈复盘文案')).toBeTruthy();
    expect(getByText('复制小红书复盘文案')).toBeTruthy();
    expect(queryByText('自动复制朋友圈文案')).toBeNull();
    expect(queryByText('自动复制带话题文案')).toBeNull();
    expect(queryByText('复制朋友圈文案')).toBeNull();
    expect(queryByText('复制小红书文案')).toBeNull();
    expect(queryByText('发布前先存图，微信 / 小红书直接选')).toBeNull();
  });

  it('surfaces low AI recognition confidence before users share externally', async () => {
    const lowConfidenceRecord = {
      ...record,
      source: 'ai_estimate',
      ai_confidence: 0.42,
      food_items: '机场贵宾厅番茄鸡蛋面、鸭肉、生菜',
    };
    const { getAllByText, getByText, queryByText } = render(
      <DietShareSheet
        visible
        record={lowConfidenceRecord}
        dateLabel="7月11日 · 午餐"
        onClose={jest.fn()}
      />,
    );

    expect(getByText('识别置信度 42%')).toBeTruthy();
    expect(getByText('核对 3:4 图片 · 微信与小红书')).toBeTruthy();
    expect(queryByText('高清 3:4 图片 · 微信与小红书')).toBeNull();
    expect(getByText('发布前建议核对食物和份量')).toBeTruthy();
    expect(getAllByText('待核对').length).toBeGreaterThan(0);
    expect(getByText('谨慎分享')).toBeTruthy();
    expect(queryByText('已确认')).toBeNull();
    expect(queryByText('可分享')).toBeNull();
    expect(getByText('识别待核对，发布前确认食物和份量')).toBeTruthy();
    expect(queryByText('营养数据以本次确认记录为准')).toBeNull();
    expect(getByText('核对后发微信/朋友圈')).toBeTruthy();
    expect(getByText('核对后发小红书')).toBeTruthy();
    expect(queryByText('发微信/朋友圈')).toBeNull();
    expect(queryByText('发小红书')).toBeNull();
    expect(getByText('核对后朋友圈文案')).toBeTruthy();
    expect(getByText('核对后小红书文案')).toBeTruthy();
    expect(queryByText('自动复制朋友圈文案')).toBeNull();
    expect(queryByText('自动复制带话题文案')).toBeNull();

    fireEvent.press(getByText('核对后复制小红书文案'));
    await waitFor(() => {
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('营养数据: 智能估算，待核对后再发布'));
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('识别置信度: 42%，发布前建议核对食物和份量'));
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.not.stringContaining('营养数据: 智能估算，已确认，可继续复盘'));
    });

    fireEvent.press(getByText('核对后复制朋友圈文案'));
    await waitFor(() => {
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('营养数据: 智能估算，待核对后再发布'));
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('识别置信度: 42%，发布前建议核对食物和份量'));
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.not.stringContaining('营养数据: 智能估算，已确认，可继续复盘'));
    });
  });

  it('keeps borderline 60-69% recognition confidence in review mode before sharing', () => {
    const borderlineRecord = {
      ...record,
      source: 'ai_estimate',
      ai_confidence: 0.65,
    };
    const { getByText, getAllByText, queryByText } = render(
      <DietShareSheet
        visible
        record={borderlineRecord}
        dateLabel="7月11日 · 午餐"
        onClose={jest.fn()}
      />,
    );

    expect(getByText('核对 3:4 图片 · 微信与小红书')).toBeTruthy();
    expect(getByText('待核对的一餐')).toBeTruthy();
    expect(getByText('识别置信度 65%')).toBeTruthy();
    expect(getByText('发布前建议核对食物和份量')).toBeTruthy();
    expect(getAllByText('待核对').length).toBeGreaterThan(0);
    expect(getByText('谨慎分享')).toBeTruthy();
    expect(getByText('核对后发微信/朋友圈')).toBeTruthy();
    expect(getByText('核对后发小红书')).toBeTruthy();
    expect(queryByText('蛋白质拉满的一餐')).toBeNull();
    expect(queryByText('高蛋白')).toBeNull();
    expect(queryByText('560')).toBeNull();
  });

  it('does not turn low-confidence estimates into a polished nutrition claim', async () => {
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

    expect(getByText('待核对的一餐')).toBeTruthy();
    expect(queryByText('蛋白质拉满的一餐')).toBeNull();

    fireEvent.press(getByText('核对后复制小红书文案'));
    await waitFor(() => {
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('小巴饮食卡｜待核对的一餐'));
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.not.stringContaining('小巴饮食卡｜蛋白质拉满的一餐'));
    });
  });

  it('does not surface nutrition highlight tags before low-confidence estimates are reviewed', async () => {
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

    expect(getByText('今日状态：待核对')).toBeTruthy();
    expect(queryByText('高蛋白')).toBeNull();
    expect(queryByText('低脂')).toBeNull();
    expect(queryByText('今日状态：高蛋白 · 低脂')).toBeNull();

    fireEvent.press(getByText('核对后复制小红书文案'));
    await waitFor(() => {
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('今日状态: 待核对'));
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.not.stringContaining('亮点: 高蛋白 / 低脂'));
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.not.stringContaining('#高蛋白饮食'));
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.not.stringContaining('#低脂餐'));
    });
  });

  it('keeps low-confidence copied captions from publishing exact macro claims', async () => {
    const lowConfidenceRecord = {
      ...record,
      source: 'ai_estimate',
      ai_confidence: 0.42,
      food_items: '机场贵宾厅番茄鸡蛋面、鸭肉、生菜',
    };
    const { getByText } = render(
      <DietShareSheet
        visible
        record={lowConfidenceRecord}
        dateLabel="7月11日 · 午餐"
        onClose={jest.fn()}
      />,
    );

    fireEvent.press(getByText('核对后复制小红书文案'));
    await waitFor(() => {
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('营养估算待核对，确认后再生成热量和三大营养'));
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.not.stringContaining('热量 560 kcal'));
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.not.stringContaining('蛋白质 67g'));
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.not.stringContaining('能量结构: 蛋白 50%'));
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.not.stringContaining('亮点: 待核对'));
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.not.stringContaining('膳食纤维 3g'));
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

    fireEvent.press(getByText('复制小红书复盘文案'));
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

    fireEvent.press(getByText('复制朋友圈复盘文案'));
    await waitFor(() => {
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('热量估算中'));
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('营养数据: 部分估算中，可继续复盘'));
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.not.stringContaining('已确认部分'));
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
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('#小巴记录'));
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
    const onShareFeedback = jest.fn();
    const { getByText } = render(
      <DietShareSheet
        visible
        record={record}
        dateLabel="7月11日 · 午餐"
        onClose={jest.fn()}
        onShareTerminal={onShareTerminal}
        onShareFeedback={onShareFeedback}
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
      expect(mockRequestPermissionsAsync).toHaveBeenCalledWith(true);
      expect(mockSaveToLibraryAsync).toHaveBeenCalledWith('file:///meal-share.png');
      expect(onShareTerminal).toHaveBeenCalledWith(expect.objectContaining({
        phase: 'completed',
        has_photo: false,
        share_target: 'generic',
      }));
      expect(mockReleaseCapture).toHaveBeenCalledWith('file:///meal-share.png');
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('#小巴记录'));
      expect(getByText('图片已保存到相册，文案已复制')).toBeTruthy();
      expect(getByText('去微信或小红书选择这张图片，再直接粘贴发布')).toBeTruthy();
      expect(onShareFeedback).toHaveBeenCalledWith(expect.objectContaining({
        title: '图片已保存到相册，文案已复制',
        tone: 'success',
      }));
    });
  });

  it('labels photo-library saving as image export progress', async () => {
    let resolveSave: (() => void) | undefined;
    mockSaveToLibraryAsync.mockImplementationOnce(() => new Promise<void>(resolve => {
      resolveSave = resolve;
    }));
    const { getByText } = render(
      <DietShareSheet
        visible
        record={record}
        dateLabel="7月11日 · 午餐"
        onClose={jest.fn()}
      />,
    );

    fireEvent.press(getByText('保存到相册'));

    await waitFor(() => {
      expect(getByText('存图中')).toBeTruthy();
    });

    await act(async () => {
      resolveSave?.();
    });
  });

  it('keeps low-confidence saved share images framed as review material', async () => {
    const lowConfidenceRecord = {
      ...record,
      source: 'ai_estimate',
      ai_confidence: 0.42,
      food_items: '机场贵宾厅番茄鸡蛋面、鸭肉、生菜',
    };
    const onShareFeedback = jest.fn();
    const { getByText, queryByText } = render(
      <DietShareSheet
        visible
        record={lowConfidenceRecord}
        dateLabel="7月11日 · 午餐"
        onClose={jest.fn()}
        onShareFeedback={onShareFeedback}
      />,
    );

    fireEvent.press(getByText('保存复盘图到相册'));

    await waitFor(() => {
      expect(mockSaveToLibraryAsync).toHaveBeenCalledWith('file:///meal-share.png');
      expect(getByText('核对素材已保存，文案已复制')).toBeTruthy();
      expect(getByText('先核对食物和份量，再从相册选择图片发布')).toBeTruthy();
      expect(queryByText('图片已保存到相册，文案已复制')).toBeNull();
      expect(queryByText('去微信或小红书选择这张图片，再直接粘贴发布')).toBeNull();
      expect(onShareFeedback).toHaveBeenCalledWith(expect.objectContaining({
        title: '核对素材已保存，文案已复制',
        tone: 'warning',
      }));
    });
  });

  it('does not capture or save when photo library permission is denied', async () => {
    mockRequestPermissionsAsync.mockResolvedValueOnce({ status: 'denied', granted: false });
    const onShareTerminal = jest.fn();
    const onShareFeedback = jest.fn();
    const { getByText } = render(
      <DietShareSheet
        visible
        record={record}
        dateLabel="7月11日 · 午餐"
        onClose={jest.fn()}
        onShareTerminal={onShareTerminal}
        onShareFeedback={onShareFeedback}
      />,
    );

    fireEvent.press(getByText('保存到相册'));

    await waitFor(() => {
      expect(mockRequestPermissionsAsync).toHaveBeenCalledWith(true);
      expect(mockCaptureRef).not.toHaveBeenCalled();
      expect(mockSaveToLibraryAsync).not.toHaveBeenCalled();
      expect(onShareTerminal).toHaveBeenCalledWith(expect.objectContaining({
        phase: 'failed',
        has_photo: false,
        share_target: 'generic',
        error_code: 'photo_library_permission_denied',
      }));
      expect(getByText('需要相册权限')).toBeTruthy();
      expect(getByText('允许访问相册后，再保存高清分享图')).toBeTruthy();
      expect(onShareFeedback).toHaveBeenCalledWith(expect.objectContaining({
        title: '需要相册权限',
        tone: 'warning',
      }));
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

  it('keeps low-confidence platform share completion framed as review material', async () => {
    const lowConfidenceRecord = {
      ...record,
      source: 'ai_estimate',
      ai_confidence: 0.42,
      food_items: '机场贵宾厅番茄鸡蛋面、鸭肉、生菜',
    };
    const onShareFeedback = jest.fn();
    const { getByText, queryByText } = render(
      <DietShareSheet
        visible
        record={lowConfidenceRecord}
        dateLabel="7月11日 · 午餐"
        onClose={jest.fn()}
        onShareFeedback={onShareFeedback}
      />,
    );

    fireEvent.press(getByText('核对后发小红书'));

    await waitFor(() => {
      expect(getByText('核对素材已准备，文案已复制')).toBeTruthy();
      expect(getByText('先核对食物和份量，再去小红书选择图片发布')).toBeTruthy();
      expect(queryByText('小红书图片已生成，文案已复制')).toBeNull();
      expect(queryByText('去小红书选择图片后直接粘贴发布')).toBeNull();
      expect(onShareFeedback).toHaveBeenCalledWith(expect.objectContaining({
        title: '核对素材已准备，文案已复制',
        tone: 'warning',
      }));
    });
  });

  it('keeps AI-estimated platform share completion framed as review material', async () => {
    const estimatedRecord = { ...record, source: 'ai_estimate', ai_confidence: 0.84 };
    const onShareFeedback = jest.fn();
    const { getByText, queryByText } = render(
      <DietShareSheet
        visible
        record={estimatedRecord}
        dateLabel="7月11日 · 午餐"
        onClose={jest.fn()}
        onShareFeedback={onShareFeedback}
      />,
    );

    fireEvent.press(getByText('发小红书'));

    await waitFor(() => {
      expect(getByText('复盘素材已准备，文案已复制')).toBeTruthy();
      expect(getByText('可继续核对后，再去小红书选择图片发布')).toBeTruthy();
      expect(queryByText('小红书图片已生成，文案已复制')).toBeNull();
      expect(queryByText('去小红书选择图片后直接粘贴发布')).toBeNull();
      expect(onShareFeedback).toHaveBeenCalledWith(expect.objectContaining({
        title: '复盘素材已准备，文案已复制',
        tone: 'success',
      }));
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

  it('frames the ready strip as review material for low-confidence shares', () => {
    const lowConfidenceRecord = { ...record, source: 'ai_estimate', ai_confidence: 0.42 };
    const { getByLabelText, getByText, queryByText } = render(
      <DietShareSheet
        visible
        record={lowConfidenceRecord}
        dateLabel="7月11日 · 午餐"
        onClose={jest.fn()}
      />,
    );

    expect(getByLabelText('核对素材已准备完成')).toBeTruthy();
    expect(getByText('3:4 核对图')).toBeTruthy();
    expect(getByText('核对后朋友圈文案')).toBeTruthy();
    expect(getByText('核对后小红书文案')).toBeTruthy();
    expect(queryByText('3:4 高清图')).toBeNull();
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
    expect(getByText('数据库已保存')).toBeTruthy();
    expect(getByText('复盘会读取数据库快照')).toBeTruthy();
    expect(getByText('读取数据库记录，再看全天热量和下一餐')).toBeTruthy();
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

  it('keeps low-confidence image-share fallback framed as review material', async () => {
    mockShareAsync.mockRejectedValueOnce(new Error('share sheet failed'));
    const lowConfidenceRecord = {
      ...record,
      source: 'ai_estimate',
      ai_confidence: 0.42,
      food_items: '机场贵宾厅番茄鸡蛋面、鸭肉、生菜',
    };
    const onShareTerminal = jest.fn();
    const { getByText, queryByText } = render(
      <DietShareSheet
        visible
        record={lowConfidenceRecord}
        dateLabel="7月11日 · 午餐"
        onClose={jest.fn()}
        onShareTerminal={onShareTerminal}
      />,
    );

    fireEvent.press(getByText('核对后发小红书'));

    await waitFor(() => {
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('营养数据: 智能估算，待核对后再发布'));
      expect(onShareTerminal).toHaveBeenCalledWith(expect.objectContaining({
        phase: 'failed',
        has_photo: false,
        share_target: 'xiaohongshu',
        error_code: 'image_share_fell_back_to_caption',
      }));
      expect(getByText('图片没生成，核对文案已复制')).toBeTruthy();
      expect(getByText('先核对食物和份量，或点“保存/分享复盘图”重试生成核对图')).toBeTruthy();
      expect(queryByText('先发文案，或点“保存/分享图片”重试生成高清图')).toBeNull();
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
    const onShareFeedback = jest.fn();
    const { getByText } = render(
      <DietShareSheet
        visible
        record={record}
        dateLabel="7月11日 · 午餐"
        onClose={jest.fn()}
        onShareFeedback={onShareFeedback}
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
    expect(onShareFeedback).toHaveBeenCalledWith(expect.objectContaining({
      title: '小红书文案已复制',
      tone: 'success',
    }));
  });

  it('keeps low-confidence copied captions framed as review copy', async () => {
    const lowConfidenceRecord = {
      ...record,
      source: 'ai_estimate',
      ai_confidence: 0.42,
      food_items: '机场贵宾厅番茄鸡蛋面、鸭肉、生菜',
    };
    const onShareFeedback = jest.fn();
    const { getByText } = render(
      <DietShareSheet
        visible
        record={lowConfidenceRecord}
        dateLabel="7月11日 · 午餐"
        onClose={jest.fn()}
        onShareFeedback={onShareFeedback}
      />,
    );

    fireEvent.press(getByText('核对后复制小红书文案'));

    await waitFor(() => {
      expect(Clipboard.setStringAsync).toHaveBeenCalledWith(expect.stringContaining('营养数据: 智能估算，待核对后再发布'));
      expect(getByText('已复制核对小红书文案')).toBeTruthy();
      expect(onShareFeedback).toHaveBeenCalledWith(expect.objectContaining({
        title: '核对文案已复制',
        detail: '先核对食物和份量，再去小红书正文框粘贴',
        tone: 'warning',
      }));
      expect(onShareFeedback).not.toHaveBeenCalledWith(expect.objectContaining({
        detail: '去小红书正文框直接粘贴发布',
      }));
    });
  });

  it('copies a WeChat Moments-ready caption without Xiaohongshu hashtags', async () => {
    const onShareFeedback = jest.fn();
    const { getByText } = render(
      <DietShareSheet
        visible
        record={record}
        dateLabel="7月11日 · 午餐"
        onClose={jest.fn()}
        onShareFeedback={onShareFeedback}
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
    expect(onShareFeedback).toHaveBeenCalledWith(expect.objectContaining({
      title: '朋友圈文案已复制',
      tone: 'success',
    }));
  });
});
