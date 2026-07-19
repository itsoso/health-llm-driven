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

describe('cloudRealtimeAsr', () => {
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
    await Promise.resolve();
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
    await Promise.resolve();
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
    await Promise.resolve();

    socket.receive({ type: 'ready' });
    await Promise.resolve();
    socket.receive({ type: 'ready' });
    await Promise.resolve();

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

    resolveToken('jwt-token');
    await Promise.resolve();
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
    await Promise.resolve();
    socket.receive({ type: 'ready' });
    await startPromise;

    socket.receive({ type: 'error', message: '上游连接中断' });
    await Promise.resolve();
    socket.receive({ type: 'partial', text: '不要回写这段' });
    socket.receive({ type: 'final', text: '也不要回写这段' });
    await Promise.resolve();

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
    await Promise.resolve();
    socket.receive({ type: 'ready' });
    await startPromise;

    const firstStop = session.stop();
    const secondStop = session.stop();
    await Promise.resolve();
    await Promise.resolve();

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
    await Promise.resolve();
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
    await Promise.resolve();
    socket.open();
    socket.receive({ type: 'ready' });
    await startPromise;

    socket.receive({ type: 'error', message: '上游连接中断' });
    await Promise.resolve();

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
    await Promise.resolve();

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
    await Promise.resolve();

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
    await Promise.resolve();
    socket.open();
    socket.receive({ type: 'ready' });
    await Promise.resolve();

    socket.receive({ type: 'error', message: '上游连接中断' });
    resolveCapture?.(captureSubscription);

    await expect(startPromise).rejects.toThrow('上游连接中断');
    await Promise.resolve();
    expect(dependencies.cancelPcmCapture).toHaveBeenCalledWith(captureSubscription);
  });
});
