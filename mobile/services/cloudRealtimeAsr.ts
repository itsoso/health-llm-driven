import * as SecureStore from 'expo-secure-store';
import type { EventSubscription } from 'expo-modules-core';

import { BASE_URL, TOKEN_KEY } from './api';
import type { TranscribeAudioResult } from './transcribe';
import {
  cancelPcmCapture,
  startPcmCapture,
  stopPcmCapture,
} from '../modules/reva-pcm-stream';

const START_TIMEOUT_MS = 8_000;
const FINAL_TIMEOUT_MS = 18_000;

type RealtimeAsrMessage = {
  type?: string;
  text?: string;
  provider?: string;
  model?: string;
  duration_ms?: number;
  confidence?: string;
  message?: string;
};

type SocketLike = {
  readyState: number;
  onopen: (() => void) | null;
  onmessage: ((event: { data: string }) => void) | null;
  onerror: (() => void) | null;
  onclose: (() => void) | null;
  send: (payload: string) => void;
  close: () => void;
};

export interface RealtimeAsrDependencies {
  getAuthToken: () => Promise<string | null>;
  openSocket: (url: string, token: string) => SocketLike;
  startPcmCapture: (
    onChunk: (audioBase64: string) => void,
    onLevel?: (level: number) => void,
  ) => Promise<EventSubscription | void>;
  stopPcmCapture: (subscription?: EventSubscription | null) => Promise<void>;
  cancelPcmCapture: (subscription?: EventSubscription | null) => Promise<void>;
}

interface RealtimeAsrOptions {
  onTranscript: (text: string, result?: TranscribeAudioResult) => void;
  onLevel?: (level: number) => void;
  onError?: (error: Error) => void;
}

export interface RealtimeAsrSession {
  start: () => Promise<boolean>;
  stop: () => Promise<TranscribeAudioResult>;
  cancel: () => Promise<void>;
}

// The native microphone is process-wide. Keep a newer session behind its
// predecessor's cleanup, including a native start that has not resolved yet.
const captureOwners = new WeakMap<RealtimeAsrDependencies['startPcmCapture'], Promise<void>>();

function confidence(value: unknown): TranscribeAudioResult['confidence'] {
  return value === 'high' || value === 'medium' || value === 'low' ? value : undefined;
}

function asResult(message: RealtimeAsrMessage, fallbackDurationMs: number): TranscribeAudioResult {
  const text = String(message.text || '').trim();
  return {
    text,
    provider: message.provider || 'dashscope_qwen_asr_realtime',
    ...(message.model ? { model: message.model } : {}),
    durationMs: typeof message.duration_ms === 'number'
      ? Math.max(0, Math.round(message.duration_ms))
      : fallbackDurationMs,
    ...(confidence(message.confidence) ? { confidence: confidence(message.confidence) } : {}),
    empty: text.length === 0,
  };
}

export function realtimeAsrWebSocketUrl(baseUrl = BASE_URL): string {
  return `${baseUrl.replace(/^http:/, 'ws:').replace(/^https:/, 'wss:').replace(/\/$/, '')}`
    + '/chat/transcribe/realtime';
}

const defaultDependencies: RealtimeAsrDependencies = {
  getAuthToken: () => SecureStore.getItemAsync(TOKEN_KEY),
  openSocket: (url, token) => new (WebSocket as any)(
    url,
    undefined,
    { headers: { Authorization: `Bearer ${token}` } },
  ) as unknown as SocketLike,
  startPcmCapture,
  stopPcmCapture,
  cancelPcmCapture,
};

