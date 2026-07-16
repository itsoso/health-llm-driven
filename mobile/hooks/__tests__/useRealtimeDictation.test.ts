import { act, renderHook, waitFor } from '@testing-library/react-native';
import { useRealtimeDictation } from '../useRealtimeDictation';

const mockSetAudioModeAsync = jest.fn().mockResolvedValue(undefined);
const mockRequestPerm = jest.fn().mockResolvedValue({ granted: true });
const mockPrepare = jest.fn().mockResolvedValue(undefined);
const mockRecord = jest.fn();
const mockStop = jest.fn().mockResolvedValue(undefined);
const mockTranscribe = jest.fn().mockResolvedValue({
  text: '记录今天喝水 500 毫升',
  provider: 'dashscope_qwen_asr',
  model: 'qwen3-asr-flash',
  durationMs: 1560,
  confidence: 'high',
  empty: false,
});
const mockEmitClientEvent = jest.fn().mockResolvedValue(undefined);
const mockDurationBucket = jest.fn().mockReturnValue('1_3s');

const recorder = {
  prepareToRecordAsync: (...args: any[]) => mockPrepare(...args),
  record: (...args: any[]) => mockRecord(...args),
  stop: (...args: any[]) => mockStop(...args),
  uri: 'file:///tmp/realtime.m4a',
};

jest.mock('expo-audio', () => ({
  useAudioRecorder: () => recorder,
  RecordingPresets: { HIGH_QUALITY: {} },
  setAudioModeAsync: (...args: any[]) => mockSetAudioModeAsync(...args),
  requestRecordingPermissionsAsync: (...args: any[]) => mockRequestPerm(...args),
}));

jest.mock('../../services/transcribe', () => ({
  transcribeAudioDetailed: (...args: any[]) => mockTranscribe(...args),
}));

jest.mock('../../services/clientEvents', () => ({
  emitClientEvent: (...args: any[]) => mockEmitClientEvent(...args),
  durationBucket: (...args: any[]) => mockDurationBucket(...args),
}));

function releasedRecordingSession(): boolean {
  return mockSetAudioModeAsync.mock.calls.some(
    ([mode]) => mode && mode.allowsRecording === false,
  );
}

describe('useRealtimeDictation', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockRequestPerm.mockResolvedValue({ granted: true });
    mockPrepare.mockResolvedValue(undefined);
    mockStop.mockResolvedValue(undefined);
    mockTranscribe.mockResolvedValue({
      text: '记录今天喝水 500 毫升',
      provider: 'dashscope_qwen_asr',
      model: 'qwen3-asr-flash',
      durationMs: 1560,
      confidence: 'high',
      empty: false,
    });
  });

  it('starts realtime dictation by recording local audio for cloud ASR', async () => {
    const { result } = renderHook(() => useRealtimeDictation({ onTranscript: jest.fn() }));

    await act(async () => {
      await result.current.startDictation();
    });

    expect(mockRequestPerm).toHaveBeenCalled();
    expect(mockSetAudioModeAsync).toHaveBeenCalledWith(
      expect.objectContaining({ allowsRecording: true }),
    );
    expect(mockPrepare).toHaveBeenCalled();
    expect(mockRecord).toHaveBeenCalled();
    expect(result.current.isDictating).toBe(true);
  });

  it('stops recording, transcribes with DashScope ASR, and returns ASR metadata', async () => {
    const onTranscript = jest.fn();
    const { result } = renderHook(() => useRealtimeDictation({ onTranscript }));

    await act(async () => {
      await result.current.startDictation();
    });
    await act(async () => {
      const text = await result.current.stopDictation();
      expect(text).toBe('记录今天喝水 500 毫升');
    });

    expect(mockStop).toHaveBeenCalled();
    expect(releasedRecordingSession()).toBe(true);
    expect(mockTranscribe).toHaveBeenCalledWith('file:///tmp/realtime.m4a');
    await waitFor(() => expect(onTranscript).toHaveBeenCalledWith(
      '记录今天喝水 500 毫升',
      expect.objectContaining({
        provider: 'dashscope_qwen_asr',
        model: 'qwen3-asr-flash',
      }),
    ));
    expect(mockEmitClientEvent).toHaveBeenCalledWith('voice_asr_terminal', {
      phase: 'completed',
      duration_bucket: '1_3s',
      action_type: 'dictation',
      provider: 'dashscope_qwen_asr',
      confidence: 'high',
      empty: false,
    });
    expect(mockEmitClientEvent).toHaveBeenCalledWith('voice_input_terminal', {
      phase: 'completed',
      duration_bucket: '1_3s',
      action_type: 'dictation',
    });
  });

  it('does not transcribe after realtime dictation is cancelled', async () => {
    const { result } = renderHook(() => useRealtimeDictation({ onTranscript: jest.fn() }));

    await act(async () => {
      await result.current.startDictation();
    });
    await act(async () => {
      await result.current.cancelDictation();
    });

    expect(mockStop).toHaveBeenCalled();
    expect(mockTranscribe).not.toHaveBeenCalled();
    expect(releasedRecordingSession()).toBe(true);
    expect(result.current.isDictating).toBe(false);
    expect(mockEmitClientEvent).toHaveBeenCalledWith('voice_input_terminal', {
      phase: 'cancelled',
      duration_bucket: '1_3s',
      action_type: 'dictation',
    });
  });

  it('fails before recording when microphone permission is denied', async () => {
    const onError = jest.fn();
    mockRequestPerm.mockResolvedValueOnce({ granted: false });
    const { result } = renderHook(() => useRealtimeDictation({ onTranscript: jest.fn(), onError }));

    let started = true;
    await act(async () => {
      started = await result.current.startDictation();
    });

    expect(started).toBe(false);
    expect(mockPrepare).not.toHaveBeenCalled();
    expect(mockTranscribe).not.toHaveBeenCalled();
    expect(result.current.error).toBe('需要麦克风权限才能实时听写');
    expect(onError).toHaveBeenCalledWith('需要麦克风权限才能实时听写');
    expect(mockEmitClientEvent).toHaveBeenCalledWith('voice_input_terminal', {
      phase: 'failed',
      duration_bucket: '1_3s',
      action_type: 'dictation',
      error_code: 'microphone_permission_denied',
    });
  });
});
