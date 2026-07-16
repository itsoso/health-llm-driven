import React from 'react';
import { render, fireEvent } from '@testing-library/react-native';
import { StyleSheet } from 'react-native';

import ChatHeader from '../ChatHeader';

describe('ChatHeader', () => {
  it('shows 小巴 as a branded assistant avatar beside the header title', () => {
    const { getByLabelText } = render(
      <ChatHeader
        activeLlmLabel="Qwen3.7 Plus"
        llmModelId="qwen3.7-plus"
        llmOptions={[]}
        llmSaving={null}
        llmError={null}
        isStreaming={false}
        onSelectModel={jest.fn()}
        onNewChat={jest.fn()}
        onOpenHistory={jest.fn()}
        onOpenToolMenu={jest.fn()}
      />,
    );

    expect(getByLabelText('小巴形象')).toBeTruthy();
  });

  it('keeps streaming state inside the active assistant turn instead of the header', () => {
    const { queryByLabelText } = render(
      <ChatHeader
        activeLlmLabel="Qwen3.7 Plus"
        llmModelId="qwen3.7-plus"
        llmOptions={[]}
        llmSaving={null}
        llmError={null}
        isStreaming
        onSelectModel={jest.fn()}
        onNewChat={jest.fn()}
        onOpenHistory={jest.fn()}
        onOpenToolMenu={jest.fn()}
      />,
    );

    expect(queryByLabelText('回复中')).toBeNull();
  });

  it('groups new chat, history, and settings actions into one compact control', () => {
    const onOpenToolMenu = jest.fn();
    const { getByTestId, getByLabelText } = render(
      <ChatHeader
        activeLlmLabel="Qwen3.7 Plus"
        llmModelId="qwen3.7-plus"
        llmOptions={[]}
        llmSaving={null}
        llmError={null}
        isStreaming={false}
        onSelectModel={jest.fn()}
        onNewChat={jest.fn()}
        onOpenHistory={jest.fn()}
        onOpenToolMenu={onOpenToolMenu}
      />,
    );

    const groupStyle = StyleSheet.flatten(getByTestId('chat-header-action-group').props.style);
    expect(groupStyle.flexDirection).toBe('row');
    expect(groupStyle.borderRadius).toBeGreaterThanOrEqual(16);
    expect(groupStyle.padding).toBeGreaterThanOrEqual(2);
    expect(getByTestId('icon-pencil-outline')).toBeTruthy();
    expect(getByTestId('icon-time-outline')).toBeTruthy();
    expect(getByTestId('icon-settings-outline')).toBeTruthy();

    expect(StyleSheet.flatten(getByLabelText('新建对话').props.style).width).toBe(32);
    expect(StyleSheet.flatten(getByLabelText('对话历史').props.style).width).toBe(32);
    expect(StyleSheet.flatten(getByLabelText('更多会诊操作').props.style).width).toBe(32);

    fireEvent.press(getByLabelText('更多会诊操作'));
    expect(onOpenToolMenu).toHaveBeenCalledTimes(1);
  });
});
