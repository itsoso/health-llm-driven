import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';

import LlmModelPicker, { ModelOption } from '../LlmModelPicker';

const options: ModelOption[] = [
  {
    id: 'qwen-max',
    label: 'Qwen Max',
    provider: 'tokenplan',
    model: 'qwen-max',
    speed_tier: 'balanced',
    note: '均衡模型',
  },
  {
    id: 'minimax-m25',
    label: 'MiniMax M2.5',
    provider: 'tokenplan',
    model: 'minimax-m25',
    speed_tier: 'fast',
    note: '快速回复',
  },
];

describe('Mobile LlmModelPicker', () => {
  it('opens options and selects a model inline', () => {
    const onSelect = jest.fn();
    const { getByLabelText, getByText } = render(
      <LlmModelPicker
        currentLabel="Qwen Max"
        currentModelId="qwen-max"
        options={options}
        savingModelId={null}
        onSelect={onSelect}
      />,
    );

    fireEvent.press(getByLabelText('切换 AI 模型，当前 Qwen Max'));
    fireEvent.press(getByText('MiniMax M2.5'));

    expect(onSelect).toHaveBeenCalledWith('minimax-m25');
  });
});
