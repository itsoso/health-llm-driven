// @vitest-environment jsdom

import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
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

describe('LlmModelPicker', () => {
  it('opens options and selects a model without page navigation', () => {
    const onSelect = vi.fn();
    render(
      <LlmModelPicker
        currentLabel="Qwen Max"
        currentModelId="qwen-max"
        options={options}
        savingModelId={null}
        disabled={false}
        onSelect={onSelect}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /当前模型/ }));
    fireEvent.click(screen.getByRole('button', { name: /MiniMax M2.5/ }));

    expect(onSelect).toHaveBeenCalledWith('minimax-m25');
  });

  it('renders the dropdown above assistant page content', () => {
    render(
      <LlmModelPicker
        currentLabel="Qwen Max"
        currentModelId="qwen-max"
        options={options}
        savingModelId={null}
        disabled={false}
        onSelect={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /当前模型/ }));

    expect(screen.getByTestId('llm-model-picker-menu')).toHaveClass('z-[80]');
  });
});
