/* eslint-disable @typescript-eslint/no-require-imports */
import React from 'react';
import { StyleSheet } from 'react-native';
import { act, fireEvent, render, waitFor } from '@testing-library/react-native';

import ChatInputBar from '../ChatInputBar';
import { revaColors } from '../../../constants/revaTheme';

const mockStartRecording = jest.fn();
const mockStopAndTranscribe = jest.fn();
const mockCancelRecording = jest.fn();
const mockPickImage = jest.fn();
const mockTakePhoto = jest.fn();
const mockClearImages = jest.fn();
const mockExecuteMedicalExamImport = jest.fn();
const mockStartDictation = jest.fn();
const mockStopDictation = jest.fn();
let latestVoiceRecordingOptions: any;
let latestRealtimeDictationOptions: any;
let mockRealtimeDictationState = {
  isDictating: false,
  error: null as string | null,
};

jest.mock('../../../hooks/useMediaPicker', () => ({
  useMediaPicker: () => ({
    pendingImages: [],
    removeImage: jest.fn(),
    clearImages: mockClearImages,
    pickImage: mockPickImage,
    takePhoto: mockTakePhoto,
  }),
}));

jest.mock('../../../hooks/useVoiceRecording', () => ({
  useVoiceRecording: (options: any) => {
    latestVoiceRecordingOptions = options;
    return {
      isRecording: false,
      isTranscribing: false,
      durationMs: 0,
      partialText: '',
      startRecording: mockStartRecording,
      stopAndTranscribe: mockStopAndTranscribe,
      cancelRecording: mockCancelRecording,
    };
  },
}));

jest.mock('../../../hooks/useRealtimeDictation', () => ({
  useRealtimeDictation: (options: any) => {
    latestRealtimeDictationOptions = options;
    return {
      isDictating: mockRealtimeDictationState.isDictating,
      error: mockRealtimeDictationState.error,
      startDictation: mockStartDictation,
      stopDictation: mockStopDictation,
    };
  },
}));

jest.mock('expo-document-picker', () => ({
  getDocumentAsync: jest.fn(),
}));

