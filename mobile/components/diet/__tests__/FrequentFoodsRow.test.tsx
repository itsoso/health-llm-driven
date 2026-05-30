import React from 'react';
import { render, fireEvent } from '@testing-library/react-native';
import FrequentFoodsRow from '../FrequentFoodsRow';
import type { FrequentFood } from '../../../services/diet';

jest.mock('../../../hooks/useTheme', () => ({
  useTheme: () => ({
    c: {
      bgCard: '#fff', separator: '#eee',
      labelPrimary: '#111', labelSecondary: '#555', labelTertiary: '#999',
    },
    isDark: false,
  }),
}));

const food = (over: Partial<FrequentFood> = {}): FrequentFood => ({
  food_items: '鸡胸肉 200g',
  meal_type: 'lunch',
  count: 3,
  calories: 330,
  protein: 62,
  carbs: 0,
  fat: 7,
  ...over,
});

describe('FrequentFoodsRow', () => {
  it('renders nothing when there are no frequent foods', () => {
    const { queryByTestId } = render(<FrequentFoodsRow foods={[]} onPick={jest.fn()} />);
    expect(queryByTestId('frequent-foods-row')).toBeNull();
  });

  it('renders a chip per food with meal + calories', () => {
    const { getByText } = render(<FrequentFoodsRow foods={[food()]} onPick={jest.fn()} />);
    expect(getByText('鸡胸肉 200g')).toBeTruthy();
    expect(getByText('午餐 · 330kcal')).toBeTruthy();
  });

  it('labels missing calories as estimated instead of faking a number', () => {
    const { getByText } = render(
      <FrequentFoodsRow foods={[food({ calories: null })]} onPick={jest.fn()} />,
    );
    expect(getByText('午餐 · 按历史估算')).toBeTruthy();
  });

  it('calls onPick with the food when a chip is tapped', () => {
    const onPick = jest.fn();
    const f = food();
    const { getByLabelText } = render(<FrequentFoodsRow foods={[f]} onPick={onPick} />);
    fireEvent.press(getByLabelText('记录午餐：鸡胸肉 200g，330kcal'));
    expect(onPick).toHaveBeenCalledWith(f);
  });
});
