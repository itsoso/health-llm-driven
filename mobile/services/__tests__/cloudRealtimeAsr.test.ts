import { requireAIConsent } from '../aiConsent';
import { aiConsentRevision } from '../aiConsentState';
jest.mock('../aiConsent', () => ({ requireAIConsent: jest.fn().mockResolvedValue(undefined) }));
const mockConsentListeners = new Set<() => void>();
jest.mock('../aiConsentState', () => ({
  ...jest.requireActual('../aiConsentState'),
  aiConsentRevision: jest.fn().mockReturnValue(0),
  subscribeAIConsentInvalidation: (listener: () => void) => {
    mockConsentListeners.add(listener);
    return () => { mockConsentListeners.delete(listener); };
  },
}));

import {
  createCloudRealtimeAsrSession,
  realtimeAsrWebSocketUrl,
  type RealtimeAsrDependencies,
} from '../cloudRealtimeAsr';

class FakeSocket {
  readyState = 0;
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;

  send(payload: string) {
    this.sent.push(payload);
  }

  close() {
    this.readyState = 3;
    this.onclose?.();
  }

  open() {
    this.readyState = 1;
    this.onopen?.();
  }

  receive(payload: object) {
    this.onmessage?.({ data: JSON.stringify(payload) });
  }
}

async function flushMicrotasks() {
  for (let index = 0; index < 8; index += 1) await Promise.resolve();
}

