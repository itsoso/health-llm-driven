import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';
import { StyleSheet } from 'react-native';

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
  it('uses 小巴 as the visible assistant persona', () => {
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

    expect(getByText('小巴')).toBeTruthy();
    expect(queryByText('健康 Agent')).toBeNull();
  });

  it('renders the header 小巴 title with stronger brand scale', () => {
    const onSelect = jest.fn();
    const { getByLabelText, getByTestId, getByText } = render(
      <LlmModelPicker
        variant="header"
        currentLabel="Qwen3.7 Plus"
        currentModelId="qwen3.7-plus"
        options={options}
        savingModelId={null}
        onSelect={onSelect}
      />,
    );

    const titleStyle = StyleSheet.flatten(getByText('小巴').props.style);
    const triggerStyle = StyleSheet.flatten(
      getByLabelText('切换 AI 模型，当前 Qwen3.7 Plus').props.style,
    );
    expect(titleStyle).toEqual(expect.objectContaining({ fontSize: 20, lineHeight: 25 }));
    expect(getByTestId('icon-chevron-down').props.size).toBe(12);
    expect(triggerStyle.minHeight).toBeGreaterThanOrEqual(44);
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
