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
  it('uses the authenticated backend websocket', () => {
    expect(streamingTtsWebSocketUrl('https://health.executor.life/api'))
      .toBe('wss://health.executor.life/api/tts/stream');
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
    await flushMicrotasks();
    expect(JSON.parse(socket.sent.at(-1)!)).toEqual({ type: 'finish' });
    socket.receive({ type: 'done' });
    await flushMicrotasks();
    expect(dependencies.finishPcmPlayback).toHaveBeenCalledTimes(1);

    let settled = false;
    void finish.then(() => { settled = true; });
    await Promise.resolve();
    expect(settled).toBe(false);
    resolveDrain();
    await expect(finish).resolves.toBeUndefined();
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
