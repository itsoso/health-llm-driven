import React from 'react';
import { fireEvent, render, waitFor } from '@testing-library/react-native';

const mockSharePlainText = jest.fn();

jest.mock('../../../../utils/share', () => ({
  sharePlainText: (...args: any[]) => mockSharePlainText(...args),
}));

jest.mock('expo-haptics', () => ({
  selectionAsync: jest.fn().mockResolvedValue(undefined),
}));

const { buildShareText, MenuShareCardView } = require('../MenuShareCard');

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
      expect(mockSharePlainText).toHaveBeenCalledTimes(2);
      expect(mockSharePlainText).toHaveBeenCalledWith(expect.objectContaining({
        title: '今晚晚餐',
        message: expect.stringContaining('— 小巴'),
      }));
    });
  });
});
