import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';
import MealForm from '../MealForm';

describe('MealForm recalculation mode', () => {
  it('keeps old nutrients visible but read-only while food or portion will be recalculated', () => {
    const onSubmit = jest.fn();
    const view = render(
      <MealForm
        date="2026-09-21"
        initialRecord={{
          id: 42, user_id: 1, record_date: '2026-09-21', meal_type: 'dinner',
          food_items: '整桌菜', calories: 1000, protein: 40, carbs: 100, fat: 50,
          fiber: 10, alcohol_units: null, image_url: null, notes: null, health_tips: null,
        }}
        nutritionReadOnly
        nutritionReadOnlyHint="旧营养仅供参考，保存后按新描述和份额重新估算"
        onSubmit={onSubmit}
        onCancel={jest.fn()}
      />,
    );

    expect(view.getByText('旧营养仅供参考，保存后按新描述和份额重新估算')).toBeTruthy();
    expect(view.getByDisplayValue('1000')).toBeDisabled();
    fireEvent.press(view.getByText('重新估算并保存'));
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      food_items: '整桌菜', calories: 1000, protein: 40, carbs: 100, fat: 50,
    }));
  });

  it('locks every control while a save is in flight', () => {
    const onSubmit = jest.fn();
    const onCancel = jest.fn();
    const view = render(
      <MealForm
        date="2026-09-21"
        initialRecord={{
          id: 42, user_id: 1, record_date: '2026-09-21', meal_type: 'dinner',
          food_items: '整桌菜', calories: 1000, protein: 40, carbs: 100, fat: 50,
          fiber: 10, alcohol_units: null, image_url: null, notes: null, health_tips: null,
        }}
        saving
        onSubmit={onSubmit}
        onCancel={onCancel}
      />,
    );

    expect(view.getByDisplayValue('整桌菜')).toBeDisabled();
    expect(view.getByDisplayValue('1000')).toBeDisabled();
    expect(view.getByText('保存中…')).toBeTruthy();
    fireEvent.press(view.getByText('保存中…'));
    fireEvent.press(view.getByText('取消'));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(onCancel).not.toHaveBeenCalled();
  });

  it('rounds a readonly nutrient for display without changing submitted precision', () => {
    const onSubmit = jest.fn();
    const view = render(
      <MealForm
        date="2026-09-21"
        initialRecord={{
          id: 43, user_id: 1, record_date: '2026-09-21', meal_type: 'dinner',
          food_items: '整桌菜', calories: 146.66666666, protein: null, carbs: null, fat: null,
          fiber: null, alcohol_units: null, image_url: null, notes: null, health_tips: null,
        }}
        nutritionReadOnly
        onSubmit={onSubmit}
        onCancel={jest.fn()}
      />,
    );

    expect(view.getByDisplayValue('146.67')).toBeDisabled();
    expect(view.queryByDisplayValue('146.66666666')).toBeNull();
    fireEvent.press(view.getByText('重新估算并保存'));
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ calories: 146.66666666 }));
  });
});
