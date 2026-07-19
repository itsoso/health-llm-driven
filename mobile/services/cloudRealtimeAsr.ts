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
}

export interface RealtimeAsrSession {
  start: () => Promise<boolean>;
  stop: () => Promise<TranscribeAudioResult>;
  cancel: () => Promise<void>;
}

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

  const clearTimers = () => {
    if (startTimer) clearTimeout(startTimer);
    if (finishTimer) clearTimeout(finishTimer);
    startTimer = null;
    finishTimer = null;
  };

  const closeSocket = () => {
    if (socket && socket.readyState < 2) socket.close();
    socket = null;
  };

  const fail = (message: string) => {
    cancelled = true;
    clearTimers();
    const subscription = captureSubscription;
    captureSubscription = null;
    if (subscription) {
      void dependencies.cancelPcmCapture(subscription).catch(() => undefined);
    }
    closeSocket();
    const error = new Error(message || '云端实时语音识别失败');
    if (!startSettled && rejectStart) {
      startSettled = true;
      rejectStart(error);
    }
    if (!finishSettled && rejectFinish) {
      finishSettled = true;
      rejectFinish(error);
    }
  };

  const handleMessage = async (raw: string) => {
    let message: RealtimeAsrMessage;
    try {
      message = JSON.parse(raw) as RealtimeAsrMessage;
    } catch {
      fail('云端实时语音返回了无效数据');
      return;
    }
    if (message.type === 'ready') {
      if (startSettled) return;
      try {
        const subscription = (await dependencies.startPcmCapture(
          (audioBase64) => {
            if (!cancelled && socket?.readyState === 1) {
              socket.send(JSON.stringify({ type: 'audio', audio: audioBase64 }));
            }
          },
          options.onLevel,
        )) || null;
        if (cancelled) {
          await dependencies.cancelPcmCapture(subscription);
          return;
        }
        captureSubscription = subscription;
        startSettled = true;
        if (startTimer) clearTimeout(startTimer);
        resolveStart?.(true);
      } catch (error: any) {
        fail(error?.message || '无法开始麦克风采集');
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
      finishSettled = true;
      if (finishTimer) clearTimeout(finishTimer);
      resolveFinish?.(finalResult || asResult({}, Math.max(0, Date.now() - startedAt)));
      closeSocket();
      return;
    }
    if (message.type === 'error') fail(message.message || '云端实时语音识别失败');
  };

  return {
    async start(): Promise<boolean> {
      if (socket) return false;
      const token = await dependencies.getAuthToken();
      if (!token) throw new Error('登录已过期，请重新登录后使用语音输入');
      cancelled = false;
      startedAt = Date.now();
      finalResult = null;
      socket = dependencies.openSocket(realtimeAsrWebSocketUrl(), token);
      socket.onmessage = event => { void handleMessage(event.data); };
      socket.onerror = () => fail('无法连接云端实时语音服务');
      socket.onclose = () => {
        if (!cancelled && (!startSettled || (resolveFinish && !finishSettled))) {
          fail('云端实时语音连接已断开');
        }
      };
      return new Promise<boolean>((resolve, reject) => {
        resolveStart = resolve;
        rejectStart = reject;
        startTimer = setTimeout(() => fail('连接云端实时语音服务超时'), START_TIMEOUT_MS);
      });
    },

    async stop(): Promise<TranscribeAudioResult> {
      if (!socket || !startSettled) return asResult({}, 0);
      await dependencies.stopPcmCapture(captureSubscription);
      captureSubscription = null;
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
    },

    async cancel(): Promise<void> {
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
      await dependencies.cancelPcmCapture(captureSubscription);
      captureSubscription = null;
      if (socket?.readyState === 1) socket.send(JSON.stringify({ type: 'cancel' }));
      closeSocket();
    },
  };
}
