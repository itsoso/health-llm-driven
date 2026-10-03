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
        onOpenVoice={jest.fn()}
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
        onOpenVoice={jest.fn()}
        onOpenHistory={jest.fn()}
        onOpenToolMenu={jest.fn()}
      />,
    );

    const avatarStyle = StyleSheet.flatten(getByLabelText('小巴形象').props.style);
    const titleStyle = StyleSheet.flatten(getByText('小巴').props.style);
    expect(avatarStyle).toEqual(expect.objectContaining({ width: 22, height: 22 }));
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
        onOpenVoice={jest.fn()}
        onOpenHistory={jest.fn()}
        onOpenToolMenu={jest.fn()}
      />,
    );

    expect(queryByLabelText('回复中')).toBeNull();
  });

  it('makes labelled voice visually primary and represents more actions without a settings gear', () => {
    const onOpenToolMenu = jest.fn();
    const onOpenVoice = jest.fn();
    const { getByTestId, getByLabelText, getByText, queryByLabelText } = render(
      <ChatHeader
        activeLlmLabel="Qwen3.7 Plus"
        llmModelId="qwen3.7-plus"
        llmOptions={[]}
        llmSaving={null}
        llmError={null}
        isStreaming={false}
        onSelectModel={jest.fn()}
        onOpenHistory={jest.fn()}
        onOpenVoice={onOpenVoice}
        onOpenToolMenu={onOpenToolMenu}
      />,
    );

    const wrapStyle = StyleSheet.flatten(getByTestId('chat-header-wrap').props.style);
    const groupStyle = StyleSheet.flatten(getByTestId('chat-header-action-group').props.style);
    expect(wrapStyle).toEqual(expect.objectContaining({ paddingTop: 8, paddingBottom: 2 }));
    expect(groupStyle.flexDirection).toBe('row');
    expect(groupStyle.borderRadius).toBeGreaterThanOrEqual(16);
    expect(groupStyle.minHeight).toBe(40);
    expect(groupStyle.padding).toBe(2);
    expect(getByTestId('icon-pulse')).toBeTruthy();
    expect(getByText('语音')).toBeTruthy();
    expect(queryByLabelText('新建对话')).toBeNull();
    expect(getByTestId('icon-time-outline')).toBeTruthy();
    expect(getByTestId('icon-ellipsis-horizontal')).toBeTruthy();

    expect(StyleSheet.flatten(getByLabelText('实时语音').props.style)).toEqual(
      expect.objectContaining({
        minHeight: 44,
        backgroundColor: C.green600,
        borderWidth: 0,
      }),
    );
    expect(getByLabelText('实时语音').props.hitSlop).toBe(8);
    expect(StyleSheet.flatten(getByLabelText('对话历史').props.style)).toEqual(
      expect.objectContaining({ width: 44, height: 44 }),
    );
    expect(getByTestId('icon-pulse').props.size).toBe(18);
    fireEvent.press(getByLabelText('实时语音'));
    expect(onOpenVoice).toHaveBeenCalledTimes(1);
    expect(getByTestId('icon-time-outline').props.size).toBe(18);
    expect(getByTestId('icon-ellipsis-horizontal').props.size).toBe(18);
    expect(StyleSheet.flatten(getByLabelText('更多会诊操作').props.style)).toEqual(
      expect.objectContaining({ width: 44, height: 44 }),
    );

    fireEvent.press(getByLabelText('更多会诊操作'));
    expect(onOpenToolMenu).toHaveBeenCalledTimes(1);
  });
});
