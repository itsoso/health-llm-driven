import React from 'react';
import { Text } from 'react-native';
import { fireEvent, render } from '@testing-library/react-native';

const mockSendMessage = jest.fn();
const mockRenderCard = jest.fn(() => <Text>动态卡片已渲染</Text>);
let mockIsStreaming = false;

jest.mock('expo-router', () => ({
  useFocusEffect: (callback: () => void | (() => void)) => callback(),
}));

jest.mock('../../../hooks/useChatEngine', () => ({
  useChatEngine: () => ({
    messages: [
      {
        id: 'card-1',
        role: 'assistant',
        content: '',
        cardType: 'vitals',
        cardData: { sleep: '8h' },
      },
    ],
    isStreaming: mockIsStreaming,
    sendMessage: mockSendMessage,
  }),
}));

jest.mock('../../chat/cards', () => ({
  renderCard: (...args: any[]) => mockRenderCard.apply(null, args),
}));

import { RevaAgentView } from '../RevaAgentView';

describe('RevaAgentView', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockIsStreaming = false;
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
});
