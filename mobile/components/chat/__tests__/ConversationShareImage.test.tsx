import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';
import { StyleSheet } from 'react-native';

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
});
