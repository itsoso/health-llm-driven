import React from 'react';
import { fireEvent, render, waitFor } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import type { UIMessage } from '../../../hooks/useChatEngine';

/* eslint-disable @typescript-eslint/no-require-imports */
const mockSpeak = jest.fn();
const mockStop = jest.fn();
const mockSetAudioModeAsync = jest.fn();
const mockSelectionAsync = jest.fn();
const mockSpeakWithUserVoice = jest.fn();

jest.mock('expo-speech', () => ({
  speak: (...args: any[]) => mockSpeak(...args),
  stop: (...args: any[]) => mockStop(...args),
}));

jest.mock('expo-audio', () => ({
  setAudioModeAsync: (...args: any[]) => mockSetAudioModeAsync(...args),
}));

jest.mock('expo-haptics', () => ({
  selectionAsync: (...args: any[]) => mockSelectionAsync(...args),
  notificationAsync: jest.fn(),
  NotificationFeedbackType: { Success: 'success' },
}));

jest.mock('../../../services/speakWithUserVoice', () => ({
  speakWithUserVoice: (...args: any[]) => mockSpeakWithUserVoice(...args),
}));

jest.mock('react-native-markdown-display', () => {
  const React = require('react');
  const { Text } = require('react-native');
  const MockMarkdown = ({ children }: { children: string }) => <Text>{children}</Text>;
  MockMarkdown.displayName = 'MockMarkdown';
  return MockMarkdown;
});

jest.mock('../BrandCircle', () => {
  const React = require('react');
  const { View } = require('react-native');
  const MockBrandCircle = ({ children }: any) => <View>{children}</View>;
  MockBrandCircle.displayName = 'MockBrandCircle';
  return MockBrandCircle;
});

jest.mock('../AttributionChips', () => {
  const React = require('react');
  const { View } = require('react-native');
  const MockAttributionChips = () => <View />;
  MockAttributionChips.displayName = 'MockAttributionChips';
  return {
    __esModule: true,
    default: MockAttributionChips,
    AttributionDetails: MockAttributionChips,
    normalizedAttributionCount: (sources?: unknown[]) => sources?.length || 0,
  };
});

jest.mock('../cards', () => ({
  renderCard: jest.fn(() => null),
}));

jest.mock('../../../services/actionCards', () => ({
  createInterventionDraft: jest.fn(),
}));

jest.mock('../../../services/interventionDraft', () => ({
  buildInterventionDraft: jest.fn(() => ({})),
}));

jest.mock('../../../utils/share', () => ({
  sharePlainText: jest.fn(),
}));

jest.mock('../../actions/InterventionDraftSheet', () => {
  const React = require('react');
  const { View } = require('react-native');
  const MockInterventionDraftSheet = () => <View />;
  MockInterventionDraftSheet.displayName = 'MockInterventionDraftSheet';
  return MockInterventionDraftSheet;
});

const ChatBubble = require('../ChatBubble').default;

const baseMessage: UIMessage = {
  id: 'assistant-1',
  role: 'assistant',
  content: '今天先做 20 分钟低强度有氧，睡前减少屏幕刺激。',
  streaming: false,
};

function renderBubble(message: UIMessage = baseMessage) {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <ChatBubble item={message} />
    </QueryClientProvider>,
  );
}

describe('ChatBubble speech playback', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockSetAudioModeAsync.mockResolvedValue(undefined);
    jest.spyOn(console, 'warn').mockImplementation(() => undefined);
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('recovers the speech button when native speech startup throws', async () => {
    mockSpeakWithUserVoice.mockRejectedValue(new Error('speech unavailable'));

    const { getByLabelText, getByTestId, queryByLabelText } = renderBubble();

    expect(queryByLabelText('语音播报')).toBeNull();
    // Completed replies with the evidence panel intentionally expose the body,
    // evidence, and utility actions as separate accessibility nodes. Trigger
    // the existing long-press gesture on the message surface without restoring
    // the old merged VoiceOver label.
    fireEvent(getByTestId('assistant-message-surface'), 'longPress');
    expect(() => fireEvent.press(getByLabelText('语音播报'))).not.toThrow();
    await waitFor(() => expect(mockSpeakWithUserVoice).toHaveBeenCalled());
  });
});
