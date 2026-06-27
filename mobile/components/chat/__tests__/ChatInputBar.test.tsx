/* eslint-disable @typescript-eslint/no-require-imports */
import React from 'react';
import { StyleSheet } from 'react-native';
import { fireEvent, render } from '@testing-library/react-native';

import ChatInputBar from '../ChatInputBar';
import { revaColors } from '../../../constants/revaTheme';

const mockStartRecording = jest.fn();

jest.mock('../../../hooks/useMediaPicker', () => ({
  useMediaPicker: () => ({
    pendingImages: [],
    removeImage: jest.fn(),
    clearImages: jest.fn(),
    pickImage: jest.fn(),
    takePhoto: jest.fn(),
  }),
}));

jest.mock('../../../hooks/useVoiceRecording', () => ({
  useVoiceRecording: () => ({
    isRecording: false,
    isTranscribing: false,
    durationMs: 0,
    startRecording: mockStartRecording,
    stopAndTranscribe: jest.fn(),
    cancelRecording: jest.fn(),
  }),
}));

jest.mock('expo-document-picker', () => ({
  getDocumentAsync: jest.fn(),
}));

jest.mock('expo-router', () => ({
  router: { push: jest.fn() },
}));

jest.mock('react-native-reanimated', () => {
  const React = require('react');
  const { View } = require('react-native');
  const AnimatedView = React.forwardRef((props: any, ref: any) => React.createElement(View, { ...props, ref }));
  AnimatedView.displayName = 'AnimatedView';
  return {
    __esModule: true,
    default: { View: AnimatedView },
    useSharedValue: (value: unknown) => ({ value }),
    useAnimatedStyle: (factory: () => unknown) => factory(),
    withRepeat: (value: unknown) => value,
    withTiming: (value: unknown) => value,
    withSpring: (value: unknown) => value,
  };
});

describe('ChatInputBar', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('uses Reva surface color for the attachment menu sheet', () => {
    const { getByLabelText, getByTestId } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    fireEvent.press(getByLabelText('附件菜单'));

    expect(StyleSheet.flatten(getByTestId('attachment-menu-sheet').props.style).backgroundColor)
      .toBe(revaColors.surface);
  });

  it('uses the bottom microphone for voice input instead of voice conversation', () => {
    const { getByLabelText } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    fireEvent.press(getByLabelText('语音输入'));
    fireEvent(getByLabelText('按住说话'), 'pressIn', { nativeEvent: { pageY: 300 } });

    expect(mockStartRecording).toHaveBeenCalled();
  });
});