export function createCloudRealtimeAsrSession(
  options: RealtimeAsrOptions,
  dependencies: RealtimeAsrDependencies = defaultDependencies,
): RealtimeAsrSession {
  let socket: SocketLike | null = null;
  let captureSubscription: EventSubscription | null = null;
  let startedAt = 0;
  let finalResult: TranscribeAudioResult | null = null;
  let cancelled = false;
  let startSettled = false;
  let finishSettled = false;
  let resolveStart: ((started: boolean) => void) | null = null;
  let rejectStart: ((error: Error) => void) | null = null;
  let resolveFinish: ((result: TranscribeAudioResult) => void) | null = null;
  let rejectFinish: ((error: Error) => void) | null = null;
  let startTimer: ReturnType<typeof setTimeout> | null = null;
  let finishTimer: ReturnType<typeof setTimeout> | null = null;
  let captureStarting = false;
  let captureStarted = false;
  let captureStartPromise: Promise<void> | null = null;
  let captureCleanupPromise: Promise<void> | null = null;
  let releaseCaptureOwner: (() => void) | null = null;
  let terminalError: Error | null = null;
  let startPromise: Promise<boolean> | null = null;
  let stopPromise: Promise<TranscribeAudioResult> | null = null;
  let cancelPromise: Promise<void> | null = null;

  const clearTimers = () => {
    if (startTimer) clearTimeout(startTimer);
    if (finishTimer) clearTimeout(finishTimer);
    startTimer = null;
    finishTimer = null;
  };

  const closeSocket = () => {
    const closingSocket = socket;
    socket = null;
    if (closingSocket && closingSocket.readyState < 2) closingSocket.close();
  };

  const cleanupCapture = (mode: 'stop' | 'cancel'): Promise<void> => {
    if (captureCleanupPromise) return captureCleanupPromise;
    if (!captureStarted) return Promise.resolve();
    captureCleanupPromise = (async () => {
      // A startup rejection is reported by handleMessage; still release any
      // partially acquired native resources before releasing ownership.
      if (captureStartPromise) await captureStartPromise.catch(() => undefined);
      // A failed cleanup must not release the singleton microphone to a new
      // owner. The caller sees the failure; a retry cannot silently record.
      await dependencies[mode === 'stop' ? 'stopPcmCapture' : 'cancelPcmCapture'](captureSubscription);
      captureSubscription = null;
      captureStarted = false;
      releaseCaptureOwner?.();
      releaseCaptureOwner = null;
    })();
    return captureCleanupPromise;
  };

  const fail = (message: string) => {
    if (cancelled || finishSettled) return;
    const wasRecording = startSettled && !stopPromise;
    const error = new Error(message || '云端实时语音识别失败');
    terminalError = error;
    cancelled = true;
    clearTimers();
    const cleanup = cleanupCapture('cancel');
    closeSocket();
    if (!startSettled && rejectStart) {
      startSettled = true;
      rejectStart(error);
    }
    if (!finishSettled && rejectFinish) {
      finishSettled = true;
      rejectFinish(error);
    }
    void cleanup.then(() => {
      if (wasRecording) options.onError?.(error);
    }, () => {
      terminalError = new Error('麦克风采集未能安全停止，请关闭语音后重试');
      if (wasRecording) options.onError?.(terminalError);
    });
  };

  const handleMessage = async (raw: string) => {
    if (cancelled || finishSettled) return;
    let message: RealtimeAsrMessage;
    try {
      message = JSON.parse(raw) as RealtimeAsrMessage;
    } catch {
      fail('云端实时语音返回了无效数据');
      return;
    }
    if (message.type === 'ready') {
      if (startSettled || captureStarting) return;
      captureStarting = true;
      try {
        while (captureOwners.has(dependencies.startPcmCapture)) {
          await captureOwners.get(dependencies.startPcmCapture);
          if (cancelled) return;
        }
        const ownership = new Promise<void>(resolve => { releaseCaptureOwner = resolve; });
        captureOwners.set(dependencies.startPcmCapture, ownership);
        void ownership.then(() => {
          if (captureOwners.get(dependencies.startPcmCapture) === ownership) {
            captureOwners.delete(dependencies.startPcmCapture);
          }
        });
        captureStarted = true;
        captureStartPromise = dependencies.startPcmCapture(
          (audioBase64) => {
            if (!cancelled && socket?.readyState === 1) {
              socket.send(JSON.stringify({ type: 'audio', audio: audioBase64 }));
            }
          },
          level => { if (!cancelled) options.onLevel?.(level); },
        ).then(subscription => { captureSubscription = subscription || null; });
        await captureStartPromise;
        captureStartPromise = null;
        if (cancelled) return;
        startSettled = true;
        if (startTimer) clearTimeout(startTimer);
        resolveStart?.(true);
      } catch (error: any) {
        fail(error?.message || '无法开始麦克风采集');
      } finally {
        captureStarting = false;
      }
      return;
    }
    if (message.type === 'partial' && message.text) {
      options.onTranscript(
        message.text,
        asResult(message, Math.max(0, Date.now() - startedAt)),
      );
      return;
    }
    if (message.type === 'final') {
      finalResult = asResult(message, Math.max(0, Date.now() - startedAt));
      if (!finalResult.empty) options.onTranscript(finalResult.text, finalResult);
      return;
    }
    if (message.type === 'done') {
      if (finishSettled) return;
      if (!resolveFinish) {
        fail('云端实时语音连接提前结束');
        return;
      }
      finishSettled = true;
      if (finishTimer) clearTimeout(finishTimer);
      resolveFinish?.(finalResult || asResult({}, Math.max(0, Date.now() - startedAt)));
      closeSocket();
      return;
    }
    if (message.type === 'error') fail(message.message || '云端实时语音识别失败');
  };

  const cancel = (): Promise<void> => {
    if (cancelPromise) return cancelPromise;
    cancelPromise = (async () => {
      cancelled = true;
      clearTimers();
      if (!startSettled && resolveStart) {
        startSettled = true;
        resolveStart(false);
      }
      if (!finishSettled && resolveFinish) {
        finishSettled = true;
        resolveFinish(asResult({}, Math.max(0, Date.now() - startedAt)));
      }
      try {
        if (socket?.readyState === 1) socket.send(JSON.stringify({ type: 'cancel' }));
      } finally {
        closeSocket();
        await cleanupCapture('cancel');
      }
    })();
    return cancelPromise;
  };

  return {
    start(): Promise<boolean> {
      if (startPromise) return startPromise;
      if (socket) return Promise.resolve(false);
      startPromise = (async () => {
        const token = await dependencies.getAuthToken();
        if (!token) throw new Error('登录已过期，请重新登录后使用语音输入');
        if (cancelled) return false;
        startedAt = Date.now();
        finalResult = null;
        socket = dependencies.openSocket(realtimeAsrWebSocketUrl(), token);
        socket.onmessage = event => { void handleMessage(event.data); };
        socket.onerror = () => fail('无法连接云端实时语音服务');
        socket.onclose = () => {
          if (!cancelled && !finishSettled) {
            fail('云端实时语音连接已断开');
          }
        };
        return new Promise<boolean>((resolve, reject) => {
          resolveStart = resolve;
          rejectStart = reject;
          startTimer = setTimeout(() => fail('连接云端实时语音服务超时'), START_TIMEOUT_MS);
        });
      })();
      return startPromise;
    },

    stop(): Promise<TranscribeAudioResult> {
      if (stopPromise) return stopPromise;
      stopPromise = (async () => {
        if (terminalError) throw terminalError;
        if (!socket || !startSettled) {
          await cancel();
          return asResult({}, 0);
        }
        try {
          await cleanupCapture('stop');
        } catch {
          fail('麦克风采集未能安全停止，请关闭语音后重试');
          throw terminalError || new Error('麦克风采集未能安全停止，请关闭语音后重试');
        }
        if (terminalError) throw terminalError;
        if (cancelled) return asResult({}, 0);
        return new Promise<TranscribeAudioResult>((resolve, reject) => {
          resolveFinish = resolve;
          rejectFinish = reject;
          finishTimer = setTimeout(() => fail('等待最终语音识别结果超时'), FINAL_TIMEOUT_MS);
          try {
            socket?.send(JSON.stringify({ type: 'finish' }));
          } catch {
            fail('无法提交最终语音识别结果');
          }
        });
      })();
      return stopPromise;
    },

    cancel,
  };
}
