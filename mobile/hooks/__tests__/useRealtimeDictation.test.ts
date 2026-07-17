import { act, renderHook } from '@testing-library/react-native';
import { useRealtimeDictation } from '../useRealtimeDictation';

const mockStart = jest.fn().mockResolvedValue(true);
const mockStop = jest.fn().mockResolvedValue({
  text: '记录今天喝水 500 毫升',
  provider: 'dashscope_qwen_asr_realtime',
  model: 'qwen3-asr-flash-realtime',
  durationMs: 920,
  confidence: 'high',
  empty: false,
});
const mockCancel = jest.fn().mockResolvedValue(undefined);
const mockCreateSession = jest.fn();
const mockEmitClientEvent = jest.fn().mockResolvedValue(undefined);
const mockDurationBucket = jest.fn().mockReturnValue('1_3s');
let latestSessionOptions: any;

jest.mock('../../services/cloudRealtimeAsr', () => ({
  createCloudRealtimeAsrSession: (options: any) => {
    latestSessionOptions = options;
    return mockCreateSession(options);
  },
}));

jest.mock('../../services/clientEvents', () => ({
  emitClientEvent: (...args: any[]) => mockEmitClientEvent(...args),
  durationBucket: (...args: any[]) => mockDurationBucket(...args),
}));

describe('useRealtimeDictation', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    latestSessionOptions = undefined;
    mockStart.mockResolvedValue(true);
    mockStop.mockResolvedValue({
      text: '记录今天喝水 500 毫升',
      provider: 'dashscope_qwen_asr_realtime',
      model: 'qwen3-asr-flash-realtime',
      durationMs: 920,
      confidence: 'high',
      empty: false,
    });
    mockCancel.mockResolvedValue(undefined);
    mockCreateSession.mockReturnValue({
      start: mockStart,
      stop: mockStop,
      cancel: mockCancel,
    });
  });

  it('starts a cloud realtime session instead of iPhone speech recognition', async () => {
    const { result } = renderHook(() => useRealtimeDictation({ onTranscript: jest.fn() }));

    await act(async () => {
      await result.current.startDictation();
    });

    expect(mockCreateSession).toHaveBeenCalledTimes(1);
    expect(mockStart).toHaveBeenCalledTimes(1);
    expect(result.current.isDictating).toBe(true);
  });

  it('forwards partial cloud transcripts while the user is still speaking', async () => {
    const onTranscript = jest.fn();
    const { result } = renderHook(() => useRealtimeDictation({ onTranscript }));
    await act(async () => {
      await result.current.startDictation();
    });

    act(() => {
      latestSessionOptions.onTranscript('记录今天喝水', {
        text: '记录今天喝水',
        provider: 'dashscope_qwen_asr_realtime',
        model: 'qwen3-asr-flash-realtime',
        durationMs: 420,
        empty: false,
      });
    });

    expect(onTranscript).toHaveBeenCalledWith(
      '记录今天喝水',
      expect.objectContaining({ provider: 'dashscope_qwen_asr_realtime' }),
    );
  });

  it('commits the cloud session on release and returns the final transcript', async () => {
    const onEnd = jest.fn();
    const { result } = renderHook(() => useRealtimeDictation({ onTranscript: jest.fn(), onEnd }));
    await act(async () => {
      await result.current.startDictation();
    });

    let text = '';
    await act(async () => {
      text = await result.current.stopDictation();
    });

    expect(text).toBe('记录今天喝水 500 毫升');
    expect(result.current.isDictating).toBe(false);
    expect(onEnd).toHaveBeenCalledTimes(1);
    expect(mockEmitClientEvent).toHaveBeenCalledWith('voice_asr_terminal', {
      phase: 'completed',
      duration_bucket: '1_3s',
      action_type: 'dictation',
      provider: 'dashscope_qwen_asr_realtime',
      confidence: 'high',
      empty: false,
    });
  });

  it('cancels cloud audio without returning a transcript', async () => {
    const { result } = renderHook(() => useRealtimeDictation({ onTranscript: jest.fn() }));
    await act(async () => {
      await result.current.startDictation();
      await result.current.cancelDictation();
    });

    expect(mockCancel).toHaveBeenCalledTimes(1);
    expect(mockStop).not.toHaveBeenCalled();
    expect(result.current.isDictating).toBe(false);
    expect(mockEmitClientEvent).toHaveBeenCalledWith('voice_input_terminal', {
      phase: 'cancelled',
      duration_bucket: '1_3s',
      action_type: 'dictation',
    });
  });

  it('surfaces cloud session startup errors without enabling dictation', async () => {
    const onError = jest.fn();
    mockStart.mockRejectedValueOnce(new Error('云端连接失败'));
    const { result } = renderHook(() => useRealtimeDictation({ onTranscript: jest.fn(), onError }));

    let started = true;
    await act(async () => {
      started = await result.current.startDictation();
    });

    expect(started).toBe(false);
    expect(result.current.isDictating).toBe(false);
    expect(result.current.error).toBe('云端连接失败');
    expect(onError).toHaveBeenCalledWith('云端连接失败');
  });
});
