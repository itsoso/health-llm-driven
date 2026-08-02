import React from 'react';
import { render, fireEvent } from '@testing-library/react-native';
import { StyleSheet } from 'react-native';

import ChatHeader from '../ChatHeader';

describe('ChatHeader', () => {
  it('shows 小巴 as a branded assistant avatar beside the header title', () => {
    const { getByLabelText, getByText } = render(
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

    const avatarStyle = StyleSheet.flatten(getByLabelText('小巴形象').props.style);
    const titleStyle = StyleSheet.flatten(getByText('小巴').props.style);
    expect(avatarStyle.width).toBeGreaterThanOrEqual(32);
    expect(avatarStyle.height).toBeGreaterThanOrEqual(32);
    expect(titleStyle.fontSize).toBeGreaterThanOrEqual(28);
    expect(titleStyle.lineHeight).toBeGreaterThanOrEqual(34);
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
    expect(StyleSheet.flatten(getByLabelText('新建对话').props.style).backgroundColor).toBeTruthy();
    expect(StyleSheet.flatten(getByLabelText('对话历史').props.style).borderWidth).toBeGreaterThan(0);
    expect(getByTestId('icon-pencil-outline')).toBeTruthy();
    expect(getByTestId('icon-time-outline')).toBeTruthy();
    expect(getByTestId('icon-settings-outline')).toBeTruthy();

    expect(StyleSheet.flatten(getByLabelText('新建对话').props.style)).toEqual(
      expect.objectContaining({ width: 44, height: 44 }),
    );
    expect(StyleSheet.flatten(getByLabelText('对话历史').props.style)).toEqual(
      expect.objectContaining({ width: 44, height: 44 }),
    );
    expect(StyleSheet.flatten(getByLabelText('更多会诊操作').props.style)).toEqual(
      expect.objectContaining({ width: 44, height: 44 }),
    );

    fireEvent.press(getByLabelText('更多会诊操作'));
    expect(onOpenToolMenu).toHaveBeenCalledTimes(1);
  });
});
