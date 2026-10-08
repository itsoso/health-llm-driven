import {
  createCloudStreamingTtsSession,
  streamingTtsWebSocketUrl,
  type StreamingTtsDependencies,
} from '../cloudStreamingTts';

class FakeSocket {
  readyState = 0;
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;

  send(payload: string) { this.sent.push(payload); }
  close() { this.readyState = 3; this.onclose?.(); }
  open() { this.readyState = 1; this.onopen?.(); }
  receive(payload: object) { this.onmessage?.({ data: JSON.stringify(payload) }); }
}

async function flushMicrotasks(times = 4) {
  for (let index = 0; index < times; index += 1) await Promise.resolve();
}

describe('cloudStreamingTts', () => {
  it.each(['close', 'error'])('stops and preserves a terminal %s before finish is called', async (failure) => {
    const socket = new FakeSocket();
    const dependencies: StreamingTtsDependencies = {
      requireAIConsent: jest.fn().mockResolvedValue(undefined),
      getAuthToken: jest.fn().mockResolvedValue('jwt-token'),
      openSocket: jest.fn(() => socket),
      startPcmPlayback: jest.fn().mockResolvedValue(undefined),
      enqueuePcmPlayback: jest.fn().mockResolvedValue(undefined),
      finishPcmPlayback: jest.fn().mockResolvedValue(undefined),
      stopPcmPlayback: jest.fn().mockResolvedValue(undefined),
    };
    const session = createCloudStreamingTtsSession({ voiceKey: 'warm_female' }, dependencies);
    const start = session.start();
    await flushMicrotasks();
    socket.open();
    socket.receive({ type: 'ready' });
    await start;
    await session.append('hello');
    if (failure === 'close') socket.close();
    else socket.receive({ type: 'error', message: 'provider failed' });
    await flushMicrotasks(12);
    expect(dependencies.stopPcmPlayback).toHaveBeenCalledTimes(1);
    await expect(session.finish()).rejects.toThrow(failure === 'close' ? '连接已断开' : 'provider failed');
    expect(dependencies.finishPcmPlayback).not.toHaveBeenCalled();
  });

  it('holds the shared player until fire-and-forget cancellation settles native start and stop', async () => {
    const oldSocket = new FakeSocket();
    const newSocket = new FakeSocket();
    let releaseStart!: () => void;
    let releaseStop!: () => void;
    const dependencies: StreamingTtsDependencies = {
      requireAIConsent: jest.fn().mockResolvedValue(undefined),
      getAuthToken: jest.fn().mockResolvedValue('jwt-token'),
      openSocket: jest.fn().mockReturnValueOnce(oldSocket).mockReturnValueOnce(newSocket),
      startPcmPlayback: jest.fn().mockImplementationOnce(() => new Promise<void>(resolve => { releaseStart = resolve; })).mockResolvedValue(undefined),
      enqueuePcmPlayback: jest.fn().mockResolvedValue(undefined),
      finishPcmPlayback: jest.fn().mockResolvedValue(undefined),
      stopPcmPlayback: jest.fn().mockImplementationOnce(() => new Promise<void>(resolve => { releaseStop = resolve; })).mockResolvedValue(undefined),
    };
    const oldSession = createCloudStreamingTtsSession({ voiceKey: 'warm_female' }, dependencies);
    const oldStart = oldSession.start();
    await flushMicrotasks();
    oldSocket.open();
    oldSocket.receive({ type: 'ready' });
    await flushMicrotasks();
    const oldCancel = oldSession.cancel();
    void oldCancel;
    const newSession = createCloudStreamingTtsSession({ voiceKey: 'warm_female' }, { ...dependencies });
    const newStart = newSession.start();
    await flushMicrotasks();
    newSocket.open();
    newSocket.receive({ type: 'ready' });
    newSocket.receive({ type: 'ready' });
    await flushMicrotasks(12);
    expect(dependencies.startPcmPlayback).toHaveBeenCalledTimes(1);
    releaseStart();
    await flushMicrotasks(12);
    expect(dependencies.stopPcmPlayback).toHaveBeenCalledTimes(1);
    expect(dependencies.startPcmPlayback).toHaveBeenCalledTimes(1);
    releaseStop();
    await oldCancel;
    await expect(oldStart).resolves.toBe(false);
    await expect(newStart).resolves.toBe(true);
    oldSocket.receive({ type: 'audio', audio: 'stale' });
    oldSocket.receive({ type: 'done' });
    oldSocket.onerror?.();
    await oldSession.cancel();
    await flushMicrotasks(12);
    expect(dependencies.startPcmPlayback).toHaveBeenCalledTimes(2);
    expect(dependencies.stopPcmPlayback).toHaveBeenCalledTimes(1);
    expect(dependencies.enqueuePcmPlayback).not.toHaveBeenCalled();
    expect(dependencies.finishPcmPlayback).not.toHaveBeenCalled();
    await newSession.cancel();
  });

  it('does not enqueue or finish old audio after cancellation and a new session starts', async () => {
    const oldSocket = new FakeSocket();
    const newSocket = new FakeSocket();
    let releaseEnqueue!: () => void;
    const dependencies: StreamingTtsDependencies = {
      requireAIConsent: jest.fn().mockResolvedValue(undefined),
      getAuthToken: jest.fn().mockResolvedValue('jwt-token'),
      openSocket: jest.fn().mockReturnValueOnce(oldSocket).mockReturnValueOnce(newSocket),
      startPcmPlayback: jest.fn().mockResolvedValue(undefined),
      enqueuePcmPlayback: jest.fn().mockImplementationOnce(() => new Promise<void>(resolve => { releaseEnqueue = resolve; })),
      finishPcmPlayback: jest.fn().mockResolvedValue(undefined),
      stopPcmPlayback: jest.fn().mockResolvedValue(undefined),
    };
    const oldSession = createCloudStreamingTtsSession({ voiceKey: 'warm_female' }, dependencies);
    const started = oldSession.start();
    await flushMicrotasks();
    oldSocket.open();
    oldSocket.receive({ type: 'ready' });
    await started;
    oldSocket.receive({ type: 'audio', audio: 'first' });
    await flushMicrotasks();
    oldSocket.receive({ type: 'audio', audio: 'stale' });
    oldSocket.receive({ type: 'done' });
    await oldSession.cancel();

    const newSession = createCloudStreamingTtsSession({ voiceKey: 'warm_female' }, dependencies);
    const newStarted = newSession.start();
    await flushMicrotasks();
    newSocket.open();
    newSocket.receive({ type: 'ready' });
    await newStarted;
    releaseEnqueue();
    await flushMicrotasks(12);
    expect(dependencies.enqueuePcmPlayback).toHaveBeenCalledTimes(1);
    expect(dependencies.finishPcmPlayback).not.toHaveBeenCalled();
    expect(dependencies.stopPcmPlayback).toHaveBeenCalledTimes(1);
    await newSession.cancel();
  });

  it('settles native startup before cancellation releases the player to a new session', async () => {
    const socket = new FakeSocket();
    let releaseStart!: () => void;
    const dependencies: StreamingTtsDependencies = {
      requireAIConsent: jest.fn().mockResolvedValue(undefined),
      getAuthToken: jest.fn().mockResolvedValue('jwt-token'),
      openSocket: jest.fn(() => socket as any),
      startPcmPlayback: jest.fn(() => new Promise<void>(resolve => { releaseStart = resolve; })),
      enqueuePcmPlayback: jest.fn().mockResolvedValue(undefined),
      finishPcmPlayback: jest.fn().mockResolvedValue(undefined),
      stopPcmPlayback: jest.fn().mockResolvedValue(undefined),
    };
    const session = createCloudStreamingTtsSession({ voiceKey: 'warm_female' }, dependencies);
    const start = session.start();
    await flushMicrotasks();
    socket.open();
    socket.receive({ type: 'ready' });
    socket.receive({ type: 'ready' });
    await flushMicrotasks();
    let cancelled = false;
    const cancel = session.cancel().then(() => { cancelled = true; });
    await flushMicrotasks();
    expect(cancelled).toBe(false);
    expect(dependencies.startPcmPlayback).toHaveBeenCalledTimes(1);
    releaseStart();
    await cancel;
    await expect(start).resolves.toBe(false);
    expect(dependencies.stopPcmPlayback).toHaveBeenCalledTimes(1);
  });

  it('uses the authenticated backend websocket', () => {
    expect(streamingTtsWebSocketUrl('https://health.executor.life/api'))
      .toBe('wss://health.executor.life/api/tts/stream');
  });

  it('does not let a cancelled waiting session stop its predecessor player', async () => {
    const oldSocket = new FakeSocket();
    const waitingSocket = new FakeSocket();
    const dependencies: StreamingTtsDependencies = {
      requireAIConsent: jest.fn().mockResolvedValue(undefined),
      getAuthToken: jest.fn().mockResolvedValue('jwt-token'),
      openSocket: jest.fn().mockReturnValueOnce(oldSocket).mockReturnValueOnce(waitingSocket),
      startPcmPlayback: jest.fn().mockResolvedValue(undefined),
      enqueuePcmPlayback: jest.fn().mockResolvedValue(undefined),
      finishPcmPlayback: jest.fn().mockResolvedValue(undefined),
      stopPcmPlayback: jest.fn().mockResolvedValue(undefined),
    };
    const oldSession = createCloudStreamingTtsSession({ voiceKey: 'warm_female' }, dependencies);
    const oldStart = oldSession.start();
    await flushMicrotasks();
    oldSocket.open();
    oldSocket.receive({ type: 'ready' });
    await oldStart;
    const waitingSession = createCloudStreamingTtsSession({ voiceKey: 'warm_female' }, dependencies);
    const waitingStart = waitingSession.start();
    await flushMicrotasks();
    waitingSocket.open();
    waitingSocket.receive({ type: 'ready' });
    const waitingCancel = waitingSession.cancel();
    await flushMicrotasks(12);
    expect(dependencies.stopPcmPlayback).not.toHaveBeenCalled();
    expect(dependencies.startPcmPlayback).toHaveBeenCalledTimes(1);
    await oldSession.cancel();
    await waitingCancel;
    await expect(waitingStart).resolves.toBe(false);
    expect(dependencies.stopPcmPlayback).toHaveBeenCalledTimes(1);
    expect(dependencies.startPcmPlayback).toHaveBeenCalledTimes(1);
  });

  it('fails closed for a successor when native cleanup fails', async () => {
    const oldSocket = new FakeSocket();
    const newSocket = new FakeSocket();
    const dependencies: StreamingTtsDependencies = {
      requireAIConsent: jest.fn().mockResolvedValue(undefined),
      getAuthToken: jest.fn().mockResolvedValue('jwt-token'),
      openSocket: jest.fn().mockReturnValueOnce(oldSocket).mockReturnValueOnce(newSocket),
      startPcmPlayback: jest.fn().mockResolvedValue(undefined),
      enqueuePcmPlayback: jest.fn().mockResolvedValue(undefined),
      finishPcmPlayback: jest.fn().mockResolvedValue(undefined),
      stopPcmPlayback: jest.fn().mockRejectedValue(new Error('native stop failed')),
    };
    const oldSession = createCloudStreamingTtsSession({ voiceKey: 'warm_female' }, dependencies);
    const oldStart = oldSession.start();
    await flushMicrotasks();
    oldSocket.open();
    oldSocket.receive({ type: 'ready' });
    await oldStart;
    await expect(oldSession.cancel()).rejects.toThrow('native stop failed');
    const newSession = createCloudStreamingTtsSession({ voiceKey: 'warm_female' }, dependencies);
    const newStart = newSession.start();
    await flushMicrotasks();
    newSocket.open();
    newSocket.receive({ type: 'ready' });
    await expect(newStart).rejects.toThrow('native stop failed');
    expect(dependencies.startPcmPlayback).toHaveBeenCalledTimes(1);
    expect(dependencies.stopPcmPlayback).toHaveBeenCalledTimes(1);
  });

  it('streams server PCM into the native player and waits for playback drain', async () => {
    const socket = new FakeSocket();
    let resolveDrain!: () => void;
    const dependencies: StreamingTtsDependencies = {
      requireAIConsent: jest.fn().mockResolvedValue(undefined),
      getAuthToken: jest.fn().mockResolvedValue('jwt-token'),
      openSocket: jest.fn(() => socket as any),
      startPcmPlayback: jest.fn().mockResolvedValue(undefined),
      enqueuePcmPlayback: jest.fn().mockResolvedValue(undefined),
      finishPcmPlayback: jest.fn(() => new Promise<void>(resolve => { resolveDrain = resolve; })),
      stopPcmPlayback: jest.fn().mockResolvedValue(undefined),
    };
    const session = createCloudStreamingTtsSession(
      { voiceKey: 'warm_female', speed: 1.1 },
      dependencies,
    );

    const start = session.start();
    await flushMicrotasks();
    socket.open();
    socket.receive({ type: 'ready', encoding: 'pcm_s16le', sample_rate: 24000, channels: 1 });
    await expect(start).resolves.toBe(true);

    await session.append('今天先喝水，');
    await session.append('再去散步。');
    expect(socket.sent.map(value => JSON.parse(value))).toEqual([
      { type: 'append', text: '今天先喝水，' },
      { type: 'append', text: '再去散步。' },
    ]);

    socket.receive({ type: 'audio', audio: 'AQACA=== ' });
    await flushMicrotasks();
    expect(dependencies.enqueuePcmPlayback).toHaveBeenCalledWith('AQACA=== ');

    const finish = session.finish();
    void finish.catch(() => undefined);
    await flushMicrotasks();
    expect(JSON.parse(socket.sent.at(-1)!)).toEqual({ type: 'finish' });
    socket.receive({ type: 'done' });
    socket.receive({ type: 'done' });
    socket.close();
    await flushMicrotasks();
    expect(dependencies.finishPcmPlayback).toHaveBeenCalledTimes(1);

    let settled = false;
    void finish.then(() => { settled = true; });
    await Promise.resolve();
    expect(settled).toBe(false);
    resolveDrain();
    await expect(finish).resolves.toBeUndefined();
    await session.cancel();
    expect(dependencies.stopPcmPlayback).not.toHaveBeenCalled();
  });

  it('cancels synthesis and playback without finishing queued audio', async () => {
    const socket = new FakeSocket();
    const dependencies: StreamingTtsDependencies = {
      requireAIConsent: jest.fn().mockResolvedValue(undefined),
      getAuthToken: jest.fn().mockResolvedValue('jwt-token'),
      openSocket: jest.fn(() => socket as any),
      startPcmPlayback: jest.fn().mockResolvedValue(undefined),
      enqueuePcmPlayback: jest.fn().mockResolvedValue(undefined),
      finishPcmPlayback: jest.fn().mockResolvedValue(undefined),
      stopPcmPlayback: jest.fn().mockResolvedValue(undefined),
    };
    const session = createCloudStreamingTtsSession({ voiceKey: 'warm_female' }, dependencies);
    const start = session.start();
    await flushMicrotasks();
    socket.open();
    socket.receive({ type: 'ready', sample_rate: 24000 });
    await start;

    await Promise.all([session.cancel(), session.cancel()]);

    expect(socket.sent.map(value => JSON.parse(value))).toContainEqual({ type: 'cancel' });
    expect(dependencies.stopPcmPlayback).toHaveBeenCalledTimes(1);
    expect(dependencies.finishPcmPlayback).not.toHaveBeenCalled();
  });
});
