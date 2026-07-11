import React from 'react';
import { fireEvent, render, waitFor } from '@testing-library/react-native';

jest.mock('@expo/vector-icons', () => ({ Ionicons: 'Ionicons' }));

const mockSaveRecipeFromConversation = jest.fn();
jest.mock('../../../../services/procedureRecipes', () => ({
  saveRecipeFromConversation: (...args: any[]) => mockSaveRecipeFromConversation(...args),
}));

import { SaveRecipeCardSpec, SaveRecipeCardView } from '../SaveRecipeCard';

const CARD_DATA = {
  conversation_id: 42,
  step_count: 2,
  steps_preview: ['饮食 鸡蛋, 燕麦', '饮水 300ml'],
};

describe('SaveRecipeCard', () => {
  beforeEach(() => {
    mockSaveRecipeFromConversation.mockReset();
  });

  it('is backend-dispatch only (no local keyword match)', () => {
    expect(SaveRecipeCardSpec.type).toBe('save_recipe');
    expect(SaveRecipeCardSpec.match({} as any)).toBeNull();
    expect(SaveRecipeCardSpec.build({} as any)).toBeNull();
  });

  it('renders the steps preview and opens the naming sheet', () => {
    const { getByText, getByLabelText, queryByTestId } = render(
      <SaveRecipeCardView {...CARD_DATA} />,
    );

    expect(getByText('饮食 鸡蛋, 燕麦 → 饮水 300ml')).toBeTruthy();
    expect(queryByTestId('save-recipe-sheet')).toBeNull();
    fireEvent.press(getByLabelText('存为配方'));
    expect(queryByTestId('save-recipe-sheet')).toBeTruthy();
    // 确认门边界如实告知:配方不绕确认
    expect(getByText(/敏感步骤仍会逐条要你确认/)).toBeTruthy();
  });

  it('submits name + trigger phrase and shows the saved state', async () => {
    mockSaveRecipeFromConversation.mockResolvedValue({
      id: 7,
      name: '早餐套餐',
      trigger_phrases: ['早餐套餐打卡'],
      steps: [],
      created_from_conversation_id: 42,
      use_count: 0,
      created_at: null,
    });
    const { getByLabelText, getByTestId } = render(<SaveRecipeCardView {...CARD_DATA} />);

    fireEvent.press(getByLabelText('存为配方'));
    fireEvent.changeText(getByLabelText('配方名称'), '早餐套餐');
    fireEvent.changeText(getByLabelText('触发短语'), '早餐套餐打卡');
    fireEvent.press(getByLabelText('确认保存配方'));

    await waitFor(() => expect(getByTestId('save-recipe-saved')).toBeTruthy());
    expect(mockSaveRecipeFromConversation).toHaveBeenCalledWith(42, {
      name: '早餐套餐',
      trigger_phrases: ['早餐套餐打卡'],
    });
  });

  it('keeps the submit button disabled until both fields are valid', () => {
    const { getByLabelText } = render(<SaveRecipeCardView {...CARD_DATA} />);

    fireEvent.press(getByLabelText('存为配方'));
    fireEvent.press(getByLabelText('确认保存配方'));
    expect(mockSaveRecipeFromConversation).not.toHaveBeenCalled();

    // 触发短语 <2 字仍不可提交(误触发护栏与后端一致)
    fireEvent.changeText(getByLabelText('配方名称'), '早餐套餐');
    fireEvent.changeText(getByLabelText('触发短语'), '好');
    fireEvent.press(getByLabelText('确认保存配方'));
    expect(mockSaveRecipeFromConversation).not.toHaveBeenCalled();
  });

  it('surfaces the backend rejection detail instead of pretending success', async () => {
    mockSaveRecipeFromConversation.mockRejectedValue({
      response: { data: { detail: '触发短语「早餐套餐打卡」已被配方「旧配方」占用' } },
    });
    const { getByLabelText, getByTestId, queryByTestId } = render(
      <SaveRecipeCardView {...CARD_DATA} />,
    );

    fireEvent.press(getByLabelText('存为配方'));
    fireEvent.changeText(getByLabelText('配方名称'), '早餐套餐');
    fireEvent.changeText(getByLabelText('触发短语'), '早餐套餐打卡');
    fireEvent.press(getByLabelText('确认保存配方'));

    await waitFor(() =>
      expect(getByTestId('save-recipe-error').props.children).toContain('已被配方'),
    );
    expect(queryByTestId('save-recipe-saved')).toBeNull();
  });
});
