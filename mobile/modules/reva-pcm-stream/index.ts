import {
  EventEmitter,
  Platform,
  requireNativeModule,
  type EventSubscription,
} from 'expo-modules-core';

const AUDIO_EVENT = 'onPcmChunk';

type PcmChunkEvent = {
  audioBase64?: string;
  level?: number;
};

type NativePcmStream = {
  start: () => Promise<void>;
  stop: () => Promise<void>;
  cancel: () => Promise<void>;
};

type NativePcmEmitter = {
  addListener: (
    eventName: typeof AUDIO_EVENT,
    listener: (event: PcmChunkEvent) => void,
  ) => EventSubscription;
};

let nativeModule: NativePcmStream | null | undefined;
let eventEmitter: NativePcmEmitter | null | undefined;

function getNativeModule(): NativePcmStream | null {
  if (nativeModule !== undefined) return nativeModule;
  if (Platform.OS !== 'ios') {
    nativeModule = null;
    return null;
  }
  try {
    nativeModule = requireNativeModule('RevaPcmStream') as NativePcmStream;
  } catch {
    nativeModule = null;
  }
  return nativeModule;
}

function getEmitter(): NativePcmEmitter | null {
  if (eventEmitter !== undefined) return eventEmitter;
  const module = getNativeModule();
  eventEmitter = module
    ? new EventEmitter(module as any) as NativePcmEmitter
    : null;
  return eventEmitter;
}

export async function startPcmCapture(
  onChunk: (audioBase64: string) => void,
  onLevel?: (level: number) => void,
): Promise<EventSubscription> {
  const module = getNativeModule();
  const emitter = getEmitter();
  if (!module || !emitter) {
    throw new Error('当前版本不支持云端实时语音，请更新 App 后重试');
  }
  const subscription = emitter.addListener(AUDIO_EVENT, (event: PcmChunkEvent) => {
    if (event.audioBase64) onChunk(event.audioBase64);
    if (typeof event.level === 'number') onLevel?.(event.level);
  });
  try {
    await module.start();
    return subscription;
  } catch (error) {
    subscription.remove();
    throw error;
  }
}

export async function stopPcmCapture(subscription?: EventSubscription | null): Promise<void> {
  try {
    await getNativeModule()?.stop();
  } finally {
    subscription?.remove();
  }
}

export async function cancelPcmCapture(subscription?: EventSubscription | null): Promise<void> {
  try {
    await getNativeModule()?.cancel();
  } finally {
    subscription?.remove();
  }
}
