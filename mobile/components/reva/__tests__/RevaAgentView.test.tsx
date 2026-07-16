import React from 'react';
import { Text } from 'react-native';
import { render } from '@testing-library/react-native';

const mockSendMessage = jest.fn();
const mockRenderCard = jest.fn(() => <Text>动态卡片已渲染</Text>);

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
    isStreaming: false,
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
  });

  it('renders dynamic UI cards inside the standalone Reva chat surface', () => {
    const { getByTestId, getByText } = render(<RevaAgentView />);

    expect(getByText('动态卡片已渲染')).toBeTruthy();
    expect(getByTestId('reva-agent-transcript').props.keyboardShouldPersistTaps).toBe('always');
    expect(mockRenderCard).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'vitals', data: { sleep: '8h' } }),
    );
  });
});
