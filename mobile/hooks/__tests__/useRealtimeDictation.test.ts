import { act, renderHook, waitFor } from '@testing-library/react-native';
import Voice from '@react-native-voice/voice';
import { useRealtimeDictation } from '../useRealtimeDictation';
import { resetVoiceSessionCoordinatorForTests } from '../../services/voiceSessionCoordinator';

const mockVoiceStart = jest.fn().mockResolvedValue(undefined);
const mockVoiceStop = jest.fn().mockResolvedValue(undefined);
const mockVoiceCancel = jest.fn().mockResolvedValue(undefined);
const mockVoiceDestroy = jest.fn().mockResolvedValue(undefined);
const mockVoiceRemoveAllListeners = jest.fn();
const mockVoiceIsAvailable = jest.fn().mockResolvedValue(1);
const mockSetAudioModeAsync = jest.fn().mockResolvedValue(undefined);
const mockEmitClientEvent = jest.fn().mockResolvedValue(undefined);
const mockDurationBucket = jest.fn().mockReturnValue('1_3s');

jest.mock('@react-native-voice/voice', () => ({
  __esModule: true,
  default: {
    start: (...args: any[]) => mockVoiceStart(...args),
    stop: (...args: any[]) => mockVoiceStop(...args),
    cancel: (...args: any[]) => mockVoiceCancel(...args),
    destroy: (...args: any[]) => mockVoiceDestroy(...args),
    isAvailable: (...args: any[]) => mockVoiceIsAvailable(...args),
    removeAllListeners: (...args: any[]) => mockVoiceRemoveAllListeners(...args),
  },
}));

jest.mock('expo-audio', () => ({
  setAudioModeAsync: (...args: any[]) => mockSetAudioModeAsync(...args),
}));

jest.mock('../../services/clientEvents', () => ({
  emitClientEvent: (...args: any[]) => mockEmitClientEvent(...args),
  durationBucket: (...args: any[]) => mockDurationBucket(...args),
}));

const mockedVoice = Voice as any;

