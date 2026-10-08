import { act, renderHook, waitFor } from '@testing-library/react-native';
import { AppState, type AppStateStatus } from 'react-native';
import { setAudioModeAsync } from 'expo-audio';
import { createCloudRealtimeAsrSession } from '../../services/cloudRealtimeAsr';
import { createCloudStreamingTtsSession } from '../../services/cloudStreamingTts';
import { cancelAgentRun, getAgentTurnStatus, streamChat } from '../../services/chat';
import { splitTextForCloudTts } from '../../utils/ttsText';
import { useVoiceConversation } from '../useVoiceConversation';
import { ensureAIConsent } from '../../services/aiConsent';
import { invalidateAIConsent } from '../../services/aiConsentState';
import { loadVoiceStyle } from '../../services/voiceStyle';

const mockSpeechSpeak = jest.fn();
const mockSpeechStop = jest.fn();
const mockAsrStart = jest.fn<Promise<boolean>, []>();
const mockAsrStop = jest.fn();
const mockAsrCancel = jest.fn<Promise<void>, []>();
const mockTtsStart = jest.fn<Promise<boolean>, []>();
const mockTtsAppend = jest.fn<Promise<void>, [string]>();
const mockTtsFinish = jest.fn<Promise<void>, []>();
const mockTtsCancel = jest.fn<Promise<void>, []>();
let realtimeOptions: { onTranscript: (text: string, result?: any) => void; onError?: (error: Error) => void } | null = null;

jest.mock('expo-speech', () => ({
  speak: (...args: any[]) => mockSpeechSpeak(...args),
  stop: (...args: any[]) => mockSpeechStop(...args),
  getAvailableVoicesAsync: jest.fn().mockResolvedValue([]),
}));

jest.mock('expo-audio', () => ({
  setAudioModeAsync: jest.fn().mockResolvedValue(undefined),
}));

jest.mock('../../services/voiceStyle', () => ({
  loadVoiceStyle: jest.fn().mockResolvedValue('cloud_cloned_private_female'),
  getVoiceStyle: jest.fn(() => ({
    provider: 'cloud',
    cloudVoiceKey: 'cloned_private_female',
  })),
  resolveIosSpeechOptions: jest.fn().mockResolvedValue({
    language: 'zh-CN',
    rate: 1.0,
    pitch: 1.0,
  }),
}));

jest.mock('../../services/cloudStreamingTts', () => ({
  createCloudStreamingTtsSession: jest.fn(() => ({
    start: () => mockTtsStart(),
    append: (text: string) => mockTtsAppend(text),
    finish: () => mockTtsFinish(),
    cancel: () => mockTtsCancel(),
  })),
}));

jest.mock('../../services/cloudRealtimeAsr', () => ({
  createCloudRealtimeAsrSession: jest.fn((options: typeof realtimeOptions) => {
    realtimeOptions = options;
    return {
      start: () => mockAsrStart(),
      stop: () => mockAsrStop(),
      cancel: () => mockAsrCancel(),
    };
  }),
}));

jest.mock('../../services/chat', () => ({
  streamChat: jest.fn(),
  cancelAgentRun: jest.fn().mockResolvedValue({ runId: 'run-voice-1', status: 'cancellation_requested' }),
  getAgentTurnStatus: jest.fn().mockResolvedValue(null),
  getConversationMessages: jest.fn().mockResolvedValue({ messages: [], total_messages: 0 }),
}));

jest.mock('../../services/aiConsent', () => ({ ensureAIConsent: jest.fn().mockResolvedValue(true) }));

const mockCreateRealtimeSession = createCloudRealtimeAsrSession as jest.MockedFunction<
  typeof createCloudRealtimeAsrSession
>;
const mockCreateStreamingTtsSession = createCloudStreamingTtsSession as jest.MockedFunction<
  typeof createCloudStreamingTtsSession
>;
const mockStreamChat = streamChat as jest.MockedFunction<typeof streamChat>;
const mockCancelAgentRun = cancelAgentRun as jest.MockedFunction<typeof cancelAgentRun>;
const mockGetAgentTurnStatus = getAgentTurnStatus as jest.MockedFunction<typeof getAgentTurnStatus>;
const mockLoadVoiceStyle = loadVoiceStyle as jest.MockedFunction<typeof loadVoiceStyle>;

const finalAsrResult = (text: string) => ({
  text,
  provider: 'dashscope_qwen_asr_realtime',
  durationMs: 800,
  empty: text.length === 0,
});

