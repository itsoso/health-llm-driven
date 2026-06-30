import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';

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

describe('Mobile LlmModelPicker', () => {
  it('uses 阿衡 as the visible assistant persona', () => {
    const onSelect = jest.fn();
    const { getByText, queryByText } = render(
      <LlmModelPicker
        currentLabel="Qwen3.7 Plus"
        currentModelId="qwen3.7-plus"
        options={options}
        savingModelId={null}
        onSelect={onSelect}
      />,
    );

    expect(getByText('阿衡')).toBeTruthy();
    expect(queryByText('健康 Agent')).toBeNull();
  });

  it('opens options and selects a model inline', () => {
    const onSelect = jest.fn();
    const { getByLabelText, getByText } = render(
      <LlmModelPicker
        currentLabel="Qwen3.7 Plus"
        currentModelId="qwen3.7-plus"
        options={options}
        savingModelId={null}
        onSelect={onSelect}
      />,
    );

    fireEvent.press(getByLabelText('切换 AI 模型，当前 Qwen3.7 Plus'));
    fireEvent.press(getByText('MiniMax M2.5'));

    expect(onSelect).toHaveBeenCalledWith('minimax-m2.5');
  });

  it('stays openable while a reply is streaming', () => {
    const onSelect = jest.fn();
    const { getByLabelText, getByText } = render(
      <LlmModelPicker
        currentLabel="Qwen3.7 Plus"
        currentModelId="qwen3.7-plus"
        options={options}
        savingModelId={null}
        disabled
        onSelect={onSelect}
      />,
    );

    fireEvent.press(getByLabelText('切换 AI 模型，当前 Qwen3.7 Plus'));
    fireEvent.press(getByText('MiniMax M2.5'));

    expect(onSelect).toHaveBeenCalledWith('minimax-m2.5');
  });

  it('hides lower-version models from stale option payloads', () => {
    const onSelect = jest.fn();
    const { getByLabelText, queryByText } = render(
      <LlmModelPicker
        currentLabel="Qwen3.7 Plus"
        currentModelId="qwen3.7-plus"
        options={options}
        savingModelId={null}
        onSelect={onSelect}
      />,
    );

    fireEvent.press(getByLabelText('切换 AI 模型，当前 Qwen3.7 Plus'));

    expect(queryByText('Qwen3.6 Plus')).toBeNull();
  });
});
