import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';

import ConversationShareImage from '../ConversationShareImage';

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
});
