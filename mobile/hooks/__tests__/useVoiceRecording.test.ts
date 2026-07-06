import { act, renderHook, waitFor } from '@testing-library/react-native';

// Bug 2: 语音结束后 iOS audio session 若停在录音模式 (allowsRecording:true), 会占着
// 麦克风, 导致下次点输入框键盘弹不出 / TextInput 摸不到。stopAndTranscribe 与
// cancelRecording 都必须显式把 session 放回 allowsRecording:false。这些测试钉死该释放。

const mockSetAudioModeAsync = jest.fn().mockResolvedValue(undefined);
const mockRequestPerm = jest.fn().mockResolvedValue({ granted: true });
const mockPrepare = jest.fn().mockResolvedValue(undefined);
const mockRecord = jest.fn();
const mockStop = jest.fn().mockResolvedValue(undefined);
const mockTranscribe = jest.fn().mockResolvedValue('识别出的文字');

const recorder = {
  prepareToRecordAsync: (...a: any[]) => mockPrepare(...a),
  record: (...a: any[]) => mockRecord(...a),
  stop: (...a: any[]) => mockStop(...a),
  uri: 'file:///tmp/voice.m4a',
};

jest.mock('expo-audio', () => ({
  useAudioRecorder: () => recorder,
  RecordingPresets: { HIGH_QUALITY: {} },
  setAudioModeAsync: (...a: any[]) => mockSetAudioModeAsync(...a),
  requestRecordingPermissionsAsync: (...a: any[]) => mockRequestPerm(...a),
}));

jest.mock('expo-haptics', () => ({
  impactAsync: jest.fn(),
  notificationAsync: jest.fn(),
  ImpactFeedbackStyle: { Medium: 'medium' },
  NotificationFeedbackType: { Success: 'success', Warning: 'warning' },
}));

jest.mock('react-native', () => ({
  Alert: { alert: jest.fn() },
}));

jest.mock('../../services/transcribe', () => ({
  transcribeAudio: (...a: any[]) => mockTranscribe(...a),
}));

import { useVoiceRecording } from '../useVoiceRecording';

/** 从 mockSetAudioModeAsync 的调用里找是否发生过 allowsRecording:false 的释放调用。 */
function releasedRecordingSession(): boolean {
  return mockSetAudioModeAsync.mock.calls.some(
    ([mode]) => mode && mode.allowsRecording === false,
  );
}

describe('useVoiceRecording audio session release (Bug 2: 语音后键盘失效)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockRequestPerm.mockResolvedValue({ granted: true });
    mockTranscribe.mockResolvedValue('识别出的文字');
  });

  it('releases the recording audio session after stopAndTranscribe', async () => {
    const onTranscript = jest.fn();
    const { result } = renderHook(() => useVoiceRecording({ onTranscript }));

    await act(async () => {
      await result.current.startRecording();
    });
    // 起录时进的是录音模式 (allowsRecording:true)。
    expect(mockSetAudioModeAsync).toHaveBeenCalledWith(
      expect.objectContaining({ allowsRecording: true }),
    );

    await act(async () => {
      await result.current.stopAndTranscribe();
    });

    // 关键: 转写完后 session 被放回 allowsRecording:false, 键盘才能再弹。
    expect(releasedRecordingSession()).toBe(true);
    await waitFor(() => expect(onTranscript).toHaveBeenCalledWith('识别出的文字'));
  });

  it('still releases the session when transcription yields no text', async () => {
    mockTranscribe.mockResolvedValueOnce('');
    const { result } = renderHook(() => useVoiceRecording({ onTranscript: jest.fn() }));

    await act(async () => {
      await result.current.startRecording();
    });
    mockSetAudioModeAsync.mockClear();
    await act(async () => {
      await result.current.stopAndTranscribe();
    });

    expect(releasedRecordingSession()).toBe(true);
  });

  it('releases the recording audio session after cancelRecording', async () => {
    const { result } = renderHook(() => useVoiceRecording({ onTranscript: jest.fn() }));

    await act(async () => {
      await result.current.startRecording();
    });
    mockSetAudioModeAsync.mockClear();
    await act(async () => {
      await result.current.cancelRecording();
    });

    // 取消同样要释放 session。
    expect(releasedRecordingSession()).toBe(true);
    expect(mockTranscribe).not.toHaveBeenCalled();
  });

  it('does not transcribe when recording never became ready (stop before start finished)', async () => {
    const { result } = renderHook(() => useVoiceRecording({ onTranscript: jest.fn() }));

    // 未 start 直接 stop: readyRef false → 早退, 不崩、不转写。
    await act(async () => {
      await result.current.stopAndTranscribe();
    });

    expect(mockTranscribe).not.toHaveBeenCalled();
  });
});
