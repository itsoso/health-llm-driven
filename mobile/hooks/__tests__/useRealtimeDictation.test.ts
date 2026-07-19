import { act, renderHook, waitFor } from '@testing-library/react-native';
import Voice from '@react-native-voice/voice';
import { resetVoiceEventRouterForTests } from '../../services/voiceEventRouter';
import { useRealtimeDictation } from '../useRealtimeDictation';

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
    jest.clearAllMocks();
    mockVoiceStart.mockResolvedValue(undefined);
    mockVoiceStop.mockResolvedValue(undefined);
    mockVoiceCancel.mockResolvedValue(undefined);
    mockVoiceDestroy.mockResolvedValue(undefined);
    mockVoiceIsAvailable.mockResolvedValue(1);
    mockedVoice.onSpeechPartialResults = undefined;
    mockedVoice.onSpeechResults = undefined;
    mockedVoice.onSpeechRecognized = undefined;
    mockedVoice.onSpeechEnd = undefined;
    mockedVoice.onSpeechError = undefined;
    resetVoiceEventRouterForTests();
  });

  it('uses iPhone native realtime recognition for the composer path', async () => {
    const { result } = renderHook(() => useRealtimeDictation({ onTranscript: jest.fn() }));

    await act(async () => {
      await result.current.startDictation();
    });

    expect(mockVoiceIsAvailable).toHaveBeenCalledTimes(1);
    expect(mockVoiceStart).toHaveBeenCalledWith('zh-CN');
    expect(result.current.isDictating).toBe(true);
  });

  it('forwards partial speech and keeps the latest final result', async () => {
    const onTranscript = jest.fn();
    const { result } = renderHook(() => useRealtimeDictation({ onTranscript }));

    await act(async () => {
      await result.current.startDictation();
    });
    act(() => {
      mockedVoice.onSpeechPartialResults({ value: ['记录今天喝水'] });
      mockedVoice.onSpeechResults({ value: ['记录今天喝水 500 毫升'] });
    });

    expect(onTranscript).toHaveBeenLastCalledWith(
      '记录今天喝水 500 毫升',
      expect.objectContaining({ provider: 'native_realtime', empty: false }),
    );
  });

  it('waits for the final marker instead of submitting the first result on release', async () => {
    const onTranscript = jest.fn();
    const { result } = renderHook(() => useRealtimeDictation({ onTranscript }));

    await act(async () => {
      await result.current.startDictation();
    });

    let settled = false;
    let finalText = '';
    let stopPromise!: Promise<string>;
    act(() => {
      stopPromise = result.current.stopDictation();
      void stopPromise.then(text => {
        settled = true;
        finalText = text;
      });
      mockedVoice.onSpeechResults({ value: ['先到达的中间结果'] });
    });
    await act(async () => {
      await Promise.resolve();
    });
    expect(settled).toBe(false);

    act(() => {
      mockedVoice.onSpeechResults({ value: ['补齐尾字后的最终结果'] });
      mockedVoice.onSpeechRecognized({ isFinal: true });
    });
    await act(async () => {
      await stopPromise;
    });

    expect(finalText).toBe('补齐尾字后的最终结果');
    expect(onTranscript).toHaveBeenLastCalledWith(
      '补齐尾字后的最终结果',
      expect.objectContaining({ provider: 'native_realtime' }),
    );
  });

  it('accepts a final result that arrives after native speech-end', async () => {
    const onTranscript = jest.fn();
    const { result } = renderHook(() => useRealtimeDictation({ onTranscript }));

    await act(async () => {
      await result.current.startDictation();
    });
    let stopPromise!: Promise<string>;
    act(() => {
      stopPromise = result.current.stopDictation();
      mockedVoice.onSpeechEnd();
      mockedVoice.onSpeechResults({ value: ['语音结束后到达的尾字'] });
      mockedVoice.onSpeechRecognized({ isFinal: true });
    });

    let finalText = '';
    await act(async () => {
      finalText = await stopPromise;
    });
    expect(finalText).toBe('语音结束后到达的尾字');
    expect(onTranscript).toHaveBeenLastCalledWith(
      '语音结束后到达的尾字',
      expect.objectContaining({ provider: 'native_realtime' }),
    );
  });

  it('cancels recognition and releases the audio session without returning text', async () => {
    const { result } = renderHook(() => useRealtimeDictation({ onTranscript: jest.fn() }));

    await act(async () => {
      await result.current.startDictation();
      await result.current.cancelDictation();
    });

    expect(mockVoiceCancel).toHaveBeenCalledTimes(1);
    expect(result.current.isDictating).toBe(false);
    expect(mockSetAudioModeAsync).toHaveBeenCalledWith(
      expect.objectContaining({ allowsRecording: false }),
    );
  });

  it('surfaces native speech availability errors without entering dictation', async () => {
    mockVoiceIsAvailable.mockResolvedValueOnce(0);
    const onError = jest.fn();
    const { result } = renderHook(() => useRealtimeDictation({ onTranscript: jest.fn(), onError }));

    await act(async () => {
      await result.current.startDictation();
    });

    expect(result.current.isDictating).toBe(false);
    expect(result.current.error).toBe('当前设备不可用语音识别');
    expect(onError).toHaveBeenCalledWith('当前设备不可用语音识别');
  });

  it('notifies the chat controller after native speech ends', async () => {
    const onEnd = jest.fn();
    const { result } = renderHook(() => useRealtimeDictation({ onTranscript: jest.fn(), onEnd }));

    await act(async () => {
      await result.current.startDictation();
    });
    act(() => {
      mockedVoice.onSpeechResults({ value: ['今天记录饮水'] });
      mockedVoice.onSpeechEnd();
    });

    await waitFor(() => expect(onEnd).toHaveBeenCalledTimes(1));
    expect(result.current.isDictating).toBe(false);
  });
});
