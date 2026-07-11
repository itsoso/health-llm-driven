/**
 * useVoiceRecording — 按住说话的三条承重路径。
 *
 * 1. 主路径: 端上识别(Voice zh-CN), 备胎录音器不启动, 松手拿最终结果交卷;
 * 2. 备胎: Voice.start 抛错 → 自动降级 expo-audio 录音 + 云端转写;
 * 3. 兜底: stop 后最终结果迟迟不来 → 1.2s 超时拿最新 partial 交卷, 不让用户干等。
 *
 * 另外钉住 iOS audio session 释放:语音结束后必须回到 allowsRecording:false,
 * 否则下次点输入框键盘可能弹不出。
 */
import { act, renderHook, waitFor } from '@testing-library/react-native';
import { Alert } from 'react-native';
import Voice from '@react-native-voice/voice';
import { useVoiceRecording } from '../useVoiceRecording';
import { transcribeAudio } from '../../services/transcribe';
import { resetVoiceSessionCoordinatorForTests } from '../../services/voiceSessionCoordinator';

const mockVoiceStart = jest.fn();
const mockVoiceStop = jest.fn().mockResolvedValue(undefined);
const mockVoiceCancel = jest.fn().mockResolvedValue(undefined);

jest.mock('@react-native-voice/voice', () => ({
  __esModule: true,
  default: {
    start: (...args: any[]) => mockVoiceStart(...args),
    stop: (...args: any[]) => mockVoiceStop(...args),
    cancel: (...args: any[]) => mockVoiceCancel(...args),
  },
}));

const mockSetAudioModeAsync = jest.fn().mockResolvedValue(undefined);
const mockRequestRecordingPermissionsAsync = jest.fn().mockResolvedValue({ granted: true });
const mockPrepare = jest.fn().mockResolvedValue(undefined);
const mockRecord = jest.fn();
const mockRecorderStop = jest.fn().mockResolvedValue(undefined);
const mockEmitClientEvent = jest.fn().mockResolvedValue(undefined);
const mockDurationBucket = jest.fn().mockReturnValue('3_10s');
const mockRecorder = {
  prepareToRecordAsync: (...args: any[]) => mockPrepare(...args),
  record: (...args: any[]) => mockRecord(...args),
  stop: (...args: any[]) => mockRecorderStop(...args),
  uri: 'file://fallback.m4a',
};

jest.mock('expo-audio', () => ({
  RecordingPresets: { HIGH_QUALITY: {} },
  setAudioModeAsync: (...args: any[]) => mockSetAudioModeAsync(...args),
  requestRecordingPermissionsAsync: (...args: any[]) => mockRequestRecordingPermissionsAsync(...args),
  useAudioRecorder: () => mockRecorder,
}));

jest.mock('expo-haptics', () => ({
  impactAsync: jest.fn().mockResolvedValue(undefined),
  notificationAsync: jest.fn().mockResolvedValue(undefined),
  ImpactFeedbackStyle: { Medium: 'medium' },
  NotificationFeedbackType: { Success: 'success', Warning: 'warning' },
}));

jest.mock('../../services/transcribe', () => ({
  transcribeAudio: jest.fn().mockResolvedValue('云端转写结果'),
}));

const voiceHandlers = Voice as unknown as {
  onSpeechPartialResults?: (e: any) => void;
  onSpeechResults?: (e: any) => void;
  onSpeechEnd?: (e?: any) => void;
  onSpeechError?: (e?: any) => void;
};
jest.mock('../../services/clientEvents', () => ({
  emitClientEvent: (...args: any[]) => mockEmitClientEvent(...args),
  durationBucket: (...args: any[]) => mockDurationBucket(...args),
}));

function releasedRecordingSession(): boolean {
  return mockSetAudioModeAsync.mock.calls.some(
    ([mode]) => mode && mode.allowsRecording === false,
  );
}

