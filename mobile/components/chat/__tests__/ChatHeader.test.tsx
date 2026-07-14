import React from 'react';
import { render } from '@testing-library/react-native';

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
});
