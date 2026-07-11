/* eslint-disable @typescript-eslint/no-require-imports */
import React from 'react';
import { Alert, AppState, StyleSheet } from 'react-native';
import { act, fireEvent, render, waitFor } from '@testing-library/react-native';

import ChatInputBar from '../ChatInputBar';
import { revaColors } from '../../../constants/revaTheme';

const mockStartRecording = jest.fn();
const mockStopAndTranscribe = jest.fn();
const mockCancelRecording = jest.fn();
const mockPickImage = jest.fn();
const mockTakePhoto = jest.fn();
const mockExecuteMedicalExamImport = jest.fn();
const mockStartDictation = jest.fn();
const mockStopDictation = jest.fn();
const mockCancelDictation = jest.fn();
let appStateHandler: ((state: string) => void) | undefined;
let latestVoiceRecordingOptions: any;
let latestRealtimeDictationOptions: any;
let mockVoiceRecordingState = {
  isRecording: false,
  isTranscribing: false,
  durationMs: 0,
  partialText: '',
};
let mockRealtimeDictationState = {
  isDictating: false,
  error: null as string | null,
};
let mockPendingImages: any[] = [];
const mockSetPendingImages = jest.fn();
const mockRemoveImage = jest.fn();
const mockClearImages = jest.fn().mockResolvedValue(undefined);
const mockReleaseImagesAfterSend = jest.fn();
const mockLoadChatDraft = jest.fn();
const mockPersistChatDraft = jest.fn().mockResolvedValue(undefined);
const mockHydrateDraftImages = jest.fn();
const mockClearPersistedChatDraft = jest.fn().mockResolvedValue(undefined);
const mockCleanupDraftFiles = jest.fn().mockResolvedValue(undefined);

jest.mock('../../../hooks/useMediaPicker', () => ({
  useMediaPicker: () => ({
    pendingImages: mockPendingImages,
    setPendingImages: mockSetPendingImages,
    removeImage: mockRemoveImage,
    clearImages: mockClearImages,
    releaseImagesAfterSend: mockReleaseImagesAfterSend,
    pickImage: mockPickImage,
    takePhoto: mockTakePhoto,
  }),
}));

jest.mock('../../../services/chatDraftStorage', () => ({
  loadChatDraft: (...args: any[]) => mockLoadChatDraft(...args),
  persistChatDraft: (...args: any[]) => mockPersistChatDraft(...args),
  hydrateDraftImagesForSend: (...args: any[]) => mockHydrateDraftImages(...args),
  clearPersistedChatDraft: (...args: any[]) => mockClearPersistedChatDraft(...args),
  cleanupAbandonedChatDraftFiles: (...args: any[]) => mockCleanupDraftFiles(...args),
}));

