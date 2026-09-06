import { act, renderHook, waitFor } from '@testing-library/react-native';
import { ensureAIConsent } from '../../services/aiConsent';
import { invalidateAIConsent } from '../../services/aiConsentState';

// iOS 按住说话必须独占 audio session；停止、取消和异常都要 deactivate，
// 让外部播放器恢复，同时把 session 放回非录音模式，避免后续键盘/麦克风失效。

const mockSetAudioModeAsync = jest.fn().mockResolvedValue(undefined);
const mockSetIsAudioActiveAsync = jest.fn().mockResolvedValue(undefined);
const mockRequestPerm = jest.fn().mockResolvedValue({ granted: true });
const mockPrepare = jest.fn().mockResolvedValue(undefined);
const mockRecord = jest.fn();
const mockStop = jest.fn().mockResolvedValue(undefined);
const mockTranscribe = jest.fn().mockResolvedValue('识别出的文字');
const mockEmitClientEvent = jest.fn().mockResolvedValue(undefined);
const mockDurationBucket = jest.fn().mockReturnValue('3_10s');

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
  setIsAudioActiveAsync: (...a: any[]) => mockSetIsAudioActiveAsync(...a),
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
  transcribeAudioDetailed: async (...a: any[]) => {
    const text = await mockTranscribe(...a);
    return {
      text,
      provider: 'openai_whisper',
      model: 'whisper-1',
      durationMs: 1234,
      confidence: text ? 'medium' : 'low',
      empty: !text,
    };
  },
}));

jest.mock('../../services/clientEvents', () => ({
  emitClientEvent: (...args: any[]) => mockEmitClientEvent(...args),
  durationBucket: (...args: any[]) => mockDurationBucket(...args),
}));

import { useVoiceRecording } from '../useVoiceRecording';

/** 从 mockSetAudioModeAsync 的调用里找是否发生过 allowsRecording:false 的释放调用。 */
function releasedRecordingSession(): boolean {
  return mockSetAudioModeAsync.mock.calls.some(
    ([mode]) => mode && mode.allowsRecording === false,
  );
}

function releasedAudioFocus(): boolean {
  return mockSetIsAudioActiveAsync.mock.calls.some(([active]) => active === false);
}