describe('cloudRealtimeAsr', () => {
  beforeEach(() => {
    mockConsentListeners.clear();
    (requireAIConsent as jest.Mock).mockReset().mockResolvedValue(undefined);
    (aiConsentRevision as jest.Mock).mockReset().mockReturnValue(0);
  });

  const consentDependencies = (): RealtimeAsrDependencies => ({
    getAuthToken: jest.fn().mockResolvedValue('jwt-token'),
    openSocket: jest.fn(() => new FakeSocket()),
    startPcmCapture: jest.fn().mockResolvedValue(undefined),
    stopPcmCapture: jest.fn().mockResolvedValue(undefined),
    cancelPcmCapture: jest.fn().mockResolvedValue(undefined),
  });

  it('does not open a socket or microphone when AI disclosure is declined', async () => {
    (requireAIConsent as jest.Mock).mockRejectedValueOnce(new Error('ai_consent_required'));
    const dependencies = consentDependencies();
    const session = createCloudRealtimeAsrSession({ onTranscript: jest.fn() }, dependencies);
    const started = session.start();
    const outcome = started.catch(error => error.message);
    await flushMicrotasks();
    expect(dependencies.openSocket).not.toHaveBeenCalled();
    await expect(outcome).resolves.toBe('ai_consent_required');
    expect(dependencies.startPcmCapture).not.toHaveBeenCalled();
  });

  it('waits for disclosure and ignores a grant after the gesture was cancelled', async () => {
    let grant!: () => void;
    (requireAIConsent as jest.Mock).mockImplementationOnce(() => new Promise<void>(resolve => { grant = resolve; }));
    const dependencies = consentDependencies();
    const session = createCloudRealtimeAsrSession({ onTranscript: jest.fn() }, dependencies);
    const started = session.start();
    await flushMicrotasks();
    expect(dependencies.openSocket).not.toHaveBeenCalled();
    await session.cancel();
    grant();
    await expect(started).resolves.toBe(false);
    expect(dependencies.openSocket).not.toHaveBeenCalled();
    expect(dependencies.startPcmCapture).not.toHaveBeenCalled();
  });

  it('rejects an account change while loading the socket credential after consent', async () => {
    const dependencies = consentDependencies();
    (dependencies.getAuthToken as jest.Mock).mockImplementationOnce(async () => {
      (aiConsentRevision as jest.Mock).mockReturnValue(1);
      return 'new-account-token';
    });
    const session = createCloudRealtimeAsrSession({ onTranscript: jest.fn() }, dependencies);
    const outcome = session.start().catch(error => error.message);
    await flushMicrotasks();
    expect(dependencies.openSocket).not.toHaveBeenCalled();
    await expect(outcome).resolves.toBe('auth_session_changed');
  });

  it.each(['before-ready', 'recording', 'finishing'])('stops all ASR dispatch when consent is revoked %s', async (phase) => {
    const socket = new FakeSocket();
    let chunk: ((value: string) => void) | undefined;
    let finishCapture!: () => void;
    const dependencies = consentDependencies();
    (dependencies.openSocket as jest.Mock).mockReturnValue(socket);
    (dependencies.startPcmCapture as jest.Mock).mockImplementation(async (onChunk) => { chunk = onChunk; });
    (dependencies.stopPcmCapture as jest.Mock).mockImplementation(() => new Promise<void>(resolve => { finishCapture = resolve; }));
    const session = createCloudRealtimeAsrSession({ onTranscript: jest.fn(), onError: jest.fn() }, dependencies);
    const outcome = session.start().catch(error => error.message);
    await flushMicrotasks();
    socket.open();
    if (phase !== 'before-ready') {
      socket.receive({ type: 'ready' });
      await expect(outcome).resolves.toBe(true);
    }
    const stop = phase === 'finishing' ? session.stop().catch(error => error.message) : null;
    await flushMicrotasks();
    (aiConsentRevision as jest.Mock).mockReturnValue(1);
    for (const listener of [...mockConsentListeners]) listener();
    await flushMicrotasks();
    expect(socket.readyState).toBe(3);
    socket.receive({ type: 'ready' });
    chunk?.('must-not-leave-device');
    if (phase === 'finishing') { finishCapture(); await stop; }
    if (phase === 'before-ready') {
      await expect(outcome).resolves.toBe('ai_consent_required');
      expect(dependencies.startPcmCapture).not.toHaveBeenCalled();
    }
    expect(socket.sent.filter(value => ['audio', 'finish'].includes(JSON.parse(value).type))).toEqual([]);
    expect(mockConsentListeners.size).toBe(0);
    await session.cancel();
  });

  it.each([undefined, { remove: jest.fn() }])('fails closed on a recording disconnect with subscription %p', async (subscription) => {
    const socket = new FakeSocket();
    const onError = jest.fn();
    const dependencies: RealtimeAsrDependencies = {
      getAuthToken: jest.fn().mockResolvedValue('jwt-token'),
      openSocket: jest.fn(() => socket),
      startPcmCapture: jest.fn().mockResolvedValue(subscription),
      stopPcmCapture: jest.fn().mockResolvedValue(undefined),
      cancelPcmCapture: jest.fn().mockResolvedValue(undefined),
    };
    const session = createCloudRealtimeAsrSession({ onTranscript: jest.fn(), onError }, dependencies);
    const started = session.start();
    await flushMicrotasks();
    socket.open();
    socket.receive({ type: 'ready' });
    await started;

    socket.close();
    await flushMicrotasks();

    expect(dependencies.cancelPcmCapture).toHaveBeenCalledTimes(1);
    expect(onError).toHaveBeenCalledWith(expect.objectContaining({ message: '云端实时语音连接已断开' }));
    await expect(session.stop()).rejects.toThrow('云端实时语音连接已断开');
    await session.cancel();
    expect(dependencies.cancelPcmCapture).toHaveBeenCalledTimes(1);
  });

  it('waits for pending native startup before cancelling exactly once', async () => {
    const socket = new FakeSocket();
    let resolveCapture!: () => void;
    const dependencies: RealtimeAsrDependencies = {
      getAuthToken: jest.fn().mockResolvedValue('jwt-token'),
      openSocket: jest.fn(() => socket),
      startPcmCapture: jest.fn(() => new Promise<void>(resolve => { resolveCapture = resolve; })),
      stopPcmCapture: jest.fn().mockResolvedValue(undefined),
      cancelPcmCapture: jest.fn().mockResolvedValue(undefined),
    };
    const session = createCloudRealtimeAsrSession({ onTranscript: jest.fn() }, dependencies);
    const started = session.start();
    await flushMicrotasks();
    socket.open();
    socket.receive({ type: 'ready' });
    let cleanupSettled = false;
    const cancelled = session.cancel().then(() => { cleanupSettled = true; });
    await flushMicrotasks();
    await flushMicrotasks();
    expect(cleanupSettled).toBe(false);
    resolveCapture();
    await cancelled;
    await expect(started).resolves.toBe(false);
    expect(dependencies.cancelPcmCapture).toHaveBeenCalledTimes(1);
    await session.cancel();
    expect(dependencies.cancelPcmCapture).toHaveBeenCalledTimes(1);
  });

  it('does not cancel another microphone owner when this session never started capture', async () => {
    const dependencies: RealtimeAsrDependencies = {
      getAuthToken: jest.fn().mockResolvedValue('jwt-token'),
      openSocket: jest.fn(() => new FakeSocket()),
      startPcmCapture: jest.fn().mockResolvedValue(undefined),
      stopPcmCapture: jest.fn().mockResolvedValue(undefined),
      cancelPcmCapture: jest.fn().mockResolvedValue(undefined),
    };
    const session = createCloudRealtimeAsrSession({ onTranscript: jest.fn() }, dependencies);
    await session.cancel();
    expect(dependencies.cancelPcmCapture).not.toHaveBeenCalled();
  });

  it('cancels a handshake when stop wins before the cloud is ready', async () => {
    const socket = new FakeSocket();
    const dependencies: RealtimeAsrDependencies = {
      getAuthToken: jest.fn().mockResolvedValue('jwt-token'),
      openSocket: jest.fn(() => socket),
      startPcmCapture: jest.fn().mockResolvedValue(undefined),
      stopPcmCapture: jest.fn().mockResolvedValue(undefined),
      cancelPcmCapture: jest.fn().mockResolvedValue(undefined),
    };
    const session = createCloudRealtimeAsrSession({ onTranscript: jest.fn() }, dependencies);
    const started = session.start();
    await flushMicrotasks();
    await expect(session.stop()).resolves.toEqual(expect.objectContaining({ empty: true }));
    socket.receive({ type: 'ready' });
    await flushMicrotasks();
    expect(dependencies.startPcmCapture).not.toHaveBeenCalled();
    await expect(started).resolves.toBe(false);
    expect(socket.readyState).toBe(3);
  });

  it('keeps a replacement capture behind old cleanup and never cancels the replacement', async () => {
    const sockets = [new FakeSocket(), new FakeSocket()];
    let resolveCleanup!: () => void;
    const dependencies: RealtimeAsrDependencies = {
      getAuthToken: jest.fn().mockResolvedValue('jwt-token'),
      openSocket: jest.fn().mockReturnValueOnce(sockets[0]).mockReturnValueOnce(sockets[1]),
      startPcmCapture: jest.fn().mockResolvedValue(undefined),
      stopPcmCapture: jest.fn().mockResolvedValue(undefined),
      cancelPcmCapture: jest.fn().mockImplementationOnce(() => new Promise<void>(resolve => {
        resolveCleanup = resolve;
      })).mockResolvedValue(undefined),
    };
    const oldSession = createCloudRealtimeAsrSession({ onTranscript: jest.fn() }, dependencies);
    const newSession = createCloudRealtimeAsrSession({ onTranscript: jest.fn() }, dependencies);
    const oldStart = oldSession.start();
    await flushMicrotasks();
    sockets[0].open();
    sockets[0].receive({ type: 'ready' });
    await oldStart;
    sockets[0].close();
    const newStart = newSession.start();
    await flushMicrotasks();
    sockets[1].open();
    sockets[1].receive({ type: 'ready' });
    await flushMicrotasks();
    expect(dependencies.startPcmCapture).toHaveBeenCalledTimes(1);
    resolveCleanup();
    await expect(newStart).resolves.toBe(true);
    await oldSession.cancel();
    expect(dependencies.cancelPcmCapture).toHaveBeenCalledTimes(1);
    await newSession.cancel();
    expect(dependencies.cancelPcmCapture).toHaveBeenCalledTimes(2);
  });

  it('reports cleanup failure and does not let a replacement capture acquire the microphone', async () => {
    const sockets = [new FakeSocket(), new FakeSocket()];
    const onError = jest.fn();
    const dependencies: RealtimeAsrDependencies = {
      getAuthToken: jest.fn().mockResolvedValue('jwt-token'),
      openSocket: jest.fn().mockReturnValueOnce(sockets[0]).mockReturnValueOnce(sockets[1]),
      startPcmCapture: jest.fn().mockResolvedValue(undefined),
      stopPcmCapture: jest.fn().mockResolvedValue(undefined),
      cancelPcmCapture: jest.fn().mockRejectedValue(new Error('native cancel failed')),
    };
    const oldSession = createCloudRealtimeAsrSession({ onTranscript: jest.fn(), onError }, dependencies);
    const started = oldSession.start();
    await flushMicrotasks();
    sockets[0].receive({ type: 'ready' });
    await started;
    sockets[0].close();
    await flushMicrotasks();
    expect(onError).toHaveBeenCalledWith(expect.objectContaining({ message: '麦克风采集未能安全停止，请关闭语音后重试' }));
    await expect(oldSession.cancel()).rejects.toThrow('native cancel failed');
    await expect(oldSession.stop()).rejects.toThrow('麦克风采集未能安全停止');

    const replacement = createCloudRealtimeAsrSession({ onTranscript: jest.fn() }, dependencies);
    const nextStart = replacement.start();
    await flushMicrotasks();
    sockets[1].receive({ type: 'ready' });
    await flushMicrotasks();
    expect(dependencies.startPcmCapture).toHaveBeenCalledTimes(1);
    await replacement.cancel();
    await expect(nextStart).resolves.toBe(false);
  });

  it('fails an unsolicited done event and stops native capture', async () => {
    const socket = new FakeSocket();
    const dependencies: RealtimeAsrDependencies = {
      getAuthToken: jest.fn().mockResolvedValue('jwt-token'),
      openSocket: jest.fn(() => socket),
      startPcmCapture: jest.fn().mockResolvedValue(undefined),
      stopPcmCapture: jest.fn().mockResolvedValue(undefined),
      cancelPcmCapture: jest.fn().mockResolvedValue(undefined),
    };
    const session = createCloudRealtimeAsrSession({ onTranscript: jest.fn() }, dependencies);
    const started = session.start();
    await flushMicrotasks();
    socket.receive({ type: 'ready' });
    await started;
    socket.receive({ type: 'done' });
    await expect(session.stop()).rejects.toThrow('云端实时语音连接提前结束');
    await session.cancel();
    expect(dependencies.cancelPcmCapture).toHaveBeenCalledTimes(1);
  });

  it('rejects finalization if the socket closes during native stop', async () => {
    const socket = new FakeSocket();
    let resolveStop!: () => void;
    const dependencies: RealtimeAsrDependencies = {
      getAuthToken: jest.fn().mockResolvedValue('jwt-token'),
      openSocket: jest.fn(() => socket),
      startPcmCapture: jest.fn().mockResolvedValue(undefined),
      stopPcmCapture: jest.fn(() => new Promise<void>(resolve => { resolveStop = resolve; })),
      cancelPcmCapture: jest.fn().mockResolvedValue(undefined),
    };
    const session = createCloudRealtimeAsrSession({ onTranscript: jest.fn() }, dependencies);
    const started = session.start();
    await flushMicrotasks();
    socket.receive({ type: 'ready' });
    await started;
    const stopped = session.stop();
    socket.close();
    resolveStop();
    await expect(stopped).rejects.toThrow('云端实时语音连接已断开');
    expect(socket.sent).not.toContain(JSON.stringify({ type: 'finish' }));
    expect(dependencies.stopPcmCapture).toHaveBeenCalledTimes(1);
    expect(dependencies.cancelPcmCapture).not.toHaveBeenCalled();
  });

  it('keeps realtime recognition behind the authenticated backend websocket', () => {
    expect(realtimeAsrWebSocketUrl('https://health.executor.life/api'))
      .toBe('wss://health.executor.life/api/chat/transcribe/realtime');
  });

  it('streams native PCM chunks and exposes partial and final cloud transcripts', async () => {
    const socket = new FakeSocket();
    let emitChunk: ((audioBase64: string) => void) | undefined;
    const dependencies: RealtimeAsrDependencies = {
      getAuthToken: jest.fn().mockResolvedValue('jwt-token'),
      openSocket: jest.fn(() => socket as any),
      startPcmCapture: jest.fn(async (onChunk) => {
        emitChunk = onChunk;
      }),
      stopPcmCapture: jest.fn().mockResolvedValue(undefined),
      cancelPcmCapture: jest.fn().mockResolvedValue(undefined),
    };
    const onTranscript = jest.fn();
    const session = createCloudRealtimeAsrSession({ onTranscript }, dependencies);

    const startPromise = session.start();
    await flushMicrotasks();
    socket.open();
    socket.receive({ type: 'ready' });
    await expect(startPromise).resolves.toBe(true);

    emitChunk?.('cGNt');
    expect(socket.sent.map(payload => JSON.parse(payload))).toContainEqual({
      type: 'audio',
      audio: 'cGNt',
    });

    socket.receive({ type: 'partial', text: '记录今天喝水' });
    expect(onTranscript).toHaveBeenLastCalledWith(
      '记录今天喝水',
      expect.objectContaining({ provider: 'dashscope_qwen_asr_realtime', empty: false }),
    );

    const stopPromise = session.stop();
    await flushMicrotasks();
    expect(JSON.parse(socket.sent.at(-1)!)).toEqual({ type: 'finish' });
    socket.receive({
      type: 'final',
      text: '记录今天喝水 500 毫升',
      provider: 'dashscope_qwen_asr_realtime',
      model: 'qwen3-asr-flash-realtime',
      duration_ms: 920,
      confidence: 'high',
    });
    socket.receive({ type: 'done' });

    await expect(stopPromise).resolves.toEqual(expect.objectContaining({
      text: '记录今天喝水 500 毫升',
      provider: 'dashscope_qwen_asr_realtime',
      model: 'qwen3-asr-flash-realtime',
    }));
  });

  it('starts PCM capture only once when the cloud repeats its ready event', async () => {
    const socket = new FakeSocket();
    let resolveCapture!: () => void;
    const dependencies: RealtimeAsrDependencies = {
      getAuthToken: jest.fn().mockResolvedValue('jwt-token'),
      openSocket: jest.fn(() => socket as any),
      startPcmCapture: jest.fn(() => new Promise<void>((resolve) => {
        resolveCapture = resolve;
      })),
      stopPcmCapture: jest.fn().mockResolvedValue(undefined),
      cancelPcmCapture: jest.fn().mockResolvedValue(undefined),
    };
    const session = createCloudRealtimeAsrSession({ onTranscript: jest.fn() }, dependencies);
    const startPromise = session.start();
    await flushMicrotasks();

    socket.receive({ type: 'ready' });
    await flushMicrotasks();
    socket.receive({ type: 'ready' });
    await flushMicrotasks();

    expect(dependencies.startPcmCapture).toHaveBeenCalledTimes(1);
    resolveCapture();
    await expect(startPromise).resolves.toBe(true);
    await session.cancel();
  });

  it('shares one startup promise when start is called concurrently', async () => {
    const socket = new FakeSocket();
    let resolveToken!: (token: string) => void;
    const dependencies: RealtimeAsrDependencies = {
      getAuthToken: jest.fn(() => new Promise<string>(resolve => { resolveToken = resolve; })),
      openSocket: jest.fn(() => socket as any),
      startPcmCapture: jest.fn().mockResolvedValue(undefined),
      stopPcmCapture: jest.fn().mockResolvedValue(undefined),
      cancelPcmCapture: jest.fn().mockResolvedValue(undefined),
    };
    const session = createCloudRealtimeAsrSession({ onTranscript: jest.fn() }, dependencies);

    const firstStart = session.start();
    const secondStart = session.start();
    expect(secondStart).toBe(firstStart);
    await flushMicrotasks();

    resolveToken('jwt-token');
    await flushMicrotasks();
    expect(dependencies.openSocket).toHaveBeenCalledTimes(1);
    socket.open();
    socket.receive({ type: 'ready' });
    await expect(firstStart).resolves.toBe(true);
    await session.cancel();
  });

  it('ignores transcripts that arrive after the cloud session has failed', async () => {
    const socket = new FakeSocket();
    const onTranscript = jest.fn();
    const dependencies: RealtimeAsrDependencies = {
      getAuthToken: jest.fn().mockResolvedValue('jwt-token'),
      openSocket: jest.fn(() => socket as any),
      startPcmCapture: jest.fn().mockResolvedValue(undefined),
      stopPcmCapture: jest.fn().mockResolvedValue(undefined),
      cancelPcmCapture: jest.fn().mockResolvedValue(undefined),
    };
    const session = createCloudRealtimeAsrSession({ onTranscript }, dependencies);
    const startPromise = session.start();
    await flushMicrotasks();
    socket.receive({ type: 'ready' });
    await startPromise;

    socket.receive({ type: 'error', message: '上游连接中断' });
    await flushMicrotasks();
    socket.receive({ type: 'partial', text: '不要回写这段' });
    socket.receive({ type: 'final', text: '也不要回写这段' });
    await flushMicrotasks();

    expect(onTranscript).not.toHaveBeenCalled();
  });

  it('shares one finalization promise when stop is called concurrently', async () => {
    const socket = new FakeSocket();
    const dependencies: RealtimeAsrDependencies = {
      getAuthToken: jest.fn().mockResolvedValue('jwt-token'),
      openSocket: jest.fn(() => socket as any),
      startPcmCapture: jest.fn().mockResolvedValue(undefined),
      stopPcmCapture: jest.fn().mockResolvedValue(undefined),
      cancelPcmCapture: jest.fn().mockResolvedValue(undefined),
    };
    const session = createCloudRealtimeAsrSession({ onTranscript: jest.fn() }, dependencies);
    const startPromise = session.start();
    await flushMicrotasks();
    socket.receive({ type: 'ready' });
    await startPromise;

    const firstStop = session.stop();
    const secondStop = session.stop();
    await flushMicrotasks();

    expect(dependencies.stopPcmCapture).toHaveBeenCalledTimes(1);
    expect(socket.sent.filter(payload => JSON.parse(payload).type === 'finish')).toHaveLength(1);
    socket.receive({ type: 'final', text: '记录喝水' });
    socket.receive({ type: 'done' });

    await expect(Promise.all([firstStop, secondStop])).resolves.toEqual([
      expect.objectContaining({ text: '记录喝水' }),
      expect.objectContaining({ text: '记录喝水' }),
    ]);
  });

  it('cancels capture without committing buffered speech', async () => {
    const socket = new FakeSocket();
    const dependencies: RealtimeAsrDependencies = {
      getAuthToken: jest.fn().mockResolvedValue('jwt-token'),
      openSocket: jest.fn(() => socket as any),
      startPcmCapture: jest.fn().mockResolvedValue(undefined),
      stopPcmCapture: jest.fn().mockResolvedValue(undefined),
      cancelPcmCapture: jest.fn().mockResolvedValue(undefined),
    };
    const session = createCloudRealtimeAsrSession({ onTranscript: jest.fn() }, dependencies);
    const startPromise = session.start();
    await flushMicrotasks();
    socket.open();
    socket.receive({ type: 'ready' });
    await startPromise;

    await Promise.all([session.cancel(), session.cancel()]);

    expect(dependencies.cancelPcmCapture).toHaveBeenCalledTimes(1);
    expect(socket.sent.map(payload => JSON.parse(payload))).toContainEqual({ type: 'cancel' });
    expect(socket.sent.map(payload => JSON.parse(payload))).not.toContainEqual({ type: 'finish' });
  });

  it('stops native capture when the cloud session fails after recording starts', async () => {
    const socket = new FakeSocket();
    const captureSubscription = { remove: jest.fn() } as any;
    const dependencies: RealtimeAsrDependencies = {
      getAuthToken: jest.fn().mockResolvedValue('jwt-token'),
      openSocket: jest.fn(() => socket as any),
      startPcmCapture: jest.fn().mockResolvedValue(captureSubscription),
      stopPcmCapture: jest.fn().mockResolvedValue(undefined),
      cancelPcmCapture: jest.fn().mockResolvedValue(undefined),
    };
    const session = createCloudRealtimeAsrSession({ onTranscript: jest.fn() }, dependencies);
    const startPromise = session.start();
    await flushMicrotasks();
    socket.open();
    socket.receive({ type: 'ready' });
    await startPromise;

    socket.receive({ type: 'error', message: '上游连接中断' });
    await flushMicrotasks();

    expect(dependencies.cancelPcmCapture).toHaveBeenCalledWith(captureSubscription);
    expect(socket.readyState).toBe(3);
  });

  it('settles a pending start when the user cancels before the cloud is ready', async () => {
    const socket = new FakeSocket();
    const dependencies: RealtimeAsrDependencies = {
      getAuthToken: jest.fn().mockResolvedValue('jwt-token'),
      openSocket: jest.fn(() => socket as any),
      startPcmCapture: jest.fn().mockResolvedValue(undefined),
      stopPcmCapture: jest.fn().mockResolvedValue(undefined),
      cancelPcmCapture: jest.fn().mockResolvedValue(undefined),
    };
    const session = createCloudRealtimeAsrSession({ onTranscript: jest.fn() }, dependencies);
    const startPromise = session.start();
    await flushMicrotasks();

    await session.cancel();

    await expect(Promise.race([startPromise, Promise.resolve('still-pending')]))
      .resolves.toBe(false);
  });

  it('does not open a socket when cancellation wins while auth is still pending', async () => {
    const socket = new FakeSocket();
    let resolveToken!: (token: string) => void;
    const dependencies: RealtimeAsrDependencies = {
      getAuthToken: jest.fn(() => new Promise<string>(resolve => { resolveToken = resolve; })),
      openSocket: jest.fn(() => socket as any),
      startPcmCapture: jest.fn().mockResolvedValue(undefined),
      stopPcmCapture: jest.fn().mockResolvedValue(undefined),
      cancelPcmCapture: jest.fn().mockResolvedValue(undefined),
    };
    const session = createCloudRealtimeAsrSession({ onTranscript: jest.fn() }, dependencies);
    const startPromise = session.start();
    await flushMicrotasks();

    await session.cancel();
    resolveToken('jwt-token');

    await expect(startPromise).resolves.toBe(false);
    expect(dependencies.openSocket).not.toHaveBeenCalled();
  });

  it('releases a capture that resolves after the cloud session already failed', async () => {
    const socket = new FakeSocket();
    const captureSubscription = { remove: jest.fn() } as any;
    let resolveCapture: ((subscription: any) => void) | undefined;
    const dependencies: RealtimeAsrDependencies = {
      getAuthToken: jest.fn().mockResolvedValue('jwt-token'),
      openSocket: jest.fn(() => socket as any),
      startPcmCapture: jest.fn(() => new Promise(resolve => { resolveCapture = resolve; })),
      stopPcmCapture: jest.fn().mockResolvedValue(undefined),
      cancelPcmCapture: jest.fn().mockResolvedValue(undefined),
    };
    const session = createCloudRealtimeAsrSession({ onTranscript: jest.fn() }, dependencies);
    const startPromise = session.start();
    await flushMicrotasks();
    socket.open();
    socket.receive({ type: 'ready' });
    await flushMicrotasks();

    socket.receive({ type: 'error', message: '上游连接中断' });
    resolveCapture?.(captureSubscription);

    await expect(startPromise).rejects.toThrow('上游连接中断');
    await flushMicrotasks();
    expect(dependencies.cancelPcmCapture).toHaveBeenCalledWith(captureSubscription);
  });
});
