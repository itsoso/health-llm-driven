import React from 'react';
import { render, fireEvent } from '@testing-library/react-native';
import { StyleSheet } from 'react-native';

import ChatHeader from '../ChatHeader';
import { revaColors as C } from '../../../constants/revaTheme';

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
        onNewChat={jest.fn()}
        onOpenHistory={jest.fn()}
        onOpenToolMenu={jest.fn()}
      />,
    );

    expect(queryByLabelText('回复中')).toBeNull();
  });

  it('makes new chat visually primary and represents more actions without a settings gear', () => {
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

    const wrapStyle = StyleSheet.flatten(getByTestId('chat-header-wrap').props.style);
    const groupStyle = StyleSheet.flatten(getByTestId('chat-header-action-group').props.style);
    expect(wrapStyle).toEqual(expect.objectContaining({ paddingTop: 8, paddingBottom: 2 }));
    expect(groupStyle.flexDirection).toBe('row');
    expect(groupStyle.borderRadius).toBeGreaterThanOrEqual(16);
    expect(groupStyle.minHeight).toBe(40);
    expect(groupStyle.padding).toBe(2);
    expect(getByTestId('icon-chatbubble-outline')).toBeTruthy();
    expect(getByTestId('icon-add')).toBeTruthy();
    expect(getByTestId('icon-time-outline')).toBeTruthy();
    expect(getByTestId('icon-ellipsis-horizontal')).toBeTruthy();

    expect(StyleSheet.flatten(getByLabelText('新建对话').props.style)).toEqual(
      expect.objectContaining({
        width: 40,
        height: 40,
        backgroundColor: C.green50,
        borderWidth: 0,
      }),
    );
    expect(getByLabelText('新建对话').props.hitSlop).toBe(4);
    expect(StyleSheet.flatten(getByLabelText('对话历史').props.style)).toEqual(
      expect.objectContaining({ width: 40, height: 40 }),
    );
    expect(getByTestId('icon-chatbubble-outline').props.size).toBe(18);
    expect(getByTestId('icon-add').props.size).toBe(9);
    expect(getByTestId('icon-time-outline').props.size).toBe(18);
    expect(getByTestId('icon-ellipsis-horizontal').props.size).toBe(18);
    expect(StyleSheet.flatten(getByLabelText('更多会诊操作').props.style)).toEqual(
      expect.objectContaining({ width: 40, height: 40 }),
    );

    fireEvent.press(getByLabelText('更多会诊操作'));
    expect(onOpenToolMenu).toHaveBeenCalledTimes(1);
  });
});
