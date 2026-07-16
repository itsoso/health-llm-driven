import React from 'react';
import { render } from '@testing-library/react-native';
import { DietSummaryCardView } from '../DietSummaryCard';

// 契约 fixture = 后端 build_diet_daily_summary 的 descriptor.data(字段逐一对齐)。
const data = {
  record_date: '2026-07-16',
  meals: [
    { meal_type: 'breakfast', name: '早餐', detail: '山药小米粥·蒸蛋羹×2·焯青菜',
      calories: 400, protein: 23, carbs: 38, fat: 13 },
    { meal_type: 'lunch', name: '午餐', detail: '三文鱼香草芝士鸡肉餐',
      calories: 580, protein: 32, carbs: 28, fat: 36 },
  ],
  totals: { calories: 1710, protein: 92, carbs: 141, fat: 75, fiber: 4 },
  water: { current_ml: 500, target_ml: 2000 },
  observations: [
    { severity: 'normal', label: '蛋白质充足', detail: '全天 92g,达标。' },
    { severity: 'caution', label: '膳食纤维不足', detail: '约 4g,建议 25g+。' },
  ],
};

describe('DietSummaryCardView', () => {
  it('renders meals, detail, observations and water progress', () => {
    const { getByText } = render(<DietSummaryCardView data={data} />);
    expect(getByText('早餐')).toBeTruthy();
    expect(getByText('午餐')).toBeTruthy();
    expect(getByText('山药小米粥·蒸蛋羹×2·焯青菜')).toBeTruthy();
    expect(getByText('蛋白质充足')).toBeTruthy();
    expect(getByText('膳食纤维不足')).toBeTruthy();
    expect(getByText('500/2000ml')).toBeTruthy();
  });

  it('degrades gracefully: water=null / observations=[] / missing fields do not crash', () => {
    expect(() =>
      render(<DietSummaryCardView data={{ meals: [], totals: {}, observations: [] }} />),
    ).not.toThrow();
    expect(() => render(<DietSummaryCardView data={{}} />)).not.toThrow();
    expect(() => render(<DietSummaryCardView data={undefined} />)).not.toThrow();
    // 缺字段的单餐(无 water/observations)不崩
    expect(() =>
      render(
        <DietSummaryCardView
          data={{ meals: [{ meal_type: 'dinner', calories: 700 }], totals: { calories: 700 } }}
        />,
      ),
    ).not.toThrow();
  });
});
