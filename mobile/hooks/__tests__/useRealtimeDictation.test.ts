import { act, renderHook } from '@testing-library/react-native';
import { useRealtimeDictation } from '../useRealtimeDictation';
import {
  createCloudRealtimeAsrSession,
  type RealtimeAsrSession,
} from '../../services/cloudRealtimeAsr';

jest.mock('../../services/cloudRealtimeAsr', () => ({
  createCloudRealtimeAsrSession: jest.fn(),
}));

jest.mock('../../services/clientEvents', () => ({
  emitClientEvent: jest.fn().mockResolvedValue(undefined),
  durationBucket: jest.fn().mockReturnValue('1_3s'),
}));

const mockedCreateSession = createCloudRealtimeAsrSession as jest.MockedFunction<
  typeof createCloudRealtimeAsrSession
>;

describe('useRealtimeDictation', () => {
  let session: jest.Mocked<RealtimeAsrSession>;
  let callbacks: {
    onTranscript: (text: string, result?: any) => void;
    onLevel?: (level: number) => void;
  };

  beforeEach(() => {
    jest.clearAllMocks();
    callbacks = { onTranscript: jest.fn() };
    session = {
      start: jest.fn().mockResolvedValue(true),
      stop: jest.fn().mockResolvedValue({
        text: '记录今天喝水 500 毫升',
        provider: 'dashscope_qwen_asr_realtime',
        model: 'qwen3-asr-flash-realtime',
        durationMs: 920,
        confidence: 'high',
        empty: false,
      }),
      cancel: jest.fn().mockResolvedValue(undefined),
    };
    mockedCreateSession.mockImplementation((options) => {
      callbacks = options;
      return session;
    });
  });

  it('uses the authenticated Alibaba Cloud ASR session as the only dictation provider', async () => {
    const onTranscript = jest.fn();
    const { result } = renderHook(() => useRealtimeDictation({ onTranscript }));

    await act(async () => {
      await result.current.startDictation();
    });

    expect(mockedCreateSession).toHaveBeenCalledTimes(1);
    expect(session.start).toHaveBeenCalledTimes(1);
    expect(result.current.isDictating).toBe(true);
    expect(callbacks.onLevel).toEqual(expect.any(Function));
  });

  it('forwards cloud partial text and keeps the cloud final result on release', async () => {
    const onTranscript = jest.fn();
    const { result } = renderHook(() => useRealtimeDictation({ onTranscript }));

    await act(async () => {
      await result.current.startDictation();
    });
    act(() => {
      callbacks.onTranscript('记录今天喝水', {
        text: '记录今天喝水',
        provider: 'dashscope_qwen_asr_realtime',
        model: 'qwen3-asr-flash-realtime',
        durationMs: 500,
        empty: false,
      });
    });

    let finalText = '';
    await act(async () => {
      finalText = await result.current.stopDictation();
    });

    expect(session.stop).toHaveBeenCalledTimes(1);
    expect(finalText).toBe('记录今天喝水 500 毫升');
    expect(onTranscript).toHaveBeenLastCalledWith(
      '记录今天喝水 500 毫升',
      expect.objectContaining({
        provider: 'dashscope_qwen_asr_realtime',
        model: 'qwen3-asr-flash-realtime',
      }),
    );
    expect(result.current.isDictating).toBe(false);
  });

  it('cancels a cloud session when released before startup completes', async () => {
    let resolveStart!: (started: boolean) => void;
    session.start.mockImplementationOnce(() => new Promise<boolean>((resolve) => {
      resolveStart = resolve;
    }));
    const { result } = renderHook(() => useRealtimeDictation({ onTranscript: jest.fn() }));

    let startPromise: Promise<boolean>;
    await act(async () => {
      startPromise = result.current.startDictation();
      await Promise.resolve();
    });

    await act(async () => {
      await result.current.stopDictation();
    });
    expect(session.cancel).toHaveBeenCalledTimes(1);

    await act(async () => {
      resolveStart(false);
      await startPromise;
    });
    expect(result.current.isDictating).toBe(false);
  });

  it('does not surface a late startup failure after the user already cancelled', async () => {
    let rejectStart!: (error: Error) => void;
    session.start.mockImplementationOnce(() => new Promise<boolean>((_resolve, reject) => {
      rejectStart = reject;
    }));
    const onError = jest.fn();
    const { result } = renderHook(() => useRealtimeDictation({
      onTranscript: jest.fn(),
      onError,
    }));

    let startPromise: Promise<boolean>;
    await act(async () => {
      startPromise = result.current.startDictation();
      await Promise.resolve();
    });
    await act(async () => {
      await result.current.stopDictation();
    });

    rejectStart(new Error('startup failed after cancellation'));
    await act(async () => {
      await expect(startPromise).resolves.toBe(false);
    });

    expect(onError).not.toHaveBeenCalled();
    expect(result.current.isDictating).toBe(false);
  });

  it('keeps cancellation authoritative while cleanup is still pending', async () => {
    let resolveStart!: (started: boolean) => void;
    let resolveCancel!: () => void;
    session.start.mockImplementationOnce(() => new Promise<boolean>((resolve) => {
      resolveStart = resolve;
    }));
    session.cancel.mockImplementationOnce(() => new Promise<void>((resolve) => {
      resolveCancel = resolve;
    }));
    const onError = jest.fn();
    const { result } = renderHook(() => useRealtimeDictation({
      onTranscript: jest.fn(),
      onError,
    }));

    let startPromise: Promise<boolean>;
    let stopPromise: Promise<string>;
    await act(async () => {
      startPromise = result.current.startDictation();
      await Promise.resolve();
      stopPromise = result.current.stopDictation();
      await Promise.resolve();
    });

    resolveStart(false);
    await act(async () => {
      await expect(startPromise).resolves.toBe(false);
    });
    expect(onError).not.toHaveBeenCalled();

    resolveCancel();
    await act(async () => {
      await expect(stopPromise).resolves.toBe('');
    });
    expect(result.current.isDictating).toBe(false);
  });

  it('cancels the cloud session without committing buffered speech', async () => {
    const { result } = renderHook(() => useRealtimeDictation({ onTranscript: jest.fn() }));

    await act(async () => {
      await result.current.startDictation();
      await result.current.cancelDictation();
    });

    expect(session.cancel).toHaveBeenCalledTimes(1);
    expect(session.stop).not.toHaveBeenCalled();
    expect(result.current.isDictating).toBe(false);
  });

  it('surfaces Alibaba Cloud errors and does not enter dictation', async () => {
    const error = new Error('阿里云实时语音服务暂不可用，请稍后重试');
    session.start.mockRejectedValueOnce(error);
    const onError = jest.fn();
    const { result } = renderHook(() => useRealtimeDictation({
      onTranscript: jest.fn(),
      onError,
    }));

    await act(async () => {
      await result.current.startDictation();
    });

    expect(result.current.isDictating).toBe(false);
    expect(result.current.error).toBe(error.message);
    expect(onError).toHaveBeenCalledWith(error.message);
    expect(session.cancel).toHaveBeenCalledTimes(1);
  });
});
