// @vitest-environment jsdom

import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import LlmModelPicker, { ModelOption } from '../LlmModelPicker';

const options: ModelOption[] = [
  {
    id: 'qwen3.7-plus',
    label: 'Qwen3.7 Plus',
    provider: 'tokenplan',
    model: 'qwen3.7-plus',
    speed_tier: 'reasoning',
    note: '千问最新多模态模型',
  },
  {
    id: 'minimax-m2.5',
    label: 'MiniMax M2.5',
    provider: 'tokenplan',
    model: 'MiniMax-M2.5',
    speed_tier: 'reasoning',
    note: 'MiniMax 最新推理模型',
  },
  {
    id: 'qwen3.6-plus',
    label: 'Qwen3.6 Plus',
    provider: 'tokenplan',
    model: 'qwen3.6-plus',
    speed_tier: 'reasoning',
    note: '旧版本, 不应展示',
  },
];

describe('LlmModelPicker', () => {
  it('opens options and selects a model without page navigation', () => {
    const onSelect = vi.fn();
    render(
      <LlmModelPicker
        currentLabel="Qwen3.7 Plus"
        currentModelId="qwen3.7-plus"
        options={options}
        savingModelId={null}
        disabled={false}
        onSelect={onSelect}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /当前模型/ }));
    fireEvent.click(screen.getByRole('button', { name: /MiniMax M2.5/ }));

    expect(onSelect).toHaveBeenCalledWith('minimax-m2.5');
  });

  it('renders the dropdown above assistant page content', () => {
    render(
      <LlmModelPicker
        currentLabel="Qwen3.7 Plus"
        currentModelId="qwen3.7-plus"
        options={options}
        savingModelId={null}
        disabled={false}
        onSelect={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /当前模型/ }));

    expect(screen.getByTestId('llm-model-picker-menu')).toHaveClass('z-[80]');
  });

  it('hides lower-version models from stale option payloads', () => {
    render(
      <LlmModelPicker
        currentLabel="Qwen3.7 Plus"
        currentModelId="qwen3.7-plus"
        options={options}
        savingModelId={null}
        disabled={false}
        onSelect={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /当前模型/ }));

    expect(screen.queryByText('Qwen3.6 Plus')).toBeNull();
  });
});