jest.mock('../../../hooks/useVoiceRecording', () => ({
  useVoiceRecording: (options: any) => {
    latestVoiceRecordingOptions = options;
    return {
      isRecording: mockVoiceRecordingState.isRecording,
      isTranscribing: mockVoiceRecordingState.isTranscribing,
      durationMs: mockVoiceRecordingState.durationMs,
      partialText: mockVoiceRecordingState.partialText,
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
      cancelDictation: mockCancelDictation,
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
    mockStartRecording.mockResolvedValue(true);
    mockStopAndTranscribe.mockResolvedValue(undefined);
    mockCancelRecording.mockResolvedValue(undefined);
    mockStartDictation.mockResolvedValue(true);
    mockStopDictation.mockResolvedValue(undefined);
    mockCancelDictation.mockResolvedValue(undefined);
    mockPendingImages = [];
    mockSetPendingImages.mockReset();
    mockClearImages.mockResolvedValue(undefined);
    mockLoadChatDraft.mockImplementation(() => new Promise(() => {}));
    mockPersistChatDraft.mockResolvedValue(undefined);
    mockHydrateDraftImages.mockImplementation(async (images: any[]) => images);
    mockClearPersistedChatDraft.mockResolvedValue(undefined);
    mockCleanupDraftFiles.mockResolvedValue(undefined);
    appStateHandler = undefined;
    jest.spyOn(AppState, 'addEventListener').mockImplementation(((_event: string, handler: (state: string) => void) => {
      appStateHandler = handler;
      return { remove: jest.fn() };
    }) as any);
    latestVoiceRecordingOptions = undefined;
    latestRealtimeDictationOptions = undefined;
    mockVoiceRecordingState = { isRecording: false, isTranscribing: false, durationMs: 0, partialText: '' };
    mockRealtimeDictationState = { isDictating: false, error: null };
  });

  afterEach(() => {
    jest.restoreAllMocks();
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
    const { getByLabelText, getByTestId } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    fireEvent.press(getByLabelText('附件菜单'));
    fireEvent.press(getByLabelText('拍照'));

    expect(mockTakePhoto).toHaveBeenCalled();
  });

  it('renders a warm-white composer coordinated with the page (not the old dark bar)', () => {
    const { getByTestId, queryByLabelText } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    const composerSurface = StyleSheet.flatten(getByTestId('chat-composer-surface').props.style);
    expect(composerSurface.backgroundColor).toBe(revaColors.paper);
    expect(composerSurface.backgroundColor).not.toBe('#1F1F1F');
    expect(composerSurface.borderRadius).toBeLessThanOrEqual(8);
    expect(queryByLabelText('Agent 模式')).toBeNull();
  });

  it('uses Reva warm surfaces for the mobile composer input instead of dark chrome', () => {
    const { getByLabelText, getByTestId } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    const styleOf = (node: any) => {
      const style = node.props.style;
      return StyleSheet.flatten(typeof style === 'function' ? style({ pressed: false }) : style);
    };

    const inputSurface = styleOf(getByTestId('wechat-composer-input'));
    const field = getByLabelText('消息输入框');
    const fieldStyle = StyleSheet.flatten(field.props.style);

    expect(inputSurface.backgroundColor).toBe(revaColors.surface);
    expect(inputSurface.backgroundColor).not.toBe('#2B2B2B');
    expect(inputSurface.borderColor).toBe(revaColors.line);
    expect(field.props.placeholderTextColor).toBe(revaColors.ink3);
    expect(fieldStyle.color).toBe(revaColors.ink1);
  });

  it('keyboard composer controls meet thumb ergonomics in the WeChat-style layout', () => {
    const { getByLabelText, getByTestId } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    const styleOf = (node: any) => {
      const style = node.props.style;
      return StyleSheet.flatten(typeof style === 'function' ? style({ pressed: false }) : style);
    };

    expect(styleOf(getByLabelText('附件菜单')).width).toBeGreaterThanOrEqual(40);
    expect(styleOf(getByLabelText('切换到语音输入')).width).toBeGreaterThanOrEqual(40);
    expect(StyleSheet.flatten(getByTestId('wechat-composer-input').props.style).minHeight).toBeGreaterThanOrEqual(48);
  });

  it('keeps the visible composer chrome slim while preserving touch targets', () => {
    const { getByLabelText, getByTestId } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    const styleOf = (node: any) => {
      const style = node.props.style;
      return StyleSheet.flatten(typeof style === 'function' ? style({ pressed: false }) : style);
    };
    const minHitSlop = (node: any) => Math.min(
      node.props.hitSlop?.top ?? 0,
      node.props.hitSlop?.right ?? 0,
      node.props.hitSlop?.bottom ?? 0,
      node.props.hitSlop?.left ?? 0,
    );

    // 2026-07-05 工学契约翻转: 拇指高度对齐 GPT — 场 ≥48, 钮 ≥40(hitSlop 补足 44 有效)
    expect(styleOf(getByLabelText('附件菜单')).width).toBeGreaterThanOrEqual(40);
    expect(styleOf(getByLabelText('切换到语音输入')).height).toBeGreaterThanOrEqual(40);
    expect(StyleSheet.flatten(getByTestId('wechat-composer-input').props.style).minHeight).toBeGreaterThanOrEqual(48);
    expect(minHitSlop(getByLabelText('附件菜单'))).toBeGreaterThanOrEqual(6);
  });

  it('renders WeChat-style text controls by default', () => {
    const { getByLabelText, getByTestId, queryByLabelText } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    expect(getByLabelText('切换到语音输入')).toBeTruthy();
    expect(getByLabelText('实时语音转文字')).toBeTruthy();
    expect(queryByLabelText('按住说话')).toBeNull();
    const inputSurface = StyleSheet.flatten(getByTestId('wechat-composer-input').props.style);
    expect(inputSurface.flexDirection).toBe('row');
    expect(inputSurface.borderRadius).toBeLessThanOrEqual(10);
    const speakerIcon = getByTestId('icon-volume-medium-outline');
    expect(speakerIcon.props.color).toBe(revaColors.ink2);
    expect(speakerIcon.props.color).not.toBe('#000000');
  });

  it('switches the speaker button into WeChat hold-to-talk mode and back to keyboard input', () => {
    const { getByLabelText, getByTestId, getByText, queryByTestId } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    fireEvent.press(getByLabelText('切换到语音输入'));

    expect(getByLabelText('切换到键盘输入')).toBeTruthy();
    expect(queryByTestId('icon-keypad-outline')).toBeNull();
    const keyboardIcon = flattenedStyle(getByTestId('wechat-keyboard-icon'));
    expect(keyboardIcon.width).toBeLessThanOrEqual(22);
    expect(keyboardIcon.height).toBeLessThanOrEqual(18);
    expect(flattenedStyle(getByTestId('wechat-keyboard-icon-frame')).borderColor).toBe(revaColors.ink2);
    expect(getByTestId('wechat-hold-to-talk-surface')).toBeTruthy();
    const holdText = getByText('按住 说话');
    expect(holdText).toBeTruthy();
    const holdTextStyle = flattenedStyle(holdText);
    expect(holdTextStyle.fontFamily).toBeUndefined();
    expect(holdTextStyle.fontSize).toBeLessThanOrEqual(17);
    expect(holdTextStyle.lineHeight).toBeLessThanOrEqual(24);
    expect(queryByTestId('wechat-composer-input')).toBeNull();
    expect(mockStartRecording).not.toHaveBeenCalled();

    fireEvent.press(getByLabelText('切换到键盘输入'));

    expect(getByLabelText('切换到语音输入')).toBeTruthy();
    expect(getByTestId('wechat-composer-input')).toBeTruthy();
  });

  it('starts hold-to-talk voice input from the WeChat hold surface', async () => {
    const { getByLabelText, getByTestId } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    fireEvent.press(getByLabelText('切换到语音输入'));
    fireEvent(getByTestId('wechat-hold-to-talk-surface'), 'pressIn', { nativeEvent: { pageX: 220, pageY: 300 } });
    await act(async () => { await Promise.resolve(); });
    fireEvent(getByTestId('wechat-hold-to-talk-surface'), 'pressOut');
    await act(async () => { await Promise.resolve(); });

    expect(mockStartRecording).toHaveBeenCalled();
    expect(mockStopAndTranscribe).toHaveBeenCalled();
  });

  it('submits a hold-to-talk transcript through the voice confirmation channel', async () => {
    const onSend = jest.fn().mockResolvedValue(true);
    const { getByLabelText, getByTestId } = render(
      <ChatInputBar onSend={onSend} isStreaming={false} />,
    );

    fireEvent.press(getByLabelText('切换到语音输入'));
    fireEvent(getByTestId('wechat-hold-to-talk-surface'), 'pressIn', {
      nativeEvent: { pageX: 220, pageY: 300 },
    });
    await act(async () => { await Promise.resolve(); });
    fireEvent(getByTestId('wechat-hold-to-talk-surface'), 'pressOut');
    act(() => {
      latestVoiceRecordingOptions.onTranscript('午餐吃了鸡胸肉');
    });

    await waitFor(() => {
      expect(onSend).toHaveBeenCalledWith(
        '午餐吃了鸡胸肉',
        null,
        { channel: 'voice' },
      );
    });
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

  it('starts hold-to-talk voice input from the center hold button after switching modes', () => {
    const { getByLabelText, getByTestId } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    fireEvent.press(getByLabelText('切换到语音输入'));
    fireEvent(getByTestId('wechat-hold-to-talk-surface'), 'pressIn', { nativeEvent: { pageX: 220, pageY: 300 } });
    fireEvent(getByTestId('wechat-hold-to-talk-surface'), 'pressOut');

    expect(mockStartRecording).toHaveBeenCalled();
    expect(mockStopAndTranscribe).toHaveBeenCalled();
  });

  it('cancels left hold-to-talk when the finger slides left', async () => {
    const { getByLabelText, getByTestId } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    fireEvent.press(getByLabelText('切换到语音输入'));
    fireEvent(getByTestId('wechat-hold-to-talk-surface'), 'pressIn', { nativeEvent: { pageX: 260, pageY: 620 } });
    await act(async () => { await Promise.resolve(); });
    fireEvent(getByTestId('wechat-hold-to-talk-surface'), 'touchMove', { nativeEvent: { pageX: 120, pageY: 620 } });
    fireEvent(getByTestId('wechat-hold-to-talk-surface'), 'pressOut');

    expect(mockCancelRecording).toHaveBeenCalled();
    expect(mockStopAndTranscribe).not.toHaveBeenCalled();
  });

  it('keeps hold-to-talk transcript editable when the finger slides right', async () => {
    const onSend = jest.fn();
    const { getByLabelText, getByTestId } = render(
      <ChatInputBar onSend={onSend} isStreaming={false} />,
    );

    fireEvent.press(getByLabelText('切换到语音输入'));
    fireEvent(getByTestId('wechat-hold-to-talk-surface'), 'pressIn', { nativeEvent: { pageX: 160, pageY: 620 } });
    await act(async () => { await Promise.resolve(); });
    fireEvent(getByTestId('wechat-hold-to-talk-surface'), 'touchMove', { nativeEvent: { pageX: 310, pageY: 620 } });
    fireEvent(getByTestId('wechat-hold-to-talk-surface'), 'pressOut');
    act(() => {
      latestVoiceRecordingOptions.onTranscript('记录午餐吃了鸡胸肉');
    });

    expect(mockStopAndTranscribe).toHaveBeenCalled();
    expect(getByLabelText('切换到语音输入')).toBeTruthy();
    expect(getByLabelText('消息输入框').props.value).toBe('记录午餐吃了鸡胸肉');
    expect(onSend).not.toHaveBeenCalled();
  });

  it('shows live text while hold-to-talk voice is recording', () => {
    mockVoiceRecordingState = {
      isRecording: true,
      isTranscribing: false,
      durationMs: 1200,
      partialText: '今天晚餐吃了鸡胸肉',
    };

    const { getByText, getByLabelText, getByTestId } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    expect(flattenedStyle(getByTestId('wechat-recording-overlay')).top).toBeGreaterThanOrEqual(52);
    expect(getByLabelText('实时语音转文字预览')).toBeTruthy();
    expect(getByText('今天晚餐吃了鸡胸肉')).toBeTruthy();
  });

  it('syncs hold-to-talk partial text into the input draft while sliding right to text', async () => {
    const { getByLabelText, getByTestId, getByText, rerender } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    fireEvent.press(getByLabelText('切换到语音输入'));
    fireEvent(getByTestId('wechat-hold-to-talk-surface'), 'pressIn', { nativeEvent: { pageX: 160, pageY: 620 } });
    fireEvent(getByTestId('wechat-hold-to-talk-surface'), 'touchMove', { nativeEvent: { pageX: 310, pageY: 620 } });

    mockVoiceRecordingState = {
      isRecording: true,
      isTranscribing: false,
      durationMs: 1200,
      partialText: '今天晚餐吃了鸡胸肉',
    };
    rerender(<ChatInputBar onSend={jest.fn()} isStreaming={false} />);

    expect(getByText('今天晚餐吃了鸡胸肉')).toBeTruthy();
    fireEvent(getByTestId('wechat-hold-to-talk-surface'), 'pressOut');
    act(() => {
      latestVoiceRecordingOptions.onTranscript('今天晚餐吃了鸡胸肉');
    });
    mockVoiceRecordingState = { isRecording: false, isTranscribing: false, durationMs: 0, partialText: '' };
    rerender(<ChatInputBar onSend={jest.fn()} isStreaming={false} />);
    await waitFor(() => {
      expect(getByLabelText('消息输入框').props.value).toBe('今天晚餐吃了鸡胸肉');
    });
  });

  it('sends left hold-to-talk transcript by default on release', () => {
    const onSend = jest.fn();
    const { getByLabelText, getByTestId } = render(
      <ChatInputBar onSend={onSend} isStreaming={false} />,
    );

    fireEvent.press(getByLabelText('切换到语音输入'));
    fireEvent(getByTestId('wechat-hold-to-talk-surface'), 'pressIn', { nativeEvent: { pageX: 160, pageY: 620 } });
    fireEvent(getByTestId('wechat-hold-to-talk-surface'), 'pressOut');
    act(() => {
      latestVoiceRecordingOptions.onTranscript('今天走了八千步');
    });

    expect(onSend).toHaveBeenCalledWith('今天走了八千步', null, { channel: 'voice' });
  });

  it('stays in hold-to-talk mode after sending a released voice transcript', () => {
    const onSend = jest.fn();
    const { getByLabelText, getByTestId } = render(
      <ChatInputBar onSend={onSend} isStreaming={false} />,
    );

    fireEvent.press(getByLabelText('切换到语音输入'));
    fireEvent(getByTestId('wechat-hold-to-talk-surface'), 'pressIn', { nativeEvent: { pageX: 160, pageY: 620 } });
    fireEvent(getByTestId('wechat-hold-to-talk-surface'), 'pressOut');
    act(() => {
      latestVoiceRecordingOptions.onTranscript('今天走了八千步');
    });

    expect(onSend).toHaveBeenCalledWith('今天走了八千步', null, { channel: 'voice' });
    expect(getByLabelText('切换到键盘输入')).toBeTruthy();
    expect(getByTestId('wechat-hold-to-talk-surface')).toBeTruthy();
  });

  it('does not enter hold-to-talk while the assistant is streaming', () => {
    const onSend = jest.fn();
    const { getByLabelText, getByTestId } = render(
      <ChatInputBar onSend={onSend} isStreaming={true} />,
    );

    fireEvent.press(getByLabelText('切换到语音输入'));
    expect(() => getByTestId('wechat-hold-to-talk-surface')).toThrow();
    expect(getByLabelText('消息输入框')).toBeTruthy();
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
    const { getByLabelText, getByTestId } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    expect(getByLabelText('正在听写')).toBeTruthy();
    const mic = getByLabelText('停止实时语音转文字');
    expect(mic.props.accessibilityState).toEqual(expect.objectContaining({ selected: true }));

    fireEvent.press(mic);

    expect(mockStopDictation).toHaveBeenCalled();
  });

  it('keeps realtime dictation explicitly disabled after tapping the active microphone again', () => {
    const onSend = jest.fn();
    mockRealtimeDictationState = { isDictating: true, error: null };
    const { getByLabelText, rerender } = render(
      <ChatInputBar onSend={onSend} isStreaming={false} />,
    );

    fireEvent.press(getByLabelText('停止实时语音转文字'));
    expect(mockStopDictation).toHaveBeenCalled();

    mockRealtimeDictationState = { isDictating: false, error: null };
    rerender(<ChatInputBar onSend={onSend} isStreaming={false} />);

    const disabledMic = getByLabelText('语音监听已禁用');
    expect(disabledMic.props.accessibilityState).toEqual(expect.objectContaining({ selected: false }));
    const disabledMicStyle = StyleSheet.flatten(disabledMic.props.style);
    expect(disabledMicStyle.backgroundColor).toBe(revaColors.paper2);
    expect(disabledMicStyle.backgroundColor).not.toBe('#2B2B2B');
    expect(disabledMicStyle.borderColor).toBe(revaColors.lineStrong);

    fireEvent.press(disabledMic);

    expect(mockStartDictation).toHaveBeenCalled();
  });

  it('does not enter hold mode while realtime dictation is still starting', async () => {
    let resolveStart!: (started: boolean) => void;
    mockStartDictation.mockImplementationOnce(() => new Promise<boolean>((resolve) => {
      resolveStart = resolve;
    }));
    const { getByLabelText, queryByLabelText } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    fireEvent.press(getByLabelText('实时语音转文字'));
    fireEvent.press(getByLabelText('切换到语音输入'));

    expect(queryByLabelText('按住说话')).toBeNull();
    expect(getByLabelText('消息输入框')).toBeTruthy();

    await act(async () => {
      resolveStart(true);
    });
  });

  it('waits for realtime audio release before switching to hold mode', async () => {
    let resolveStop!: () => void;
    mockRealtimeDictationState = { isDictating: true, error: null };
    mockStopDictation.mockImplementationOnce(() => new Promise<void>((resolve) => {
      resolveStop = resolve;
    }));
    const { getByLabelText, queryByLabelText } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    fireEvent.press(getByLabelText('切换到语音输入'));

    expect(mockStopDictation).toHaveBeenCalled();
    expect(queryByLabelText('按住说话')).toBeNull();

    await act(async () => {
      resolveStop();
    });
    await waitFor(() => expect(getByLabelText('按住说话')).toBeTruthy());
  });

  it('stops realtime dictation and disables the microphone after submit', async () => {
    const onSend = jest.fn();
    mockRealtimeDictationState = { isDictating: true, error: null };
    const { getByLabelText, rerender } = render(
      <ChatInputBar onSend={onSend} isStreaming={false} />,
    );

    fireEvent.changeText(getByLabelText('消息输入框'), '记录今天喝水 500 毫升');
    await act(async () => {
      fireEvent.press(getByLabelText('发送消息'));
      await Promise.resolve();
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(mockStopDictation).toHaveBeenCalled();
      expect(onSend).toHaveBeenCalledWith('记录今天喝水 500 毫升', null, undefined);
    });

    mockRealtimeDictationState = { isDictating: false, error: null };
    rerender(<ChatInputBar onSend={onSend} isStreaming={true} />);
    expect(() => getByLabelText('语音监听已禁用')).toThrow();
  });

  it('submits realtime microphone transcription through the voice channel', async () => {
    const onSend = jest.fn().mockResolvedValue(true);
    const { getByLabelText } = render(
      <ChatInputBar onSend={onSend} isStreaming={false} />,
    );

    await act(async () => {
      fireEvent.press(getByLabelText('实时语音转文字'));
      await Promise.resolve();
    });
    act(() => {
      latestRealtimeDictationOptions.onTranscript('记录今天喝水 500 毫升');
    });
    await act(async () => {
      fireEvent.press(getByLabelText('发送消息'));
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(onSend).toHaveBeenCalledWith(
        '记录今天喝水 500 毫升',
        null,
        { channel: 'voice' },
      );
    });
  });

  it('includes the final transcript returned while realtime recognition stops', async () => {
    mockStopDictation.mockResolvedValueOnce('记录今天喝水 500 毫升');
    const onSend = jest.fn().mockResolvedValue(true);
    const { getByLabelText } = render(
      <ChatInputBar onSend={onSend} isStreaming={false} />,
    );

    await act(async () => {
      fireEvent.press(getByLabelText('实时语音转文字'));
      await Promise.resolve();
    });
    act(() => {
      latestRealtimeDictationOptions.onTranscript('记录今天喝水');
    });
    await act(async () => {
      fireEvent.press(getByLabelText('发送消息'));
      await Promise.resolve();
    });

    expect(onSend).toHaveBeenCalledWith(
      '记录今天喝水 500 毫升',
      null,
      { channel: 'voice' },
    );
  });

  it('returns to the typed channel after the user edits realtime transcription', async () => {
    const onSend = jest.fn().mockResolvedValue(true);
    const { getByLabelText } = render(
      <ChatInputBar onSend={onSend} isStreaming={false} />,
    );

    await act(async () => {
      fireEvent.press(getByLabelText('实时语音转文字'));
      await Promise.resolve();
    });
    act(() => {
      latestRealtimeDictationOptions.onTranscript('记录今天喝水');
    });
    fireEvent.changeText(getByLabelText('消息输入框'), '记录今天喝水 500 毫升');
    await act(async () => {
      fireEvent.press(getByLabelText('发送消息'));
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(onSend).toHaveBeenCalledWith('记录今天喝水 500 毫升', null, undefined);
    });
  });

  it('cancels active dictation when the app moves to the background', async () => {
    mockRealtimeDictationState = { isDictating: true, error: null };
    const { getByLabelText, rerender } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    expect(appStateHandler).toBeDefined();
    act(() => {
      appStateHandler?.('background');
    });

    await waitFor(() => expect(mockCancelDictation).toHaveBeenCalled());
    mockRealtimeDictationState = { isDictating: false, error: null };
    rerender(<ChatInputBar onSend={jest.fn()} isStreaming={false} />);
    expect(getByLabelText('语音监听已禁用')).toBeTruthy();
  });

  it('cancels hold-to-talk when the app moves to the background', async () => {
    const { getByLabelText, getByTestId } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    fireEvent.press(getByLabelText('切换到语音输入'));
    fireEvent(getByTestId('wechat-hold-to-talk-surface'), 'pressIn', {
      nativeEvent: { pageX: 220, pageY: 620 },
    });
    await act(async () => { await Promise.resolve(); });
    act(() => {
      appStateHandler?.('background');
    });

    await waitFor(() => expect(mockCancelRecording).toHaveBeenCalled());
    expect(getByLabelText('切换到键盘输入')).toBeTruthy();
  });

  it('lets the inline microphone toggle from disabled back into realtime voice-to-text', () => {
    mockRealtimeDictationState = { isDictating: true, error: null };
    const { getByLabelText, rerender } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    fireEvent.press(getByLabelText('停止实时语音转文字'));
    mockRealtimeDictationState = { isDictating: false, error: null };
    rerender(<ChatInputBar onSend={jest.fn()} isStreaming={false} />);
    fireEvent.press(getByLabelText('语音监听已禁用'));

    expect(mockStartDictation).toHaveBeenCalled();
  });

  it('hides inline dictation while the left voice mode is in hold-to-talk', () => {
    const { getByLabelText, queryByLabelText } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    fireEvent.press(getByLabelText('切换到语音输入'));

    expect(getByLabelText('切换到键盘输入')).toBeTruthy();
    expect(getByLabelText('按住说话')).toBeTruthy();
    expect(queryByLabelText('实时语音转文字')).toBeNull();
  });

  it('stops and hides active inline dictation when tapping the send button', async () => {
    mockRealtimeDictationState = { isDictating: true, error: null };
    const onSend = jest.fn();
    const { getByLabelText, queryByLabelText } = render(
      <ChatInputBar onSend={onSend} isStreaming={false} />,
    );

    fireEvent.changeText(getByLabelText('消息输入框'), '听写完成的文字');
    await act(async () => {
      fireEvent.press(getByLabelText('发送消息'));
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(mockStopDictation).toHaveBeenCalled();
    expect(onSend).toHaveBeenCalledWith('听写完成的文字', null, undefined);
    expect(queryByLabelText('停止实时语音转文字')).toBeNull();
    expect(queryByLabelText('正在听写')).toBeNull();
    expect(queryByLabelText('语音监听已禁用')).toBeNull();
  });

  it('sends typed text when Enter is pressed in the composer', () => {
    const onSend = jest.fn();
    const { getByLabelText } = render(
      <ChatInputBar onSend={onSend} isStreaming={false} />,
    );

    fireEvent.changeText(getByLabelText('消息输入框'), '记录晚餐吃了鸡胸肉');
    fireEvent(getByLabelText('消息输入框'), 'keyPress', { nativeEvent: { key: 'Enter' } });

    expect(onSend).toHaveBeenCalledWith('记录晚餐吃了鸡胸肉', null, undefined);
  });

  it('stops realtime dictation before Enter submits the composer', async () => {
    mockRealtimeDictationState = { isDictating: true, error: null };
    const onSend = jest.fn();
    const { getByLabelText } = render(
      <ChatInputBar onSend={onSend} isStreaming={false} />,
    );

    fireEvent.changeText(getByLabelText('消息输入框'), '听写完成的文字');
    await act(async () => {
      fireEvent(getByLabelText('消息输入框'), 'keyPress', { nativeEvent: { key: 'Enter' } });
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(mockStopDictation).toHaveBeenCalled();
    expect(onSend).toHaveBeenCalledWith('听写完成的文字', null, undefined);
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

  it('restores a persisted text and image draft on mount', async () => {
    const restoredImages = [{
      uri: 'file:///documents/chat-drafts/lunch.jpeg',
      base64: '',
      type: 'jpeg',
      draftCreatedAt: 100,
    }];
    mockLoadChatDraft.mockResolvedValueOnce({ text: '继续确认午餐', images: restoredImages });
    const { getByLabelText } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    await waitFor(() => {
      expect(getByLabelText('消息输入框').props.value).toBe('继续确认午餐');
      expect(mockSetPendingImages).toHaveBeenCalledWith(restoredImages);
    });
  });

  it('hydrates private image bytes before send and clears only after acceptance', async () => {
    const storedImage = {
      uri: 'file:///documents/chat-drafts/lunch.jpeg',
      base64: '',
      type: 'jpeg',
      draftCreatedAt: 100,
    };
    const hydratedImage = { ...storedImage, base64: 'private-base64' };
    mockPendingImages = [storedImage];
    mockHydrateDraftImages.mockResolvedValueOnce([hydratedImage]);
    const onSend = jest.fn();
    const { getByLabelText } = render(
      <ChatInputBar onSend={onSend} isStreaming={false} />,
    );

    await act(async () => {
      fireEvent.press(getByLabelText('发送消息'));
      await Promise.resolve();
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(onSend).toHaveBeenCalledWith('请分析这些图片', [hydratedImage], undefined);
      expect(mockReleaseImagesAfterSend).toHaveBeenCalled();
      expect(mockClearImages).not.toHaveBeenCalled();
      expect(mockClearPersistedChatDraft).toHaveBeenCalled();
    });
  });

  it('retains the draft when send rejects immediately', async () => {
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation(jest.fn());
    jest.spyOn(console, 'warn').mockImplementation(jest.fn());
    const onSend = jest.fn().mockRejectedValue(new Error('network unavailable'));
    const { getByLabelText } = render(
      <ChatInputBar onSend={onSend} isStreaming={false} />,
    );

    fireEvent.changeText(getByLabelText('消息输入框'), '这条草稿不能丢');
    await act(async () => {
      fireEvent.press(getByLabelText('发送消息'));
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith('发送失败', expect.stringContaining('草稿已保留'));
    });
    expect(getByLabelText('消息输入框').props.value).toBe('这条草稿不能丢');
    expect(mockClearImages).not.toHaveBeenCalled();
    expect(mockClearPersistedChatDraft).not.toHaveBeenCalled();
  });

  it('retains the draft when the chat engine explicitly rejects before server acceptance', async () => {
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation(jest.fn());
    const storedImage = {
      uri: 'file:///documents/chat-drafts/offline-lunch.jpeg',
      base64: '',
      type: 'jpeg',
    };
    mockPendingImages = [storedImage];
    mockHydrateDraftImages.mockResolvedValueOnce([{ ...storedImage, base64: 'private-base64' }]);
    const onSend = jest.fn().mockResolvedValue(false);
    const { getByLabelText } = render(
      <ChatInputBar onSend={onSend} isStreaming={false} />,
    );

    fireEvent.changeText(getByLabelText('消息输入框'), '离线时也不能丢');
    await act(async () => {
      fireEvent.press(getByLabelText('发送消息'));
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith('发送失败', expect.stringContaining('草稿已保留'));
    });
    expect(getByLabelText('消息输入框').props.value).toBe('离线时也不能丢');
    expect(mockClearImages).not.toHaveBeenCalled();
    expect(mockClearPersistedChatDraft).not.toHaveBeenCalled();
  });

  it('updates the composer when the same follow-up prompt is injected again', async () => {
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

    await act(async () => {
      fireEvent(getByLabelText('消息输入框'), 'keyPress', { nativeEvent: { key: 'Enter' } });
      await Promise.resolve();
    });
    expect(onSend).toHaveBeenCalledWith(prompt, null, undefined);
    await waitFor(() => expect(getByLabelText('消息输入框').props.value).toBe(''));

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
