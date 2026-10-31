import React from 'react';
import { render, fireEvent } from '@testing-library/react-native';
import { StyleSheet } from 'react-native';

import ChatHeader from '../ChatHeader';
import { revaColors as C } from '../../../constants/revaTheme';

describe('ChatHeader', () => {
  it('shows a source return action for contextual health discussions', () => {
    const onBack = jest.fn();
    const { getByLabelText } = render(
      <ChatHeader
        activeLlmLabel="Qwen3.7 Plus"
        llmModelId="qwen3.7-plus"
        llmOptions={[]}
        llmSaving={null}
        llmError={null}
        isStreaming={false}
        onBack={onBack}
        onSelectModel={jest.fn()}
        onNewChat={jest.fn()}
        onOpenHistory={jest.fn()}
        onOpenToolMenu={jest.fn()}
      />,
    );

    fireEvent.press(getByLabelText('返回上一页'));
    expect(onBack).toHaveBeenCalledTimes(1);
  });

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

    const avatarStyle = StyleSheet.flatten(getByLabelText('小气候形象').props.style);
    const titleStyle = StyleSheet.flatten(getByText('小气候').props.style);
    expect(avatarStyle).toEqual(expect.objectContaining({ width: 32, height: 32 }));
    expect(titleStyle).toEqual(expect.objectContaining({ fontSize: 20, lineHeight: 25 }));
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

  it('offers compact accessible actions for new chat, history and more', () => {
    const onNewChat = jest.fn();
    const onOpenHistory = jest.fn();
    const onOpenToolMenu = jest.fn();
    const { getByTestId, getByLabelText, queryByText, queryByTestId, queryByLabelText } = render(
      <ChatHeader
        activeLlmLabel="Qwen3.7 Plus"
        llmModelId="qwen3.7-plus"
        llmOptions={[]}
        llmSaving={null}
        llmError={null}
        isStreaming={false}
        onSelectModel={jest.fn()}
        onNewChat={onNewChat}
        onOpenHistory={onOpenHistory}
        onOpenToolMenu={onOpenToolMenu}
      />,
    );

    expect(queryByTestId('icon-pulse')).toBeNull();
    expect(queryByTestId('chat-header-voice')).toBeNull();
    expect(queryByText('语音')).toBeNull();
    expect(queryByLabelText('实时语音')).toBeNull();
    expect(getByLabelText('新建对话')).toBeTruthy();
    expect(queryByText('新对话')).toBeNull();
    expect(queryByTestId('icon-add')).toBeNull();
    expect(getByTestId('icon-ellipsis-horizontal')).toBeTruthy();

    expect(StyleSheet.flatten(getByLabelText('对话历史').props.style)).toEqual(
      expect.objectContaining({ width: 44, height: 44 }),
    );
    expect(StyleSheet.flatten(getByLabelText('更多会诊操作').props.style)).toEqual(
      expect.objectContaining({ width: 44, height: 44 }),
    );
    expect(StyleSheet.flatten(getByTestId('chat-header-action-group').props.style)).toEqual(
      expect.objectContaining({ backgroundColor: 'transparent' }),
    );
    expect(StyleSheet.flatten(getByTestId('chat-header-new-visual').props.style)).toEqual(
      expect.objectContaining({ backgroundColor: C.green50 }),
    );
    expect(StyleSheet.flatten(getByTestId('chat-header-new-visual').props.style)).toEqual(
      expect.objectContaining({ width: 36, height: 36 }),
    );

    fireEvent.press(getByLabelText('新建对话'));
    expect(onNewChat).toHaveBeenCalledTimes(1);
    fireEvent.press(getByLabelText('对话历史'));
    expect(onOpenHistory).toHaveBeenCalledTimes(1);
    fireEvent.press(getByLabelText('更多会诊操作'));
    expect(onOpenToolMenu).toHaveBeenCalledTimes(1);
  });
});
