import React from 'react';
import { Alert } from 'react-native';
import { fireEvent, render, waitFor } from '@testing-library/react-native';

jest.mock('@expo/vector-icons', () => ({ Ionicons: 'Ionicons' }));

const mockListRecipes = jest.fn();
const mockDeleteRecipe = jest.fn();
jest.mock('../../../services/procedureRecipes', () => ({
  listRecipes: (...args: any[]) => mockListRecipes(...args),
  deleteRecipe: (...args: any[]) => mockDeleteRecipe(...args),
}));

import RecipeManagerSheet from '../RecipeManagerSheet';

const RECIPES = [
  {
    id: 1,
    name: '早餐套餐',
    trigger_phrases: ['早餐套餐打卡'],
    steps: [{ tool: 'health_record', args_template: {} }, { tool: 'health_record', args_template: {} }],
    created_from_conversation_id: 42,
    use_count: 3,
    created_at: '2026-07-11T09:00:00+08:00',
  },
  {
    id: 2,
    name: '晚间流程',
    trigger_phrases: ['晚间流程打卡'],
    steps: [{ tool: 'health_record', args_template: {} }],
    created_from_conversation_id: null,
    use_count: 0,
    created_at: '2026-07-10T20:00:00+08:00',
  },
];

describe('RecipeManagerSheet', () => {
  beforeEach(() => {
    mockListRecipes.mockReset();
    mockDeleteRecipe.mockReset();
  });

  it('lists saved recipes with trigger phrase, step count and use count', async () => {
    mockListRecipes.mockResolvedValue(RECIPES);
    const { getByText } = render(<RecipeManagerSheet visible onClose={() => {}} />);

    await waitFor(() => expect(getByText('早餐套餐')).toBeTruthy());
    expect(getByText('晚间流程')).toBeTruthy();
    expect(getByText(/说「早餐套餐打卡」触发 · 2 步 · 已用 3 次/)).toBeTruthy();
  });

  it('shows the honest empty state with the save-recipe hint', async () => {
    mockListRecipes.mockResolvedValue([]);
    const { getByText } = render(<RecipeManagerSheet visible onClose={() => {}} />);

    await waitFor(() => expect(getByText(/还没有配方/)).toBeTruthy());
  });

  it('shows an explicit error state with retry when loading fails', async () => {
    mockListRecipes.mockRejectedValueOnce(new Error('network down'));
    mockListRecipes.mockResolvedValueOnce(RECIPES);
    const { getByText, getByLabelText } = render(
      <RecipeManagerSheet visible onClose={() => {}} />,
    );

    await waitFor(() => expect(getByText('配方列表加载失败')).toBeTruthy());
    fireEvent.press(getByLabelText('重试加载配方列表'));
    await waitFor(() => expect(getByText('早餐套餐')).toBeTruthy());
    expect(mockListRecipes).toHaveBeenCalledTimes(2);
  });

  it('deletes a recipe only after the destructive confirm', async () => {
    mockListRecipes.mockResolvedValue(RECIPES);
    mockDeleteRecipe.mockResolvedValue(undefined);
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation((_t, _m, buttons) => {
      const destructive = (buttons ?? []).find((b: any) => b.style === 'destructive');
      destructive?.onPress?.();
    });
    const { getByLabelText, queryByText } = render(
      <RecipeManagerSheet visible onClose={() => {}} />,
    );

    await waitFor(() => expect(getByLabelText('删除配方 早餐套餐')).toBeTruthy());
    fireEvent.press(getByLabelText('删除配方 早餐套餐'));

    await waitFor(() => expect(mockDeleteRecipe).toHaveBeenCalledWith(1));
    await waitFor(() => expect(queryByText('早餐套餐')).toBeNull());
    expect(queryByText('晚间流程')).toBeTruthy();
    alertSpy.mockRestore();
  });

  it('calls onClose from the header close button', async () => {
    mockListRecipes.mockResolvedValue([]);
    const onClose = jest.fn();
    const { getByLabelText } = render(<RecipeManagerSheet visible onClose={onClose} />);

    await waitFor(() => expect(getByLabelText('关闭配方管理')).toBeTruthy());
    fireEvent.press(getByLabelText('关闭配方管理'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
