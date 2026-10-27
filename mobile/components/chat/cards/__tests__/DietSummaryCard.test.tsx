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
  it('marks partial historical cards and suppresses unsupported daily judgements', () => {
    const { getByText, queryByText } = render(<DietSummaryCardView data={{
      ...data, meals: [...data.meals, { meal_type: 'lunch' }],
    }} />);
    expect(getByText('已知小计')).toBeTruthy();
    expect(getByText('980')).toBeTruthy();
    expect(getByText('1 条记录营养数据不完整；小计仅含各项已知值，不能代表全天摄入。')).toBeTruthy();
    expect(queryByText('全天合计')).toBeNull();
    expect(queryByText('蛋白质充足')).toBeNull();
  });

  it('keeps unknown distinct from a real zero', () => {
    const { queryByText, getByText, getAllByText } = render(<DietSummaryCardView data={{
      meals: [{ calories: null, protein: 0, carbs: -1, fat: true }],
      totals: { calories: 0, protein: 0, carbs: 0, fat: 0 },
    }} />);
    expect(getByText('已知小计')).toBeTruthy();
    expect(queryByText('全天合计')).toBeNull();
    expect(getAllByText('—')).toHaveLength(6);
    expect(getAllByText('0')).toHaveLength(2);
  });

  it('preserves the new server subtotal summed before rounding individual readings', () => {
    const { getByText } = render(<DietSummaryCardView data={{
      meals: [{ calories: 0, protein: 0, carbs: 0, fat: 0 },
        { calories: 0, protein: 0, carbs: 0, fat: 0 }],
      totals: { calories: 0.01, protein: 0, carbs: 0, fat: 0 },
      nutrition_coverage: { version: 1, record_count: 2, incomplete_records: 0,
        missing_by_nutrient: { calories: 0, protein: 0, carbs: 0, fat: 0, fiber: 2 } },
    }} />);
    expect(getByText('0.01')).toBeTruthy();
    expect(getByText('已记录合计')).toBeTruthy();
  });

  it('does not display a zero subtotal for an entirely unknown meal', () => {
    const { queryByText, getByText } = render(<DietSummaryCardView data={{
      meals: [{ meal_type: 'lunch' }], totals: { calories: 0, protein: 0, carbs: 0, fat: 0 },
    }} />);
    expect(queryByText('0')).toBeNull();
    expect(getByText('1 条记录营养数据不完整；小计仅含各项已知值，不能代表全天摄入。')).toBeTruthy();
  });
  it('renders meals, detail, observations and water progress', () => {
    const { getByText, queryByText } = render(<DietSummaryCardView data={data} />);
    expect(getByText('早餐')).toBeTruthy();
    expect(getByText('午餐')).toBeTruthy();
    expect(getByText('山药小米粥·蒸蛋羹×2·焯青菜')).toBeTruthy();
    expect(queryByText('蛋白质充足')).toBeNull();
    expect(queryByText('膳食纤维不足')).toBeNull();
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
