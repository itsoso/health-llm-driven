// @vitest-environment jsdom
import React from 'react';
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import MealPlanCard from '../MealPlanCard';
import type { MealPlanData } from '../assistantContent';

const plan: MealPlanData = {
  title: '户外日午餐',
  reason: '训练量大，补碳水和蛋白。',
  items: [
    { name: '鸡胸肉', qty: '150g', kcal: 165 },
    { name: '糙米饭', qty: '1碗', kcal: 220 },
  ],
  totals: { kcal: 520, protein: 38, carbs: 55, fat: 12 },
  shopping_list: ['鸡胸肉 150g', '糙米 100g'],
};

describe('MealPlanCard', () => {
  it('renders title, reason, items, totals and shopping list', () => {
    render(<MealPlanCard plan={plan} />);
    expect(screen.getByText('户外日午餐')).toBeInTheDocument();
    expect(screen.getByText('训练量大，补碳水和蛋白。')).toBeInTheDocument();
    expect(screen.getByText('鸡胸肉')).toBeInTheDocument();
    expect(screen.getByText('糙米饭')).toBeInTheDocument();
    expect(screen.getByText('520')).toBeInTheDocument();
    expect(screen.getByText('买菜清单')).toBeInTheDocument();
    expect(screen.getByText(/鸡胸肉 150g/)).toBeInTheDocument();
  });

  it('renders without optional fields (no totals / shopping)', () => {
    render(<MealPlanCard plan={{ title: '简餐', items: [{ name: '水煮蛋' }] }} />);
    expect(screen.getByText('简餐')).toBeInTheDocument();
    expect(screen.getByText('水煮蛋')).toBeInTheDocument();
    expect(screen.queryByText('买菜清单')).not.toBeInTheDocument();
  });
});