jest.mock('../../../services/chatMedicalExamImportSkill', () => ({
  executeMedicalExamImportSkillForDocumentAsset: (...args: any[]) => mockExecuteMedicalExamImport(...args),
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

const flattenedStyle = (node: any) => {
  const style = node.props.style;
  return StyleSheet.flatten(typeof style === 'function' ? style({ pressed: false }) : style);
};

describe('ChatInputBar', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    latestVoiceRecordingOptions = undefined;
    latestRealtimeDictationOptions = undefined;
    mockRealtimeDictationState = { isDictating: false, error: null };
  });

  it('uses Reva surface color for the attachment menu sheet', () => {
    const { getByLabelText, getByTestId } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    fireEvent.press(getByLabelText('附件菜单'));

    expect(StyleSheet.flatten(getByTestId('attachment-menu-sheet').props.style).backgroundColor)
      .toBe(revaColors.surface);
  });

  it('keeps the attachment menu sheet vertically tight', () => {
    const { getByLabelText, getByTestId } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    fireEvent.press(getByLabelText('附件菜单'));

    const menuSheet = StyleSheet.flatten(getByTestId('attachment-menu-sheet').props.style);
    expect(menuSheet.paddingTop).toBeLessThanOrEqual(8);
    expect(menuSheet.paddingBottom).toBeLessThanOrEqual(28);
  });

  it('keeps the attachment menu handle close to the action grid', () => {
    const { getByLabelText, getByTestId } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    fireEvent.press(getByLabelText('附件菜单'));

    const handle = StyleSheet.flatten(getByTestId('attachment-menu-handle').props.style);
    expect(handle.marginBottom).toBeLessThanOrEqual(10);
  });

  it('renders attachment actions as a compact two-column grid', () => {
    const { getByLabelText, getByTestId, getByText } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    fireEvent.press(getByLabelText('附件菜单'));

    const actionGrid = StyleSheet.flatten(getByTestId('attachment-action-grid').props.style);
    expect(actionGrid.flexDirection).toBe('row');
    expect(actionGrid.flexWrap).toBe('wrap');
    expect(actionGrid.gap).toBeLessThanOrEqual(8);
    expect(getByText('拍照')).toBeTruthy();
    expect(getByText('相册')).toBeTruthy();
    expect(getByText('文件')).toBeTruthy();
    expect(getByLabelText('导入体检报告')).toBeTruthy();
  });

  it('uses the media picker camera entry from the attachment menu', () => {
    const { getByLabelText } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    fireEvent.press(getByLabelText('附件菜单'));
    fireEvent.press(getByLabelText('拍照'));

    expect(mockTakePhoto).toHaveBeenCalled();
  });

  it('renders only one compact WeChat-style composer row by default', () => {
    const { getByTestId, queryByLabelText } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    const composerSurface = StyleSheet.flatten(getByTestId('chat-composer-surface').props.style);
    expect(composerSurface.backgroundColor).toBe('#1F1F1F');
    expect(composerSurface.borderRadius).toBeLessThanOrEqual(8);
    expect(queryByLabelText('Agent 模式')).toBeNull();
  });

  it('keyboard composer controls meet thumb ergonomics in the WeChat-style layout', () => {
    const { getByLabelText, getByTestId } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    expect(flattenedStyle(getByLabelText('附件菜单')).width).toBeGreaterThanOrEqual(40);
    expect(flattenedStyle(getByLabelText('按住说话')).width).toBeGreaterThanOrEqual(40);
    expect(flattenedStyle(getByTestId('wechat-composer-input')).minHeight).toBeGreaterThanOrEqual(48);
  });

  it('renders WeChat-style visible voice controls by default', () => {
    const { getByLabelText, getByTestId } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    expect(getByLabelText('按住说话')).toBeTruthy();
    expect(getByLabelText('实时语音转文字')).toBeTruthy();
    const inputSurface = flattenedStyle(getByTestId('wechat-composer-input'));
    expect(inputSurface.flexDirection).toBe('row');
    expect(inputSurface.borderRadius).toBeLessThanOrEqual(10);
  });

  it('keeps the empty field directly focusable because voice has its own left button', () => {
    const { getByLabelText } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    expect(StyleSheet.flatten(getByLabelText('消息输入框').props.style).pointerEvents).toBe('auto');
  });

  it('recovers a tappable, focusable field after a voice to blur cycle', () => {
    const { getByLabelText, getByTestId } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    const field = getByLabelText('消息输入框');
    fireEvent(field, 'focus');
    expect(StyleSheet.flatten(field.props.style).pointerEvents).toBe('auto');
    fireEvent(field, 'blur');
    expect(StyleSheet.flatten(field.props.style).pointerEvents).toBe('auto');

    fireEvent.press(getByTestId('wechat-composer-input'));
    fireEvent(field, 'focus');
    expect(StyleSheet.flatten(field.props.style).pointerEvents).toBe('auto');
  });

  it('starts hold-to-talk voice input from the left speaker button', () => {
    const { getByLabelText } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    fireEvent(getByLabelText('按住说话'), 'pressIn', { nativeEvent: { pageX: 220, pageY: 300 } });
    fireEvent(getByLabelText('按住说话'), 'pressOut');

    expect(mockStartRecording).toHaveBeenCalled();
    expect(mockStopAndTranscribe).toHaveBeenCalled();
  });

  it('cancels left hold-to-talk when the finger slides left', () => {
    const { getByLabelText } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    fireEvent(getByLabelText('按住说话'), 'pressIn', { nativeEvent: { pageX: 260, pageY: 620 } });
    fireEvent(getByLabelText('按住说话'), 'touchMove', { nativeEvent: { pageX: 120, pageY: 620 } });
    fireEvent(getByLabelText('按住说话'), 'pressOut');

    expect(mockCancelRecording).toHaveBeenCalled();
    expect(mockStopAndTranscribe).not.toHaveBeenCalled();
  });

  it('keeps left hold-to-talk transcript editable when the finger slides right', () => {
    const onSend = jest.fn();
    const { getByLabelText } = render(
      <ChatInputBar onSend={onSend} isStreaming={false} />,
    );

    fireEvent(getByLabelText('按住说话'), 'pressIn', { nativeEvent: { pageX: 160, pageY: 620 } });
    fireEvent(getByLabelText('按住说话'), 'touchMove', { nativeEvent: { pageX: 310, pageY: 620 } });
    fireEvent(getByLabelText('按住说话'), 'pressOut');
    act(() => {
      latestVoiceRecordingOptions.onTranscript('记录午餐吃了鸡胸肉');
    });

    expect(mockStopAndTranscribe).toHaveBeenCalled();
    expect(getByLabelText('消息输入框').props.value).toBe('记录午餐吃了鸡胸肉');
    expect(onSend).not.toHaveBeenCalled();
  });

  it('sends left hold-to-talk transcript by default on release', () => {
    const onSend = jest.fn();
    const { getByLabelText } = render(
      <ChatInputBar onSend={onSend} isStreaming={false} />,
    );

    fireEvent(getByLabelText('按住说话'), 'pressIn', { nativeEvent: { pageX: 160, pageY: 620 } });
    fireEvent(getByLabelText('按住说话'), 'pressOut');
    act(() => {
      latestVoiceRecordingOptions.onTranscript('今天走了八千步');
    });

    expect(onSend).toHaveBeenCalledWith('今天走了八千步', null);
  });

  it('keeps hold-to-talk transcript editable instead of sending while assistant is streaming', () => {
    const onSend = jest.fn();
    const { getByLabelText } = render(
      <ChatInputBar onSend={onSend} isStreaming={true} />,
    );

    fireEvent(getByLabelText('按住说话'), 'pressIn', { nativeEvent: { pageX: 160, pageY: 620 } });
    fireEvent(getByLabelText('按住说话'), 'pressOut');
    act(() => {
      latestVoiceRecordingOptions.onTranscript('先记到输入框');
    });

    expect(getByLabelText('消息输入框').props.value).toBe('先记到输入框');
    expect(onSend).not.toHaveBeenCalled();
  });

  it('starts realtime dictation from the microphone inside the input field', () => {
    const { getByLabelText } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    fireEvent.press(getByLabelText('实时语音转文字'));
    act(() => {
      latestRealtimeDictationOptions.onTranscript('记录今天喝水 500 毫升');
    });

    expect(mockStartDictation).toHaveBeenCalled();
    expect(getByLabelText('消息输入框').props.value).toBe('记录今天喝水 500 毫升');
  });

  it('stops realtime dictation from the active microphone button', () => {
    mockRealtimeDictationState = { isDictating: true, error: null };
    const { getByLabelText } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    const mic = getByLabelText('停止实时语音转文字');
    fireEvent.press(mic);

    expect(mic.props.accessibilityState).toEqual(expect.objectContaining({ selected: true }));
    expect(mockStopDictation).toHaveBeenCalled();
  });

  it('sends typed text when Enter is pressed in the composer', () => {
    const onSend = jest.fn();
    const { getByLabelText } = render(
      <ChatInputBar onSend={onSend} isStreaming={false} />,
    );

    fireEvent.changeText(getByLabelText('消息输入框'), '记录晚餐吃了鸡胸肉');
    fireEvent(getByLabelText('消息输入框'), 'keyPress', { nativeEvent: { key: 'Enter' } });

    expect(onSend).toHaveBeenCalledWith('记录晚餐吃了鸡胸肉', null);
  });

  it('stops realtime dictation before Enter submits the composer', () => {
    mockRealtimeDictationState = { isDictating: true, error: null };
    const onSend = jest.fn();
    const { getByLabelText } = render(
      <ChatInputBar onSend={onSend} isStreaming={false} />,
    );

    fireEvent.changeText(getByLabelText('消息输入框'), '听写完成的文字');
    fireEvent(getByLabelText('消息输入框'), 'keyPress', { nativeEvent: { key: 'Enter' } });

    expect(mockStopDictation).toHaveBeenCalled();
    expect(onSend).toHaveBeenCalledWith('听写完成的文字', null);
  });

  it('has no agent-mode segmented row', () => {
    const { getByLabelText, queryByText, queryByTestId } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    fireEvent.press(getByLabelText('附件菜单'));

    expect(queryByTestId('agent-mode-segmented-row')).toBeNull();
    expect(queryByText('深思')).toBeNull();
    expect(queryByText('识图')).toBeNull();
  });

  it('updates the composer when a follow-up prompt is injected after mount', () => {
    const { getByLabelText, rerender } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    rerender(
      <ChatInputBar
        onSend={jest.fn()}
        isStreaming={false}
        initialText="请基于上一条建议继续追问"
      />,
    );

    expect(getByLabelText('消息输入框').props.value).toBe('请基于上一条建议继续追问');
  });

  it('updates the composer when the same follow-up prompt is injected again', () => {
    const onSend = jest.fn();
    const prompt = '请基于上一条建议继续追问';
    const { getByLabelText, rerender } = render(
      <ChatInputBar
        onSend={onSend}
        isStreaming={false}
        initialText={prompt}
        initialTextKey={1}
      />,
    );

    fireEvent(getByLabelText('消息输入框'), 'keyPress', { nativeEvent: { key: 'Enter' } });
    expect(onSend).toHaveBeenCalledWith(prompt, null);
    expect(getByLabelText('消息输入框').props.value).toBe('');

    rerender(
      <ChatInputBar
        onSend={onSend}
        isStreaming={false}
        initialText={prompt}
        initialTextKey={2}
      />,
    );

    expect(getByLabelText('消息输入框').props.value).toBe(prompt);
  });

  it('runs the medical exam import skill from the attachment menu', async () => {
    const DocumentPicker = require('expo-document-picker');
    DocumentPicker.getDocumentAsync.mockResolvedValueOnce({
      canceled: false,
      assets: [{
        uri: 'file:///tmp/report.pdf',
        name: 'report.pdf',
        mimeType: 'application/pdf',
      }],
    });
    const skillResult = {
      skillId: 'medical_exam_import',
      card: {
        type: 'medical_exam_import_result',
        data: { exam_id: 42, items_count: 28, review_required: true },
      },
    };
    mockExecuteMedicalExamImport.mockResolvedValueOnce(skillResult);
    const onMedicalExamImportResult = jest.fn();

    const { getByLabelText } = render(
      <ChatInputBar
        onSend={jest.fn()}
        isStreaming={false}
        onMedicalExamImportResult={onMedicalExamImportResult}
      />,
    );

    fireEvent.press(getByLabelText('附件菜单'));
    fireEvent.press(getByLabelText('导入体检报告'));
    fireEvent.press(getByLabelText('选择 PDF 或图片报告'));

    await waitFor(() => {
      expect(mockExecuteMedicalExamImport).toHaveBeenCalledWith({
        uri: 'file:///tmp/report.pdf',
        name: 'report.pdf',
        mimeType: 'application/pdf',
      });
    });
    expect(onMedicalExamImportResult).toHaveBeenCalledWith(skillResult);
  });
});
