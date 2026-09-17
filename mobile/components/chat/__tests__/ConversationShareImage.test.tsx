import React from 'react';
import { act, fireEvent, render } from '@testing-library/react-native';
import { StyleSheet } from 'react-native';

import ConversationShareImage, { SHARE_IMAGE_LOAD_TIMEOUT_MS } from '../ConversationShareImage';
import MarkdownText from '../../shared/MarkdownText';
import { colors } from '../../../constants/theme';

const makeImageLoadEvent = () => ({
  nativeEvent: {
    source: { url: 'https://example.test/image.png', width: 100, height: 100 },
    cacheType: 'none',
  },
});

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

  it('embeds attached and markdown images as export tiles with auth headers', () => {
    const view = render(
      <ConversationShareImage
        imageAuthToken="token-1"
        messages={[
          {
            id: 'user-1',
            role: 'user',
            content: '午餐',
            imageUris: ['https://health.executor.life/api/v1/upload/files/chat/1/meal.jpg'],
          },
          {
            id: 'assistant-1',
            role: 'assistant',
            content: '![睡眠趋势](https://example.test/sleep.png)\n\n整体不错。',
          },
        ]}
      />,
    );

    expect(view.getByTestId('share-image-user-1-0').props.source).toEqual([{
      uri: 'https://health.executor.life/api/v1/upload/files/chat/1/meal.jpg',
      headers: { Authorization: 'Bearer token-1' },
    }]);
    expect(view.getByTestId('share-image-assistant-1-0').props.source).toEqual([{
      uri: 'https://example.test/sleep.png',
    }]);
    expect(view.getByText('整体不错。')).toBeTruthy();
  });

  it('waits for every export image to load before reporting readiness', () => {
    const onReady = jest.fn();
    const view = render(
      <ConversationShareImage
        messages={[{
          id: 'user-1',
          role: 'user',
          content: '午餐',
          imageUris: ['https://example.test/a.png', 'https://example.test/b.png'],
        }]}
        onReady={onReady}
      />,
    );

    fireEvent(view.getByTestId('conversation-share-image'), 'layout', {
      nativeEvent: { layout: { x: 0, y: 0, width: 360, height: 900 } },
    });
    expect(onReady).not.toHaveBeenCalled();

    fireEvent(view.getByTestId('share-image-user-1-0'), 'load', makeImageLoadEvent());
    expect(onReady).not.toHaveBeenCalled();

    fireEvent(view.getByTestId('share-image-user-1-1'), 'load', makeImageLoadEvent());
    expect(onReady).toHaveBeenCalledTimes(1);
  });

  it('keeps the export moving with a visible placeholder when an image fails', () => {
    const onReady = jest.fn();
    const view = render(
      <ConversationShareImage
        messages={[{
          id: 'user-1',
          role: 'user',
          content: '午餐',
          imageUris: ['https://example.test/a.png'],
        }]}
        onReady={onReady}
      />,
    );

    fireEvent(view.getByTestId('conversation-share-image'), 'layout', {
      nativeEvent: { layout: { x: 0, y: 0, width: 360, height: 900 } },
    });
    fireEvent(view.getByTestId('share-image-user-1-0'), 'error', { nativeEvent: { error: 'boom' } });

    expect(view.getByTestId('share-image-failed-user-1-0')).toBeTruthy();
    expect(view.getByText('图片加载失败')).toBeTruthy();
    expect(onReady).toHaveBeenCalledTimes(1);
  });

  it('falls back to visible placeholders when export images never settle', () => {
    jest.useFakeTimers();
    try {
      const onReady = jest.fn();
      const view = render(
        <ConversationShareImage
          messages={[{
            id: 'user-1',
            role: 'user',
            content: '午餐',
            imageUris: ['https://example.test/a.png'],
          }]}
          onReady={onReady}
        />,
      );

      fireEvent(view.getByTestId('conversation-share-image'), 'layout', {
        nativeEvent: { layout: { x: 0, y: 0, width: 360, height: 900 } },
      });
      expect(onReady).not.toHaveBeenCalled();

      act(() => {
        jest.advanceTimersByTime(SHARE_IMAGE_LOAD_TIMEOUT_MS);
      });

      expect(view.getByTestId('share-image-failed-user-1-0')).toBeTruthy();
      expect(onReady).toHaveBeenCalledTimes(1);
    } finally {
      jest.useRealTimers();
    }
  });
});