describe('useVoiceRecording', () => {
  beforeEach(() => {
    resetVoiceSessionCoordinatorForTests();
    jest.clearAllMocks();
    mockVoiceStart.mockResolvedValue(undefined);
    mockRequestRecordingPermissionsAsync.mockResolvedValue({ granted: true });
    mockPrepare.mockResolvedValue(undefined);
    mockRecorderStop.mockResolvedValue(undefined);
    (transcribeAudio as jest.Mock).mockResolvedValue('云端转写结果');
    jest.spyOn(Alert, 'alert').mockImplementation(() => {});
  });

  it('主路径: 端上识别, 不碰备胎录音器, partial 实时可见, 松手拿最终结果', async () => {
    const onTranscript = jest.fn();
    const { result } = renderHook(() => useVoiceRecording({ onTranscript }));

    await act(async () => {
      await result.current.startRecording();
    });

    expect(mockSetAudioModeAsync).toHaveBeenCalledWith(
      expect.objectContaining({ allowsRecording: true }),
    );
    expect(mockVoiceStart).toHaveBeenCalledWith('zh-CN');
    expect(mockPrepare).not.toHaveBeenCalled();
    expect(result.current.isRecording).toBe(true);

    act(() => {
      voiceHandlers.onSpeechPartialResults?.({ value: ['喝了一杯'] });
    });
    expect(result.current.partialText).toBe('喝了一杯');

    let stopPromise: Promise<void>;
    act(() => {
      stopPromise = result.current.stopAndTranscribe();
      voiceHandlers.onSpeechResults?.({ value: ['喝了一杯水'] });
    });
    await act(async () => { await stopPromise!; });

    expect(onTranscript).toHaveBeenCalledWith('喝了一杯水');
    expect(transcribeAudio).not.toHaveBeenCalled();
    expect(result.current.partialText).toBe('');
    await waitFor(() => expect(releasedRecordingSession()).toBe(true));
  });

  it('备胎: Voice.start 抛错 → 降级录音 + 云端转写, 并在网络转写前释放 session', async () => {
    mockVoiceStart.mockRejectedValue(new Error('dictation disabled'));
    const onTranscript = jest.fn();
    const { result } = renderHook(() => useVoiceRecording({ onTranscript }));

    await act(async () => {
      await result.current.startRecording();
    });

    expect(mockPrepare).toHaveBeenCalled();
    expect(mockRecord).toHaveBeenCalled();
    expect(result.current.isRecording).toBe(true);

    await act(async () => {
      await result.current.stopAndTranscribe();
    });

    expect(transcribeAudio).toHaveBeenCalledWith('file://fallback.m4a');
    expect(onTranscript).toHaveBeenCalledWith('云端转写结果');
    expect(releasedRecordingSession()).toBe(true);
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

  it('兜底: 最终结果不来 → 1.2s 超时拿最新 partial 交卷', async () => {
    const onTranscript = jest.fn();
    const { result } = renderHook(() => useVoiceRecording({ onTranscript }));

    await act(async () => {
      await result.current.startRecording();
    });
    act(() => {
      voiceHandlers.onSpeechPartialResults?.({ value: ['今天走了八千步'] });
    });

    await act(async () => {
      const p = result.current.stopAndTranscribe();
      await p;
    });

    expect(onTranscript).toHaveBeenCalledWith('今天走了八千步');
    expect(transcribeAudio).not.toHaveBeenCalled();
    expect(releasedRecordingSession()).toBe(true);
  }, 10000);

  it('极速轻点: start 在途中就被取消 → 不进入录音态, 且释放 session', async () => {
    const { result } = renderHook(() => useVoiceRecording());

    let startPromise: Promise<boolean | undefined>;
    await act(async () => {
      startPromise = result.current.startRecording();
      await result.current.cancelRecording();
      await startPromise!;
    });

    expect(result.current.isRecording).toBe(false);
    await waitFor(() => expect(releasedRecordingSession()).toBe(true));
    expect(mockEmitClientEvent).toHaveBeenCalledWith('voice_input_terminal', {
      phase: 'cancelled',
      duration_bucket: '3_10s',
      action_type: 'hold',
    });
  });

  it('取消: 上滑取消后不产出任何转写, 且释放 session', async () => {
    const onTranscript = jest.fn();
    const { result } = renderHook(() => useVoiceRecording({ onTranscript }));

    await act(async () => {
      await result.current.startRecording();
    });
    mockSetAudioModeAsync.mockClear();
    await act(async () => {
      await result.current.cancelRecording();
    });

    expect(mockVoiceCancel).toHaveBeenCalled();
    expect(onTranscript).not.toHaveBeenCalled();
    expect(releasedRecordingSession()).toBe(true);
    await waitFor(() => expect(result.current.isRecording).toBe(false));
    expect(transcribeAudio).not.toHaveBeenCalled();
    expect(mockEmitClientEvent).toHaveBeenCalledWith('voice_input_terminal', {
      phase: 'cancelled',
      duration_bucket: '3_10s',
      action_type: 'hold',
    });
  });

  it('drops a late transcription result after cancellation or background cleanup', async () => {
    let resolveTranscription!: (text: string) => void;
    mockVoiceStart.mockRejectedValueOnce(new Error('dictation disabled'));
    (transcribeAudio as jest.Mock).mockImplementationOnce(() => new Promise<string>((resolve) => {
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
    await waitFor(() => expect(transcribeAudio).toHaveBeenCalled());

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

  it('云端转写无文本时仍释放 session', async () => {
    mockVoiceStart.mockRejectedValue(new Error('dictation disabled'));
    (transcribeAudio as jest.Mock).mockResolvedValueOnce('');
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

  it('aborts a pending recording start when the user releases before the recorder is ready', async () => {
    mockVoiceStart.mockRejectedValueOnce(new Error('dictation disabled'));
    let resolvePrepare!: () => void;
    mockPrepare.mockImplementationOnce(() => new Promise<void>((resolve) => {
      resolvePrepare = resolve;
    }));
    const { result } = renderHook(() => useVoiceRecording({ onTranscript: jest.fn() }));
    let startPromise!: Promise<boolean | undefined>;

    act(() => {
      startPromise = result.current.startRecording();
    });
    await waitFor(() => expect(mockPrepare).toHaveBeenCalled());

    await act(async () => {
      await result.current.stopAndTranscribe();
    });
    expect(transcribeAudio).not.toHaveBeenCalled();

    resolvePrepare();
    await act(async () => {
      await startPromise;
    });

    expect(mockRecord).not.toHaveBeenCalled();
    expect(transcribeAudio).not.toHaveBeenCalled();
    expect(releasedRecordingSession()).toBe(true);
  });

  it('cancels native recognition when start finishes after the user already released', async () => {
    let resolveStart!: () => void;
    mockVoiceStart.mockImplementationOnce(() => new Promise<void>((resolve) => {
      resolveStart = resolve;
    }));
    const { result } = renderHook(() => useVoiceRecording({ onTranscript: jest.fn() }));
    let startPromise!: Promise<boolean | undefined>;

    act(() => {
      startPromise = result.current.startRecording();
    });
    await waitFor(() => expect(mockVoiceStart).toHaveBeenCalled());
    await act(async () => {
      await result.current.stopAndTranscribe();
    });
    resolveStart();
    await act(async () => {
      await startPromise;
    });

    expect(mockVoiceCancel).toHaveBeenCalled();
    expect(result.current.isRecording).toBe(false);
    expect(releasedRecordingSession()).toBe(true);
  });
});
