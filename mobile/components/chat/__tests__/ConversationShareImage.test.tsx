import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';
import { Image, StyleSheet } from 'react-native';

import ConversationShareImage from '../ConversationShareImage';
import MarkdownText from '../../shared/MarkdownText';
import { colors } from '../../../constants/theme';

describe('ConversationShareImage', () => {
  it('reports readiness only after receiving a positive complete layout', () => {
    const onReady = jest.fn();
    const view = render(
      <ConversationShareImage
        messages={[{ id: 'assistant-1', role: 'assistant', content: '一段很长的回答' }]}
        onReady={onReady}
      />,
    );
    const canvas = view.getByTestId('conversation-share-image');

    fireEvent(canvas, 'layout', {
      nativeEvent: { layout: { x: 0, y: 0, width: 360, height: 0 } },
    });
    expect(onReady).not.toHaveBeenCalled();

    fireEvent(canvas, 'layout', {
      nativeEvent: { layout: { x: 0, y: 0, width: 360, height: 1800 } },
    });
    expect(onReady).toHaveBeenCalledTimes(1);
  });

  it('uses a fixed light palette for exported assistant markdown', () => {
    const view = render(
      <ConversationShareImage
        messages={[{ id: 'assistant-1', role: 'assistant', content: '## 饮食建议\n\n优先吃真实食物。' }]}
      />,
    );

    expect(view.UNSAFE_getByType(MarkdownText).props.palette).toBe(colors);
  });

  it('uses 小巴健康 on every exported brand surface', () => {
    const view = render(
      <ConversationShareImage
        messages={[{ id: 'assistant-1', role: 'assistant', content: '今晚早点休息。' }]}
      />,
    );

    expect(view.getByText('小巴健康 · 对话摘录')).toBeTruthy();
    expect(view.getByText('小巴健康')).toBeTruthy();
    expect(view.getByText('小巴健康 · 你忠实的健康参谋')).toBeTruthy();
    expect(view.queryByText('小巴')).toBeNull();
  });

  it('gives long assistant answers the full editorial card width', () => {
    const view = render(
      <ConversationShareImage
        messages={[
          { id: 'user-1', role: 'user', content: '今天怎么吃？' },
          { id: 'assistant-1', role: 'assistant', content: '这是一段较长的回答。' },
        ]}
      />,
    );

    const assistantCard = view.getByTestId('share-bubble-assistant-1');
    expect(StyleSheet.flatten(assistantCard.props.style)).toMatchObject({
      alignSelf: 'stretch',
      maxWidth: '100%',
    });
  });

  it('omits markdown images that would leave unloaded blank space in the export', () => {
    const getSize = jest.spyOn(Image, 'getSize').mockImplementation((_uri, success) => {
      success?.(100, 100);
    });
    const view = render(
      <ConversationShareImage
        messages={[{
          id: 'assistant-1',
          role: 'assistant',
          content: '![睡眠趋势](https://example.test/sleep.png)\n\n## 昨晚睡眠总结\n\n整体不错。',
        }]}
      />,
    );
    getSize.mockRestore();

    expect(view.UNSAFE_queryAllByType(Image)).toHaveLength(0);
    expect(view.getByText('昨晚睡眠总结')).toBeTruthy();
    expect(view.getByText('整体不错。')).toBeTruthy();
  });
});