describe('useVoiceRecording audio session release (Bug 2: 语音后键盘失效)', () => {
  it('cancels an active recording after authorization is withdrawn without transcribing', async () => {
    const { result } = renderHook(() => useVoiceRecording());
    await act(async () => { await result.current.startRecording(); });
    await act(async () => { invalidateAIConsent(); });
    expect(mockStop).toHaveBeenCalled();
    expect(result.current.isRecording).toBe(false);
    expect(mockTranscribe).not.toHaveBeenCalled();
  });
  it('does not request the microphone or record after AI sharing is declined', async () => {
    (ensureAIConsent as jest.Mock).mockResolvedValueOnce(false);
    const { result } = renderHook(() => useVoiceRecording());
    await act(async () => { expect(await result.current.startRecording()).toBe(false); });
    expect(mockRequestPerm).not.toHaveBeenCalled();
    expect(mockRecord).not.toHaveBeenCalled();
    expect(mockTranscribe).not.toHaveBeenCalled();
  });
  beforeEach(() => {
    jest.clearAllMocks();
    mockRequestPerm.mockResolvedValue({ granted: true });
    mockPrepare.mockResolvedValue(undefined);
    mockStop.mockResolvedValue(undefined);
    mockTranscribe.mockResolvedValue('识别出的文字');
  });

  it('requests exclusive iOS audio focus before preparing push-to-talk recording', async () => {
    const { result } = renderHook(() => useVoiceRecording({ onTranscript: jest.fn() }));

    await act(async () => {
      await result.current.startRecording();
    });

    expect(mockSetAudioModeAsync).toHaveBeenCalledWith({
      allowsRecording: true,
      playsInSilentMode: true,
      shouldPlayInBackground: false,
      interruptionMode: 'doNotMix',
    });
    expect(mockSetAudioModeAsync.mock.invocationCallOrder[0]).toBeLessThan(
      mockPrepare.mock.invocationCallOrder[0],
    );
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
    expect(releasedAudioFocus()).toBe(true);
    await waitFor(() => expect(onTranscript).toHaveBeenCalledWith(
      '识别出的文字',
      expect.objectContaining({ provider: 'openai_whisper', durationMs: 1234 }),
    ));
    expect(mockEmitClientEvent).toHaveBeenCalledWith('voice_input_terminal', {
      phase: 'completed',
      duration_bucket: '3_10s',
      action_type: 'hold',
    });
  });

  it('reports whether native recording actually became ready', async () => {
    const { result } = renderHook(() => useVoiceRecording({ onTranscript: jest.fn() }));
    let started: boolean | undefined;

    await act(async () => {
      started = await result.current.startRecording();
    });

    expect(started).toBe(true);
  });

  it('does not stop the native recorder when unmounted before recording is ready', async () => {
    mockRequestPerm.mockResolvedValueOnce({ granted: false });
    const { result, unmount } = renderHook(() => useVoiceRecording({ onTranscript: jest.fn() }));

    await act(async () => {
      await result.current.startRecording();
    });
    unmount();
    await act(async () => {
      await Promise.resolve();
    });

    expect(mockPrepare).not.toHaveBeenCalled();
    expect(mockStop).not.toHaveBeenCalled();
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
    expect(mockEmitClientEvent).toHaveBeenCalledWith('voice_input_terminal', {
      phase: 'failed',
      duration_bucket: '3_10s',
      action_type: 'hold',
      error_code: 'empty_transcript',
    });
  });

  it('releases the recording audio session when the native recorder fails to stop', async () => {
    mockStop.mockRejectedValueOnce(new Error('native stop failed'));
    const { result } = renderHook(() => useVoiceRecording({ onTranscript: jest.fn() }));

    await act(async () => {
      await result.current.startRecording();
    });
    mockSetAudioModeAsync.mockClear();

    await act(async () => {
      await result.current.stopAndTranscribe();
    });

    expect(releasedRecordingSession()).toBe(true);
    expect(result.current.isRecording).toBe(false);
    expect(result.current.isTranscribing).toBe(false);
    expect(mockTranscribe).not.toHaveBeenCalled();
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
    expect(releasedAudioFocus()).toBe(true);
    expect(mockTranscribe).not.toHaveBeenCalled();
    expect(mockEmitClientEvent).toHaveBeenCalledWith('voice_input_terminal', {
      phase: 'cancelled',
      duration_bucket: '3_10s',
      action_type: 'hold',
    });
  });

  it('releases audio focus when recording preparation fails after focus configuration', async () => {
    mockPrepare.mockRejectedValueOnce(new Error('prepare failed'));
    const { result } = renderHook(() => useVoiceRecording({ onTranscript: jest.fn() }));

    await act(async () => {
      await result.current.startRecording();
    });

    expect(result.current.isRecording).toBe(false);
    expect(releasedRecordingSession()).toBe(true);
    expect(releasedAudioFocus()).toBe(true);
  });

  it('releases audio focus when the recording hook unmounts while holding to talk', async () => {
    let resolveStop!: () => void;
    mockStop.mockImplementationOnce(() => new Promise<void>((resolve) => {
      resolveStop = resolve;
    }));
    const { result, unmount } = renderHook(() => useVoiceRecording({ onTranscript: jest.fn() }));

    await act(async () => {
      await result.current.startRecording();
    });
    mockSetAudioModeAsync.mockClear();
    mockSetIsAudioActiveAsync.mockClear();

    unmount();
    await act(async () => {
      await Promise.resolve();
    });

    expect(releasedAudioFocus()).toBe(false);

    resolveStop();
    await act(async () => {
      await Promise.resolve();
    });

    expect(releasedRecordingSession()).toBe(true);
    expect(releasedAudioFocus()).toBe(true);
  });

  it('drops a late transcription result after cancellation or background cleanup', async () => {
    let resolveTranscription!: (text: string) => void;
    mockTranscribe.mockImplementationOnce(() => new Promise<string>((resolve) => {
      resolveTranscription = resolve;
    }));
    const onTranscript = jest.fn();
    const { result } = renderHook(() => useVoiceRecording({ onTranscript }));

    await act(async () => {
      await result.current.startRecording();
    });
    let stopPromise!: Promise<void>;
    act(() => {
      stopPromise = result.current.stopAndTranscribe();
    });
    await waitFor(() => expect(mockTranscribe).toHaveBeenCalled());

    await act(async () => {
      await result.current.cancelRecording();
    });
    resolveTranscription('这条迟到结果不应写回输入框');
    await act(async () => {
      await stopPromise;
    });

    expect(onTranscript).not.toHaveBeenCalled();
    expect(result.current.isTranscribing).toBe(false);
  });

  it('does not transcribe when recording never became ready (stop before start finished)', async () => {
    const { result } = renderHook(() => useVoiceRecording({ onTranscript: jest.fn() }));

    // 未 start 直接 stop: readyRef false → 早退, 不崩、不转写。
    await act(async () => {
      await result.current.stopAndTranscribe();
    });

    expect(mockTranscribe).not.toHaveBeenCalled();
  });

  it('aborts a pending recording start when the user releases before the recorder is ready', async () => {
    let resolvePrepare!: () => void;
    mockPrepare.mockImplementationOnce(() => new Promise<void>((resolve) => {
      resolvePrepare = resolve;
    }));
    const { result } = renderHook(() => useVoiceRecording({ onTranscript: jest.fn() }));
    let startPromise!: Promise<boolean>;

    act(() => {
      startPromise = result.current.startRecording();
    });
    await waitFor(() => expect(mockPrepare).toHaveBeenCalled());

    await act(async () => {
      await result.current.stopAndTranscribe();
    });
    expect(mockTranscribe).not.toHaveBeenCalled();

    resolvePrepare();
    await act(async () => {
      await startPromise;
    });

    expect(mockRecord).not.toHaveBeenCalled();
    expect(mockTranscribe).not.toHaveBeenCalled();
    expect(releasedRecordingSession()).toBe(true);
  });
});
jest.mock('../../services/aiConsent', () => ({ ensureAIConsent: jest.fn().mockResolvedValue(true) }));