describe('useVoiceConversation', () => {
  it('cancels capture on background and does not resume or submit a partial on foreground', async () => {
    let onState: ((state: AppStateStatus) => void) | undefined;
    const listener = jest.spyOn(AppState, 'addEventListener').mockImplementation((_type, callback) => {
      onState = callback;
      return { remove: jest.fn() };
    });
    const { result, unmount } = renderHook(() => useVoiceConversation());
    try {
      await act(async () => { await result.current.startListening(); });
      act(() => { realtimeOptions?.onTranscript('未提交的片段'); });
      await act(async () => { onState?.('background'); });
      expect(mockAsrCancel).toHaveBeenCalledTimes(1);
      expect(result.current.state).toBe('idle');
      await act(async () => { await result.current.startListening(); });
      expect(mockAsrStart).toHaveBeenCalledTimes(1);
      await act(async () => { onState?.('active'); });
      expect(mockAsrStart).toHaveBeenCalledTimes(1);
      expect(mockStreamChat).not.toHaveBeenCalled();
    } finally {
      unmount();
      listener.mockRestore();
    }
  });

  it('does not begin deferred direct speech after background invalidates its generation', async () => {
    let onState: ((state: AppStateStatus) => void) | undefined;
    const listener = jest.spyOn(AppState, 'addEventListener').mockImplementation((_type, callback) => {
      onState = callback;
      return { remove: jest.fn() };
    });
    const { result, unmount } = renderHook(() => useVoiceConversation());
    let releaseStyle!: (style: any) => void;
    mockLoadVoiceStyle.mockImplementationOnce(() => new Promise(resolve => { releaseStyle = resolve; }));
    try {
      let speaking!: Promise<void>;
      act(() => { speaking = result.current.speakDirect('不应在后台播放。', { thenListen: true }); });
      await act(async () => { onState?.('background'); });
      await act(async () => { releaseStyle('cloud_cloned_private_female'); await speaking; });
      expect(mockTtsStart).not.toHaveBeenCalled();
      expect(mockAsrStart).not.toHaveBeenCalled();
      expect(result.current.state).toBe('idle');
    } finally {
      unmount();
      listener.mockRestore();
    }
  });

  it('surfaces a runtime ASR disconnect and never submits the buffered partial', async () => {
    jest.useFakeTimers();
    const { result, unmount } = renderHook(() => useVoiceConversation());
    await act(async () => { await result.current.startListening(); });
    act(() => { realtimeOptions?.onTranscript('未完成的输入'); });
    await act(async () => {
      realtimeOptions?.onError?.(new Error('云端实时语音连接已断开'));
      await Promise.resolve();
    });
    expect(result.current.state).toBe('error');
    expect(result.current.error).toBe('云端实时语音连接已断开');
    await act(async () => { jest.advanceTimersByTime(2000); });
    expect(mockAsrStop).not.toHaveBeenCalled();
    expect(mockStreamChat).not.toHaveBeenCalled();
    unmount();
  });

  beforeEach(() => {
    jest.clearAllMocks();
    jest.useRealTimers();
    AppState.currentState = 'active';
    jest.spyOn(AppState, 'addEventListener').mockReturnValue({ remove: jest.fn() });
    realtimeOptions = null;
    (setAudioModeAsync as jest.Mock).mockResolvedValue(undefined);
    (ensureAIConsent as jest.Mock).mockResolvedValue(true);
    mockLoadVoiceStyle.mockResolvedValue('cloud_cloned_private_female');
    mockAsrStart.mockResolvedValue(true);
    mockAsrStop.mockResolvedValue(finalAsrResult(''));
    mockAsrCancel.mockResolvedValue(undefined);
    mockTtsStart.mockResolvedValue(true);
    mockTtsAppend.mockResolvedValue(undefined);
    mockTtsFinish.mockResolvedValue(undefined);
    mockTtsCancel.mockResolvedValue(undefined);
    mockGetAgentTurnStatus.mockResolvedValue(null);
    mockStreamChat.mockImplementation(async function* () {
      yield { type: 'done', conversationId: 42, runId: 'run-default' } as any;
    });
  });

  afterEach(() => { jest.restoreAllMocks(); });

  it.each(['。', ' …！？ ', '\u200b，\n。', '🎤'])('does not submit non-speech final ASR text %j', async (text) => {
    mockAsrStop.mockResolvedValue(finalAsrResult(text));
    const { result, unmount } = renderHook(() => useVoiceConversation());
    await act(async () => { await result.current.startListening(); });
    await act(async () => { await result.current.stopListening(); });
    expect(mockStreamChat).not.toHaveBeenCalled();
    expect(result.current.turns).toEqual([]);
    expect(result.current.transcript).toBe('');
    expect(result.current.state).toBe('idle');
    unmount();
  });

  it.each(['好', '不', '1', '３', 'é', 'نعم', '是。'])('preserves short meaningful final ASR text %j', async (text) => {
    mockAsrStop.mockResolvedValue(finalAsrResult(text));
    const { result, unmount } = renderHook(() => useVoiceConversation());
    await act(async () => { await result.current.startListening(); });
    await act(async () => { await result.current.stopListening(); });
    expect(mockStreamChat.mock.calls[0][0]).toBe(text);
    unmount();
  });

  it('does not use punctuation-only partials to trigger automatic submission', async () => {
    jest.useFakeTimers();
    const { result, unmount } = renderHook(() => useVoiceConversation());
    await act(async () => { await result.current.startListening(); });
    act(() => { realtimeOptions?.onTranscript('。'); });
    await act(async () => { jest.advanceTimersByTime(2000); });
    expect(mockAsrStop).not.toHaveBeenCalled();
    expect(mockStreamChat).not.toHaveBeenCalled();
    expect(result.current.transcript).toBe('');
    unmount();
  });

  // A normal timeout cannot interrupt a synchronous JS loop. Bound only the
  // sentence-boundary matcher so a regression fails instead of hanging Jest.
  function boundSentenceScans() {
    const original = String.prototype.match;
    let scans = 0;
    jest.spyOn(String.prototype, 'match').mockImplementation(function (this: string, pattern: any) {
      if (pattern instanceof RegExp && pattern.source.includes('。！？') && ++scans > 100) {
        throw new Error('sentence splitter made no forward progress');
      }
      return original.call(this, pattern);
    });
  }

  it.each([
    [['好。', '接下来保持轻松活动。'], '好。接下来保持轻松活动。'],
    [['是。'], '是。'],
    [['1.', ' 今天走3.6公里。'], '今天走3点6公里。'],
    [['好。是。不。再继续。'], '好。是。不。再继续。'],
  ])('drains streamed short phrases without blocking the JS event loop: %j', async (chunks, expected) => {
    boundSentenceScans();
    mockAsrStop.mockResolvedValue(finalAsrResult('请继续'));
    mockStreamChat.mockImplementation(async function* () {
      for (const content of chunks) yield { type: 'token', content } as any;
      yield { type: 'done', conversationId: 42 } as any;
    });
    const { result, unmount } = renderHook(() => useVoiceConversation());
    await act(async () => { await result.current.startListening(); });
    await act(async () => { await result.current.stopListening(); });
    expect(result.current.error).toBeNull();
    expect(result.current.state).toBe('idle');
    // Cloud chunking inserts inter-sentence pause spaces; content must survive.
    expect(mockTtsAppend.mock.calls.map(([text]) => text).join('').replace(/\s/g, ''))
      .toBe(expected.replace(/\s/g, ''));
    expect(mockTtsFinish).toHaveBeenCalledTimes(1);
    unmount();
  });

  it('can exit an in-flight short-phrase reply and cancels speech/run without reopening capture', async () => {
    boundSentenceScans();
    mockAsrStop.mockResolvedValue(finalAsrResult('请继续'));
    let reachedShortPhrase = false;
    mockStreamChat.mockImplementation(async function* (...args: any[]) {
      yield { type: 'persisted', runId: 'run-short-phrase' } as any;
      yield { type: 'token', content: '先保持轻松活动。' } as any;
      yield { type: 'token', content: '好。' } as any;
      reachedShortPhrase = true;
      const signal = args[3] as AbortSignal;
      await new Promise<void>((_resolve, reject) => {
        signal.addEventListener('abort', () => reject(new Error('aborted')), { once: true });
      });
    });
    const { result, unmount } = renderHook(() => useVoiceConversation());
    await act(async () => { await result.current.startListening(); });
    let turn!: Promise<void>;
    act(() => { turn = result.current.stopListening(); });
    await waitFor(() => expect(reachedShortPhrase).toBe(true));
    await act(async () => { result.current.reset(); unmount(); await turn; });
    expect(mockTtsCancel).toHaveBeenCalled();
    expect(mockCancelAgentRun).toHaveBeenCalledWith('run-short-phrase');
    expect(mockAsrStart).toHaveBeenCalledTimes(1);
  });

  it('starts cloud realtime ASR and renders partial transcript without submitting it', async () => {
    const { result, unmount } = renderHook(() => useVoiceConversation());

    await act(async () => { await result.current.startListening(); });

    expect(mockCreateRealtimeSession).toHaveBeenCalledTimes(1);
    expect(mockAsrStart).toHaveBeenCalledTimes(1);
    expect(result.current.state).toBe('listening');

    act(() => { realtimeOptions?.onTranscript('正在记录这句话'); });

    expect(result.current.transcript).toBe('正在记录这句话');
    expect(mockStreamChat).not.toHaveBeenCalled();
    unmount();
  });

  it('waits for authoritative final text and submits it exactly once after silence', async () => {
    jest.useFakeTimers();
    mockAsrStop.mockResolvedValue(finalAsrResult('最终识别文本'));
    const { result, unmount } = renderHook(() => useVoiceConversation());
    await act(async () => { await result.current.startListening(); });

    act(() => { realtimeOptions?.onTranscript('中间识别'); });
    await act(async () => {
      jest.advanceTimersByTime(1200);
      await Promise.resolve();
      await Promise.resolve();
    });

    await waitFor(() => expect(mockStreamChat).toHaveBeenCalledTimes(1));
    expect(mockAsrStop).toHaveBeenCalledTimes(1);
    expect(mockStreamChat.mock.calls[0][0]).toBe('最终识别文本');
    expect(mockStreamChat.mock.calls[0][5]).toBe('voice');
    expect(mockStreamChat.mock.calls[0][6]).toMatch(/^voice-turn-\d+-\d+$/);

    await act(async () => { await result.current.stopListening(); });
    expect(mockStreamChat).toHaveBeenCalledTimes(1);
    unmount();
  });

  it('cancels the matching server run before opening a barge-in microphone session', async () => {
    mockAsrStop.mockResolvedValue(finalAsrResult('先回答这个问题'));
    let persisted!: () => void;
    const persistedPromise = new Promise<void>(resolve => { persisted = resolve; });
    mockStreamChat.mockImplementation(async function* (...args: any[]) {
      const signal = args[3] as AbortSignal;
      yield { type: 'persisted', clientTurnId: args[6], runId: 'run-voice-active' } as any;
      persisted();
      await new Promise<void>((_resolve, reject) => {
        if (signal.aborted) reject(new Error('aborted'));
        else signal.addEventListener('abort', () => reject(new Error('aborted')), { once: true });
      });
    });
    const { result, unmount } = renderHook(() => useVoiceConversation());

    await act(async () => { await result.current.startListening(); });
    act(() => { realtimeOptions?.onTranscript('先回答'); });
    act(() => { void result.current.stopListening(); });
    await act(async () => { await persistedPromise; });

    await act(async () => { await result.current.startListening(); });

    expect(mockCancelAgentRun).toHaveBeenCalledWith('run-voice-active');
    expect(mockCancelAgentRun.mock.invocationCallOrder[0])
      .toBeLessThan(mockAsrStart.mock.invocationCallOrder[1]);
    expect(mockCreateRealtimeSession).toHaveBeenCalledTimes(2);
    expect(result.current.state).toBe('listening');
    unmount();
  });

  it('does not open a competing microphone session when server cancellation fails', async () => {
    mockAsrStop.mockResolvedValue(finalAsrResult('仍在处理的问题'));
    let persisted!: () => void;
    const persistedPromise = new Promise<void>(resolve => { persisted = resolve; });
    mockStreamChat.mockImplementation(async function* (...args: any[]) {
      const signal = args[3] as AbortSignal;
      yield { type: 'persisted', clientTurnId: args[6], runId: 'run-cancel-fails' } as any;
      persisted();
      await new Promise<void>((_resolve, reject) => {
        signal.addEventListener('abort', () => reject(new Error('aborted')), { once: true });
      });
    });
    mockCancelAgentRun.mockRejectedValueOnce(new Error('private gateway detail'));
    const { result, unmount } = renderHook(() => useVoiceConversation());

    await act(async () => { await result.current.startListening(); });
    act(() => { void result.current.stopListening(); });
    await act(async () => { await persistedPromise; });
    await act(async () => { await result.current.startListening(); });

    expect(mockCreateRealtimeSession).toHaveBeenCalledTimes(1);
    expect(result.current.state).toBe('error');
    expect(result.current.error).toBe('上一轮对话未能安全停止，请稍后重试');
    unmount();
  });

  it('fails closed when an active turn still has no cancellable run identity', async () => {
    mockAsrStop.mockResolvedValue(finalAsrResult('仍在后台执行的问题'));
    mockGetAgentTurnStatus.mockResolvedValue({
      clientTurnId: 'voice-turn-pending',
      status: 'running',
      requestPersisted: true,
      responsePersisted: false,
      retryable: false,
    });
    let persisted!: () => void;
    const persistedPromise = new Promise<void>(resolve => { persisted = resolve; });
    mockStreamChat.mockImplementation(async function* (...args: any[]) {
      const signal = args[3] as AbortSignal;
      yield { type: 'persisted', clientTurnId: args[6] } as any;
      persisted();
      await new Promise<void>((_resolve, reject) => {
        signal.addEventListener('abort', () => reject(new Error('aborted')), { once: true });
      });
    });
    const { result, unmount } = renderHook(() => useVoiceConversation());

    await act(async () => { await result.current.startListening(); });
    act(() => { void result.current.stopListening(); });
    await act(async () => { await persistedPromise; });
    await act(async () => { await result.current.startListening(); });

    expect(mockGetAgentTurnStatus).toHaveBeenCalledTimes(3);
    expect(mockCancelAgentRun).not.toHaveBeenCalled();
    expect(mockCreateRealtimeSession).toHaveBeenCalledTimes(1);
    expect(result.current.state).toBe('error');
    expect(result.current.error).toBe('上一轮对话未能安全停止，请稍后重试');
    unmount();
  });

  it('aborts a turn interrupted while voice style is still loading', async () => {
    mockAsrStop.mockResolvedValue(finalAsrResult('样式加载中的问题'));
    const { result, unmount } = renderHook(() => useVoiceConversation());
    await act(async () => { await result.current.startListening(); });
    let releaseStyle!: (style: 'cloud_cloned_private_female') => void;
    mockLoadVoiceStyle.mockImplementationOnce(() => new Promise(resolve => { releaseStyle = resolve; }));

    let stop!: Promise<void>;
    act(() => { stop = result.current.stopListening(); });
    await waitFor(() => expect(mockLoadVoiceStyle).toHaveBeenCalledTimes(2));
    await act(async () => { await result.current.startListening(); });
    await act(async () => {
      releaseStyle('cloud_cloned_private_female');
      await stop;
    });

    expect(mockStreamChat).not.toHaveBeenCalled();
    expect(mockCreateRealtimeSession).toHaveBeenCalledTimes(2);
    expect(result.current.state).toBe('listening');
    unmount();
  });

  it('cancels a realtime ASR start that finishes after consent withdrawal', async () => {
    let release!: (started: boolean) => void;
    mockAsrStart.mockImplementationOnce(() => new Promise<boolean>(resolve => { release = resolve; }));
    const { result, unmount } = renderHook(() => useVoiceConversation());
    let start!: Promise<void>;

    await act(async () => { start = result.current.startListening(); });
    await act(async () => { invalidateAIConsent(); });
    await act(async () => { release(true); await start; });

    expect(mockAsrCancel).toHaveBeenCalled();
    expect(result.current.state).toBe('idle');
    unmount();
  });

  it('does not submit a final transcript that arrives after reset', async () => {
    let finish!: (result: ReturnType<typeof finalAsrResult>) => void;
    mockAsrStop.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    const { result, unmount } = renderHook(() => useVoiceConversation());
    await act(async () => { await result.current.startListening(); });
    act(() => { realtimeOptions?.onTranscript('不应发送'); });

    let stop!: Promise<void>;
    act(() => { stop = result.current.stopListening(); });
    act(() => { result.current.reset(); });
    await act(async () => {
      finish(finalAsrResult('不应发送'));
      await stop;
    });

    expect(mockAsrCancel).toHaveBeenCalled();
    expect(mockStreamChat).not.toHaveBeenCalled();
    expect(result.current.state).toBe('idle');
    unmount();
  });

  it('does not start cloud ASR after AI consent is declined', async () => {
    (ensureAIConsent as jest.Mock).mockResolvedValueOnce(false);
    const { result, unmount } = renderHook(() => useVoiceConversation());
    await act(async () => { await result.current.startListening(); });
    expect(mockCreateRealtimeSession).not.toHaveBeenCalled();
    unmount();
  });

  it('keeps long direct voice-chat scripts on one private streaming voice session', async () => {
    const longText = Array.from({ length: 35 }, (_, i) => (
      `第${i + 1}段：结合你的体检、基因、运动和睡眠数据，今天建议优先执行一个明确动作。`
    )).join(' ');
    const expectedChunks = splitTextForCloudTts(longText);
    expect(expectedChunks.length).toBeGreaterThan(1);

    const { result, unmount } = renderHook(() => useVoiceConversation());
    await act(async () => { await result.current.speakDirect(longText); });

    await waitFor(() => expect(mockTtsAppend).toHaveBeenCalled());
    expect(mockCreateStreamingTtsSession).toHaveBeenCalledTimes(1);
    expect(mockTtsAppend.mock.calls.every(([text]) => text.length <= 480)).toBe(true);
    expect(mockTtsAppend.mock.calls[0][0]).toBe(expectedChunks[0]);
    expect(mockTtsFinish).toHaveBeenCalledTimes(1);
    expect(mockSpeechSpeak).not.toHaveBeenCalled();
    unmount();
  });

  it('cancels capture and never reopens the microphone after unmount', async () => {
    mockTtsFinish.mockImplementationOnce(() => new Promise<void>(() => undefined));
    const longText = Array.from({ length: 35 }, (_, i) => (
      `第${i + 1}段：离开语音页面后，不应继续播放，也不应重新启动麦克风。`
    )).join(' ');
    const { result, unmount } = renderHook(() => useVoiceConversation());

    await act(async () => { await result.current.startListening(); });
    act(() => { result.current.reset(); });
    expect(mockAsrCancel).toHaveBeenCalledTimes(1);

    act(() => { void result.current.speakDirect(longText, { thenListen: true }); });
    await waitFor(() => expect(mockTtsAppend).toHaveBeenCalled());
    act(() => { unmount(); });
    await new Promise(resolve => setTimeout(resolve, 350));

    expect(mockTtsCancel).toHaveBeenCalled();
    expect(mockCreateRealtimeSession).toHaveBeenCalledTimes(1);
  });

  it('starts streaming speech at a natural phrase boundary before the Agent turn completes', async () => {
    mockAsrStop.mockResolvedValue(finalAsrResult('给我一个恢复建议'));
    let releaseTurn!: () => void;
    mockStreamChat.mockImplementation(async function* () {
      yield { type: 'token', content: '今天先降低强度，' } as any;
      await new Promise<void>(resolve => { releaseTurn = resolve; });
      yield { type: 'token', content: '晚些时候再看恢复状态。' } as any;
      yield { type: 'done', conversationId: 42, runId: 'run-streaming-tts' } as any;
    });
    const { result, unmount } = renderHook(() => useVoiceConversation());
    await act(async () => { await result.current.startListening(); });

    act(() => { void result.current.stopListening(); });
    await waitFor(() => expect(mockTtsAppend).toHaveBeenCalledWith('今天先降低强度，'));
    expect(mockTtsFinish).not.toHaveBeenCalled();

    await act(async () => { releaseTurn(); });
    await waitFor(() => expect(mockTtsFinish).toHaveBeenCalledTimes(1));
    unmount();
  });

  it('cancels streaming speech before opening the barge-in microphone', async () => {
    mockAsrStop.mockResolvedValue(finalAsrResult('先给我一个建议'));
    let releaseTurn!: () => void;
    mockStreamChat.mockImplementation(async function* (...args: any[]) {
      yield { type: 'persisted', clientTurnId: args[6], runId: 'run-speaking' } as any;
      yield { type: 'token', content: '先保持轻松活动，' } as any;
      await new Promise<void>((resolve, reject) => {
        releaseTurn = resolve;
        const signal = args[3] as AbortSignal;
        signal.addEventListener('abort', () => reject(new Error('aborted')), { once: true });
      });
    });
    const { result, unmount } = renderHook(() => useVoiceConversation());
    await act(async () => { await result.current.startListening(); });
    act(() => { void result.current.stopListening(); });
    await waitFor(() => expect(mockTtsAppend).toHaveBeenCalled());

    await act(async () => { await result.current.startListening(); });

    expect(mockTtsCancel).toHaveBeenCalled();
    expect(mockTtsCancel.mock.invocationCallOrder[0])
      .toBeLessThan(mockAsrStart.mock.invocationCallOrder[1]);
    expect(mockCancelAgentRun).toHaveBeenCalledWith('run-speaking');
    releaseTurn?.();
    unmount();
  });
});
