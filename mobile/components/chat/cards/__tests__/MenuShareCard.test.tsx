import React from 'react';
import { fireEvent, render, waitFor } from '@testing-library/react-native';
import { buildShareText, buildXiaohongshuShareText, MenuShareCardView } from '../MenuShareCard';

const mockSharePlainText = jest.fn();
const mockSharePlainCaption = jest.fn();

jest.mock('../../../../utils/share', () => ({
  sharePlainText: (...args: any[]) => mockSharePlainText(...args),
  sharePlainCaption: (...args: any[]) => mockSharePlainCaption(...args),
}));

jest.mock('expo-haptics', () => ({
  selectionAsync: jest.fn().mockResolvedValue(undefined),
}));

describe('MenuShareCard', () => {
  it('shares menu recommendations under the 小巴 persona', async () => {
    const message = buildShareText(
      {
        title: '今晚晚餐',
        reason: '适合轻负担补蛋白。',
        items: [{ name: '鸡胸肉', qty: '150g', kcal: 240 }],
        totals: { kcal: 420, protein: 35, carbs: 40, fat: 12 },
        shopping_list: ['鸡胸肉', '生菜'],
      },
    );

    expect(message).toContain('— 小巴');
    expect(message).not.toContain('健康 Agent');
  });

  it('renders explicit WeChat and Xiaohongshu share actions', async () => {
    mockSharePlainText.mockResolvedValue(undefined);
    mockSharePlainCaption.mockResolvedValue(undefined);
    const { getByLabelText, getByText } = render(
      <MenuShareCardView
        title="今晚晚餐"
        reason="适合轻负担补蛋白。"
        items={[{ name: '鸡胸肉', qty: '150g', kcal: 240 }]}
        totals={{ kcal: 420, protein: 35, carbs: 40, fat: 12 }}
        shopping_list={['鸡胸肉', '生菜']}
      />,
    );

    expect(getByText('发微信')).toBeTruthy();
    expect(getByText('发小红书')).toBeTruthy();
    expect(getByText('更多')).toBeTruthy();

    fireEvent.press(getByLabelText('发微信分享菜单'));
    fireEvent.press(getByLabelText('发小红书分享菜单'));

    await waitFor(() => {
      expect(mockSharePlainText).toHaveBeenCalledTimes(1);
      expect(mockSharePlainText).toHaveBeenCalledWith(expect.objectContaining({
        title: '今晚晚餐',
        message: expect.stringContaining('— 小巴'),
      }));
      expect(mockSharePlainCaption).toHaveBeenCalledTimes(1);
      expect(mockSharePlainCaption).toHaveBeenCalledWith(expect.objectContaining({
        title: '今晚晚餐 · 小红书文案',
        message: expect.stringContaining('适合轻负担补蛋白。'),
      }));
      expect(mockSharePlainCaption).toHaveBeenCalledWith(expect.objectContaining({
        message: expect.not.stringContaining('http'),
      }));
    });
  });

  it('keeps Xiaohongshu copy complete enough for short meal cards without truncating later items', () => {
    const caption = buildXiaohongshuShareText({
      title: '明天早餐',
      reason: '适合控糖日的高蛋白早餐。',
      items: [
        { name: '希腊酸奶', qty: '180g', kcal: 130, protein: 16 },
        { name: '水煮蛋', qty: '1 个', kcal: 78, protein: 6 },
        { name: '蓝莓', qty: '80g', kcal: 45, carbs: 11 },
        { name: '燕麦麸皮', qty: '20g', kcal: 50, fiber: 4 },
        { name: '无糖豆浆', qty: '250ml', kcal: 80, protein: 7 },
        { name: '核桃仁', qty: '10g', kcal: 65, fat: 6 },
      ],
      totals: { kcal: 448, protein: 29, carbs: 38, fat: 18, fiber: 8 },
      shopping_list: ['希腊酸奶', '蓝莓', '无糖豆浆', '核桃仁'],
    });

    expect(caption).toContain('小巴给我的一餐建议');
    expect(caption).toContain('1. 希腊酸奶');
    expect(caption).toContain('6. 核桃仁');
    expect(caption).toContain('蛋白 29g');
    expect(caption).toContain('纤维 8g');
    expect(caption).toContain('买菜清单');
    expect(caption).toContain('无糖豆浆');
    expect(caption).toContain('#小巴饮食建议');
    expect(caption.length).toBeGreaterThan(220);
    expect(caption.length).toBeLessThanOrEqual(900);
  });

  it('allows long menu item names to wrap instead of clipping them to one line', () => {
    const { getByText } = render(
      <MenuShareCardView
        title="今晚晚餐"
        reason="适合轻负担补蛋白。"
        items={[{ name: '低脂高蛋白番茄蘑菇鸡胸肉藜麦碗', qty: '1 份', kcal: 430 }]}
        totals={{ kcal: 430, protein: 36, carbs: 42, fat: 12 }}
      />,
    );

    expect(getByText('低脂高蛋白番茄蘑菇鸡胸肉藜麦碗').props.numberOfLines).toBeUndefined();
  });
});
