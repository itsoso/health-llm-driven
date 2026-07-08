import { act, renderHook, waitFor } from '@testing-library/react-native';
import Voice from '@react-native-voice/voice';
import { useRealtimeDictation } from '../useRealtimeDictation';

const mockVoiceStart = jest.fn().mockResolvedValue(undefined);
const mockVoiceStop = jest.fn().mockResolvedValue(undefined);
const mockVoiceDestroy = jest.fn().mockResolvedValue(undefined);
const mockVoiceRemoveAllListeners = jest.fn();
const mockVoiceIsAvailable = jest.fn().mockResolvedValue(1);
const mockSetAudioModeAsync = jest.fn().mockResolvedValue(undefined);

jest.mock('@react-native-voice/voice', () => ({
  __esModule: true,
  default: {
    start: (...args: any[]) => mockVoiceStart(...args),
    stop: (...args: any[]) => mockVoiceStop(...args),
    destroy: (...args: any[]) => mockVoiceDestroy(...args),
    isAvailable: (...args: any[]) => mockVoiceIsAvailable(...args),
    removeAllListeners: (...args: any[]) => mockVoiceRemoveAllListeners(...args),
  },
}));

jest.mock('expo-audio', () => ({
  setAudioModeAsync: (...args: any[]) => mockSetAudioModeAsync(...args),
}));

const mockedVoice = Voice as any;

describe('useRealtimeDictation', () => {
  beforeEach(() => {
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

    expect(mockSetAudioModeAsync).toHaveBeenCalledWith(
      expect.objectContaining({ allowsRecording: false }),
    );
    expect(result.current.error).toBe('speech denied');
    expect(result.current.isDictating).toBe(false);
  });
});
