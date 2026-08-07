import React from 'react';
import { render, fireEvent } from '@testing-library/react-native';
import { StyleSheet } from 'react-native';

import ChatHeader from '../ChatHeader';

describe('ChatHeader', () => {
  it('keeps the branded assistant identity compact in the header', () => {
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
    expect(avatarStyle).toEqual(expect.objectContaining({ width: 30, height: 30 }));
    expect(titleStyle).toEqual(expect.objectContaining({ fontSize: 24, lineHeight: 30 }));
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
    expect(groupStyle.minHeight).toBe(44);
    expect(groupStyle.padding).toBe(2);
    expect(getByTestId('icon-pencil-outline')).toBeTruthy();
    expect(getByTestId('icon-time-outline')).toBeTruthy();
    expect(getByTestId('icon-settings-outline')).toBeTruthy();

    expect(StyleSheet.flatten(getByLabelText('新建对话').props.style)).toEqual(
      expect.objectContaining({
        width: 44,
        height: 44,
        backgroundColor: 'transparent',
        borderWidth: 0,
      }),
    );
    expect(StyleSheet.flatten(getByLabelText('对话历史').props.style)).toEqual(
      expect.objectContaining({ width: 44, height: 44 }),
    );
    expect(getByTestId('icon-pencil-outline').props.size).toBe(19);
    expect(getByTestId('icon-time-outline').props.size).toBe(19);
    expect(getByTestId('icon-settings-outline').props.size).toBe(19);
    expect(StyleSheet.flatten(getByLabelText('更多会诊操作').props.style)).toEqual(
      expect.objectContaining({ width: 44, height: 44 }),
    );

    fireEvent.press(getByLabelText('更多会诊操作'));
    expect(onOpenToolMenu).toHaveBeenCalledTimes(1);
  });
});
