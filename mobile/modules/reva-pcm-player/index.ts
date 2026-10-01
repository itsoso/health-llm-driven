import {
  EventEmitter,
  Platform,
  requireNativeModule,
  type EventSubscription,
} from 'expo-modules-core';

const DRAINED_EVENT = 'onPlaybackDrained';
const ERROR_EVENT = 'onPlaybackError';
const PLAYBACK_TIMEOUT_MS = 90_000;

type NativePcmPlayer = {
  start: (sampleRate: number) => Promise<void>;
  enqueue: (audioBase64: string) => Promise<void>;
  finish: () => Promise<void>;
  stop: () => Promise<void>;
};

type NativePcmEmitter = {
  addListener: (
    eventName: typeof DRAINED_EVENT | typeof ERROR_EVENT,
    listener: (event: { message?: string }) => void,
  ) => EventSubscription;
};

let nativeModule: NativePcmPlayer | null | undefined;
let eventEmitter: NativePcmEmitter | null | undefined;
let rejectPendingFinish: ((error: Error) => void) | null = null;

function getNativeModule(): NativePcmPlayer | null {
  if (nativeModule !== undefined) return nativeModule;
  if (Platform.OS !== 'ios') {
    nativeModule = null;
    return null;
  }
  try {
    nativeModule = requireNativeModule('RevaPcmPlayer') as NativePcmPlayer;
  } catch {
    nativeModule = null;
  }
  return nativeModule;
}

function getEmitter(): NativePcmEmitter | null {
  if (eventEmitter !== undefined) return eventEmitter;
  const module = getNativeModule();
  eventEmitter = module ? new EventEmitter(module as any) as NativePcmEmitter : null;
  return eventEmitter;
}

function requirePlayer(): NativePcmPlayer {
  const module = getNativeModule();
  if (!module) throw new Error('当前版本不支持流式语音播放，请更新 App 后重试');
  return module;
}

export async function startPcmPlayback(sampleRate = 24000): Promise<void> {
  await requirePlayer().start(sampleRate);
}

export async function enqueuePcmPlayback(audioBase64: string): Promise<void> {
  await requirePlayer().enqueue(audioBase64);
}

export async function finishPcmPlayback(): Promise<void> {
  const module = requirePlayer();
  const emitter = getEmitter();
  if (!emitter) throw new Error('流式语音播放器事件不可用');
  if (rejectPendingFinish) throw new Error('流式语音播放已在结束中');

  await new Promise<void>((resolve, reject) => {
    let settled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let drainedSubscription: EventSubscription | null = null;
    let errorSubscription: EventSubscription | null = null;
    const settle = (error?: Error) => {
      if (settled) return;
      settled = true;
      if (timer) clearTimeout(timer);
      drainedSubscription?.remove();
      errorSubscription?.remove();
      rejectPendingFinish = null;
      if (error) reject(error);
      else resolve();
    };
    rejectPendingFinish = error => settle(error);
    drainedSubscription = emitter.addListener(DRAINED_EVENT, () => settle());
    errorSubscription = emitter.addListener(ERROR_EVENT, event => {
      settle(new Error(event.message || '流式语音播放失败'));
    });
    timer = setTimeout(() => settle(new Error('等待流式语音播放结束超时')), PLAYBACK_TIMEOUT_MS);
    void module.finish().catch(error => settle(error instanceof Error ? error : new Error(String(error))));
  });
}

export async function stopPcmPlayback(): Promise<void> {
  rejectPendingFinish?.(new Error('流式语音播放已取消'));
  rejectPendingFinish = null;
  await getNativeModule()?.stop();
}
