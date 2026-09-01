import React from 'react';
import { Text } from 'react-native';
import { fireEvent, render } from '@testing-library/react-native';

const mockSendMessage = jest.fn();
const mockRenderCard = jest.fn(() => <Text>动态卡片已渲染</Text>);
let mockIsStreaming = false;
let mockMessages: any[] = [];

jest.mock('expo-router', () => ({
  useFocusEffect: (callback: () => void | (() => void)) => callback(),
}));

jest.mock('../../../hooks/useChatEngine', () => ({
  useChatEngine: () => ({
    messages: mockMessages,
    isStreaming: mockIsStreaming,
    sendMessage: mockSendMessage,
  }),
}));

jest.mock('react-native-markdown-display', () => {
  const React = require('react');
  const { Text } = require('react-native');
  const MockMarkdown = ({ children }: { children: string }) => <Text>{children}</Text>;
  MockMarkdown.displayName = 'MockMarkdown';
  return MockMarkdown;
});

jest.mock('../../chat/cards', () => ({
  renderCard: (...args: any[]) => mockRenderCard.apply(null, args),
}));

import { RevaAgentView } from '../RevaAgentView';

describe('RevaAgentView', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockIsStreaming = false;
    mockMessages = [{
      id: 'card-1',
      role: 'assistant',
      content: '',
      cardType: 'vitals',
      cardData: { sleep: '8h' },
    }];
  });

  it('renders dynamic UI cards inside the standalone Reva chat surface', () => {
    const { getByTestId, getByText } = render(<RevaAgentView />);

    expect(getByText('动态卡片已渲染')).toBeTruthy();
    expect(getByTestId('reva-agent-transcript').props.keyboardShouldPersistTaps).toBe('always');
    expect(mockRenderCard).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'vitals', data: { sleep: '8h' } }),
    );
  });

  it('keeps the standalone 小巴 composer usable while a reply is streaming', () => {
    mockIsStreaming = true;
    const { getByPlaceholderText, getByLabelText } = render(<RevaAgentView />);

    const input = getByPlaceholderText('问问小巴…');
    fireEvent.changeText(input, '继续补充');
    fireEvent.press(getByLabelText('发送消息'));

    expect(mockSendMessage).toHaveBeenCalledWith('继续补充');
  });

  it('uses the canonical assistant normalizer for text and fenced cards', () => {
    mockMessages = [{
      id: 'normalized-1',
      role: 'assistant',
      content: [
        '第一段<br/>第二段',
        '```reva-ui',
        '{"v":1,"component":"line_chart","title":"趋势"}',
        '```',
      ].join('\n'),
    }];

    const { getByLabelText, getByText } = render(<RevaAgentView />);

    expect(getByText('第一段\n第二段')).toBeTruthy();
    expect(getByLabelText('AI: 第一段\n第二段')).toBeTruthy();
    expect(mockRenderCard).toHaveBeenCalledWith(expect.objectContaining({ type: 'line_chart' }));
  });
});