describe('useRealtimeDictation', () => {
  beforeEach(() => {
    resetVoiceSessionCoordinatorForTests();
    jest.clearAllMocks();
    mockVoiceIsAvailable.mockResolvedValue(1);
    mockedVoice.onSpeechPartialResults = undefined;
    mockedVoice.onSpeechResults = undefined;
    mockedVoice.onSpeechEnd = undefined;
    mockedVoice.onSpeechError = undefined;
  });

  it('starts native speech recognition in recording audio mode', async () => {
    const { result } = renderHook(() => useRealtimeDictation({ onTranscript: jest.fn() }));

    await act(async () => {
      await result.current.startDictation();
    });

    expect(mockSetAudioModeAsync).toHaveBeenCalledWith(
      expect.objectContaining({ allowsRecording: true }),
    );
    expect(mockVoiceStart).toHaveBeenCalledWith('zh-CN');
    expect(result.current.isDictating).toBe(true);
  });

  it('reclaims the shared Voice callbacks when dictation starts after hold-to-talk', async () => {
    const onTranscript = jest.fn();
    const foreignPartialHandler = jest.fn();
    const { result } = renderHook(() => useRealtimeDictation({ onTranscript }));
    mockedVoice.onSpeechPartialResults = foreignPartialHandler;

    await act(async () => {
      await result.current.startDictation();
    });
    act(() => {
      mockedVoice.onSpeechPartialResults({ value: ['右侧听写重新接管回调'] });
    });

    expect(foreignPartialHandler).not.toHaveBeenCalled();
    expect(onTranscript).toHaveBeenCalledWith('右侧听写重新接管回调');
  });

  it('cancels a pending native start so a second mic tap cannot re-enable listening', async () => {
    let resolveAvailability!: (value: number) => void;
    mockVoiceIsAvailable.mockReturnValueOnce(new Promise<number>((resolve) => {
      resolveAvailability = resolve;
    }));
    const { result } = renderHook(() => useRealtimeDictation({ onTranscript: jest.fn() }));

    let started: boolean | undefined;
    act(() => {
      void result.current.startDictation().then(value => { started = value; });
    });
    await act(async () => {
      await result.current.stopDictation();
      resolveAvailability(1);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(started).toBe(false);
    expect(mockVoiceStart).not.toHaveBeenCalled();
    expect(result.current.isDictating).toBe(false);
    expect(mockEmitClientEvent).toHaveBeenCalledWith('voice_input_terminal', {
      phase: 'cancelled',
      duration_bucket: '1_3s',
      action_type: 'dictation',
      error_code: 'start_cancelled',
    });
  });

  it('does not enter realtime dictation when native speech recognition is unavailable', async () => {
    mockVoiceIsAvailable.mockResolvedValueOnce(0);
    const { result } = renderHook(() => useRealtimeDictation({ onTranscript: jest.fn() }));

    await act(async () => {
      await result.current.startDictation();
    });

    expect(mockVoiceIsAvailable).toHaveBeenCalled();
    expect(mockVoiceStart).not.toHaveBeenCalled();
    expect(result.current.isDictating).toBe(false);
    expect(result.current.error).toBe('当前设备不可用语音识别');
    expect(mockEmitClientEvent).toHaveBeenCalledWith('voice_input_terminal', {
      phase: 'failed',
      duration_bucket: '1_3s',
      action_type: 'dictation',
      error_code: 'speech_recognition_unavailable',
    });
  });

  it('emits partial speech results as realtime composer text', async () => {
    const onTranscript = jest.fn();
    const { result } = renderHook(() => useRealtimeDictation({ onTranscript }));

    await act(async () => {
      await result.current.startDictation();
    });
    act(() => {
      mockedVoice.onSpeechPartialResults({ value: ['记录今天喝水 500 毫升'] });
    });

    expect(onTranscript).toHaveBeenCalledWith('记录今天喝水 500 毫升');
  });

  it('uses the longest result when final speech text arrives after a partial', async () => {
    const onTranscript = jest.fn();
    const { result } = renderHook(() => useRealtimeDictation({ onTranscript }));

    await act(async () => {
      await result.current.startDictation();
    });
    act(() => {
      mockedVoice.onSpeechPartialResults({ value: ['记录今天'] });
      mockedVoice.onSpeechResults({ value: ['记录今天喝水 500 毫升'] });
    });

    expect(onTranscript).toHaveBeenLastCalledWith('记录今天喝水 500 毫升');
  });

  it('treats a shorter final result as the authoritative native correction', async () => {
    const onTranscript = jest.fn();
    const { result } = renderHook(() => useRealtimeDictation({ onTranscript }));

    await act(async () => {
      await result.current.startDictation();
    });
    act(() => {
      mockedVoice.onSpeechPartialResults({ value: ['吃了十五个鸡蛋'] });
      mockedVoice.onSpeechResults({ value: ['吃了五个鸡蛋'] });
    });

    expect(onTranscript).toHaveBeenLastCalledWith('吃了五个鸡蛋');
  });

  it('stops recognition and releases the recording audio session', async () => {
    const { result } = renderHook(() => useRealtimeDictation({ onTranscript: jest.fn() }));

    await act(async () => {
      await result.current.startDictation();
    });
    mockSetAudioModeAsync.mockClear();
    await act(async () => {
      await result.current.stopDictation();
    });

    expect(mockVoiceStop).toHaveBeenCalled();
    expect(mockSetAudioModeAsync).toHaveBeenCalledWith(
      expect.objectContaining({ allowsRecording: false }),
    );
    await waitFor(() => expect(result.current.isDictating).toBe(false));
    expect(mockEmitClientEvent).toHaveBeenCalledWith('voice_input_terminal', {
      phase: 'completed',
      duration_bucket: '1_3s',
      action_type: 'dictation',
    });
  });

  it('keeps the final native transcript delivered while stop is completing', async () => {
    const onTranscript = jest.fn();
    let resolveStop!: () => void;
    mockVoiceStop.mockImplementationOnce(() => new Promise<void>((resolve) => {
      resolveStop = resolve;
    }));
    const { result } = renderHook(() => useRealtimeDictation({ onTranscript }));

    await act(async () => {
      await result.current.startDictation();
    });
    let finalTranscript: string | undefined;
    let stopPromise!: Promise<string>;
    act(() => {
      stopPromise = result.current.stopDictation();
      void stopPromise.then(value => { finalTranscript = value; });
    });
    await waitFor(() => expect(mockVoiceStop).toHaveBeenCalled());
    await act(async () => {
      mockedVoice.onSpeechResults({ value: ['停止前补齐的最终文字'] });
      resolveStop();
      await stopPromise;
    });

    expect(finalTranscript).toBe('停止前补齐的最终文字');
    expect(onTranscript).toHaveBeenLastCalledWith('停止前补齐的最终文字');
    expect(result.current.isDictating).toBe(false);
  });

  it('accepts final speech results that arrive after native speech-end during stop', async () => {
    const onTranscript = jest.fn();
    const { result } = renderHook(() => useRealtimeDictation({ onTranscript }));

    await act(async () => {
      await result.current.startDictation();
    });
    let stopPromise!: Promise<string>;
    act(() => {
      stopPromise = result.current.stopDictation();
      mockedVoice.onSpeechEnd();
      mockedVoice.onSpeechResults({ value: ['语音结束事件之后到达的尾字'] });
    });
    let finalTranscript = '';
    await act(async () => {
      finalTranscript = await stopPromise;
    });

    expect(finalTranscript).toBe('语音结束事件之后到达的尾字');
    expect(onTranscript).toHaveBeenLastCalledWith('语音结束事件之后到达的尾字');
  });

  it('keeps the final transcript when speech-end happens before submit stops dictation', async () => {
    const onTranscript = jest.fn();
    const { result } = renderHook(() => useRealtimeDictation({ onTranscript }));

    await act(async () => {
      await result.current.startDictation();
    });
    act(() => {
      mockedVoice.onSpeechEnd();
    });

    let stopPromise!: Promise<string>;
    act(() => {
      stopPromise = result.current.stopDictation();
      mockedVoice.onSpeechResults({ value: ['先结束后提交仍要保留的尾字'] });
    });
    let finalTranscript = '';
    await act(async () => {
      finalTranscript = await stopPromise;
    });

    expect(finalTranscript).toBe('先结束后提交仍要保留的尾字');
    expect(onTranscript).toHaveBeenLastCalledWith('先结束后提交仍要保留的尾字');
  });

  it('stops a native recognizer that finishes starting after cancellation', async () => {
    let resolveStart!: () => void;
    mockVoiceStart.mockImplementationOnce(() => new Promise<void>((resolve) => {
      resolveStart = resolve;
    }));
    const { result } = renderHook(() => useRealtimeDictation({ onTranscript: jest.fn() }));

    let startResult: boolean | undefined;
    act(() => {
      void result.current.startDictation().then(value => { startResult = value; });
    });
    await waitFor(() => expect(mockVoiceStart).toHaveBeenCalled());
    await act(async () => {
      await result.current.cancelDictation();
      resolveStart();
      await Promise.resolve();
    });

    expect(startResult).toBe(false);
    await waitFor(() => expect(mockVoiceCancel).toHaveBeenCalled());
    expect(result.current.isDictating).toBe(false);
  });

  it('cancels recognition and releases the recording audio session', async () => {
    const { result } = renderHook(() => useRealtimeDictation({ onTranscript: jest.fn() }));

    await act(async () => {
      await result.current.startDictation();
    });
    mockSetAudioModeAsync.mockClear();
    await act(async () => {
      await result.current.cancelDictation();
    });

    expect(mockVoiceCancel).toHaveBeenCalled();
    await waitFor(() => {
      expect(mockSetAudioModeAsync).toHaveBeenCalledWith(
        expect.objectContaining({ allowsRecording: false }),
      );
    });
    expect(result.current.isDictating).toBe(false);
    expect(mockEmitClientEvent).toHaveBeenCalledWith('voice_input_terminal', {
      phase: 'cancelled',
      duration_bucket: '1_3s',
      action_type: 'dictation',
    });
  });

  it('notifies the controller after native speech ends and audio is released', async () => {
    const onEnd = jest.fn();
    const { result } = renderHook(() => useRealtimeDictation({ onTranscript: jest.fn(), onEnd }));

    await act(async () => {
      await result.current.startDictation();
    });
    mockSetAudioModeAsync.mockClear();
    act(() => {
      mockedVoice.onSpeechEnd();
    });

    await waitFor(() => expect(onEnd).toHaveBeenCalled());
    expect(mockSetAudioModeAsync).toHaveBeenCalledWith(
      expect.objectContaining({ allowsRecording: false }),
    );
    expect(mockEmitClientEvent).toHaveBeenCalledWith('voice_input_terminal', {
      phase: 'completed',
      duration_bucket: '1_3s',
      action_type: 'dictation',
    });
  });

  it('releases the audio session when speech recognition fails', async () => {
    const { result } = renderHook(() => useRealtimeDictation({ onTranscript: jest.fn() }));

    await act(async () => {
      await result.current.startDictation();
    });
    mockSetAudioModeAsync.mockClear();
    act(() => {
      mockedVoice.onSpeechError({ error: { message: 'speech denied' } });
    });

    await waitFor(() => {
      expect(mockSetAudioModeAsync).toHaveBeenCalledWith(
        expect.objectContaining({ allowsRecording: false }),
      );
    });
    expect(result.current.error).toBe('speech denied');
    expect(result.current.isDictating).toBe(false);
    expect(mockEmitClientEvent).toHaveBeenCalledWith('voice_input_terminal', {
      phase: 'failed',
      duration_bucket: '1_3s',
      action_type: 'dictation',
      error_code: 'speech_recognition_failed',
    });
  });
});
