import * as SecureStore from 'expo-secure-store';

import { BASE_URL, TOKEN_KEY } from './api';
import { requireAIConsent } from './aiConsent';
import type { CloudVoiceKey } from './cloudTts';
import {
  enqueuePcmPlayback,
  finishPcmPlayback,
  startPcmPlayback,
  stopPcmPlayback,
} from '../modules/reva-pcm-player';

const START_TIMEOUT_MS = 8_000;
const FINISH_TIMEOUT_MS = 75_000;

type SocketLike = {
  readyState: number;
  onopen: (() => void) | null;
  onmessage: ((event: { data: string }) => void) | null;
  onerror: (() => void) | null;
  onclose: (() => void) | null;
  send: (payload: string) => void;
  close: () => void;
};

type StreamingTtsMessage = {
  type?: string;
  audio?: string;
  sample_rate?: number;
  encoding?: string;
  channels?: number;
  message?: string;
};

export interface StreamingTtsDependencies {
  requireAIConsent: () => Promise<void>;
  getAuthToken: () => Promise<string | null>;
  openSocket: (url: string, token: string) => SocketLike;
  startPcmPlayback: (sampleRate?: number) => Promise<void>;
  enqueuePcmPlayback: (audioBase64: string) => Promise<void>;
  finishPcmPlayback: () => Promise<void>;
  stopPcmPlayback: () => Promise<void>;
}

export interface StreamingTtsSession {
  start: () => Promise<boolean>;
  append: (text: string) => Promise<void>;
  finish: () => Promise<void>;
  cancel: () => Promise<void>;
}

interface StreamingTtsOptions {
  voiceKey: CloudVoiceKey;
  speed?: number;
}

export function streamingTtsWebSocketUrl(baseUrl = BASE_URL): string {
  return `${baseUrl.replace(/^http:/, 'ws:').replace(/^https:/, 'wss:').replace(/\/$/, '')}`
    + '/tts/stream';
}

const defaultDependencies: StreamingTtsDependencies = {
  requireAIConsent,
  getAuthToken: () => SecureStore.getItemAsync(TOKEN_KEY),
  openSocket: (url, token) => new (WebSocket as any)(
    url,
    undefined,
    { headers: { Authorization: `Bearer ${token}` } },
  ) as unknown as SocketLike,
  startPcmPlayback,
  enqueuePcmPlayback,
  finishPcmPlayback,
  stopPcmPlayback,
};

export function createCloudStreamingTtsSession(
  options: StreamingTtsOptions,
  dependencies: StreamingTtsDependencies = defaultDependencies,
): StreamingTtsSession {
  let socket: SocketLike | null = null;
  let cancelled = false;
  let started = false;
  let completed = false;
  let startPromise: Promise<boolean> | null = null;
  let finishPromise: Promise<void> | null = null;
  let cancelPromise: Promise<void> | null = null;
  let resolveStart: ((value: boolean) => void) | null = null;
  let rejectStart: ((error: Error) => void) | null = null;
  let resolveFinish: (() => void) | null = null;
  let rejectFinish: ((error: Error) => void) | null = null;
  let startTimer: ReturnType<typeof setTimeout> | null = null;
  let finishTimer: ReturnType<typeof setTimeout> | null = null;
  let playerChain = Promise.resolve();

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
    if (cancelled || completed) return;
    cancelled = true;
    clearTimers();
    closeSocket();
    void dependencies.stopPcmPlayback().catch(() => undefined);
    const error = new Error(message || '流式语音服务暂时不可用');
    if (!started && rejectStart) rejectStart(error);
    if (finishPromise && rejectFinish) rejectFinish(error);
  };

  const handleMessage = async (raw: string) => {
    if (cancelled || completed) return;
    let message: StreamingTtsMessage;
    try {
      message = JSON.parse(raw) as StreamingTtsMessage;
    } catch {
      fail('流式语音返回了无效数据');
      return;
    }
    if (message.type === 'ready') {
      if (started) return;
      if (message.encoding && message.encoding !== 'pcm_s16le') {
        fail('流式语音格式不受支持');
        return;
      }
      try {
        await dependencies.startPcmPlayback(message.sample_rate || 24000);
        if (cancelled) {
          await dependencies.stopPcmPlayback();
          return;
        }
        started = true;
        if (startTimer) clearTimeout(startTimer);
        resolveStart?.(true);
      } catch (error: any) {
        fail(error?.message || '无法启动流式语音播放');
      }
      return;
    }
    if (message.type === 'audio' && message.audio) {
      playerChain = playerChain.then(() => dependencies.enqueuePcmPlayback(message.audio!));
      playerChain.catch(error => fail(error?.message || '流式语音播放失败'));
      return;
    }
    if (message.type === 'done') {
      try {
        await playerChain;
        await dependencies.finishPcmPlayback();
        if (cancelled) return;
        completed = true;
        clearTimers();
        closeSocket();
        resolveFinish?.();
      } catch (error: any) {
        fail(error?.message || '流式语音播放失败');
      }
      return;
    }
    if (message.type === 'error') fail(message.message || '流式语音服务暂时不可用');
  };

  return {
    start(): Promise<boolean> {
      if (startPromise) return startPromise;
      startPromise = (async () => {
        await dependencies.requireAIConsent();
        const token = await dependencies.getAuthToken();
        if (!token) throw new Error('登录已过期，请重新登录后使用语音播放');
        if (cancelled) return false;
        const query = `voice_style=${encodeURIComponent(options.voiceKey)}`
          + `&speed=${encodeURIComponent(String(options.speed ?? 1.0))}`;
        socket = dependencies.openSocket(`${streamingTtsWebSocketUrl()}?${query}`, token);
        socket.onmessage = event => { void handleMessage(event.data); };
        socket.onerror = () => fail('无法连接流式语音服务');
        socket.onclose = () => {
          if (!cancelled && !completed && (!started || finishPromise)) {
            fail('流式语音连接已断开');
          }
        };
        return new Promise<boolean>((resolve, reject) => {
          resolveStart = resolve;
          rejectStart = reject;
          startTimer = setTimeout(() => fail('连接流式语音服务超时'), START_TIMEOUT_MS);
        });
      })();
      return startPromise;
    },

    async append(text: string): Promise<void> {
      const clean = text.trim();
      if (!clean) return;
      const didStart = await this.start();
      if (!didStart || cancelled || !socket || socket.readyState > 1) {
        throw new Error('流式语音会话不可用');
      }
      socket.send(JSON.stringify({ type: 'append', text: clean }));
    },

    finish(): Promise<void> {
      if (finishPromise) return finishPromise;
      finishPromise = (async () => {
        const didStart = await this.start();
        if (!didStart || cancelled || !socket) return;
        return new Promise<void>((resolve, reject) => {
          resolveFinish = resolve;
          rejectFinish = reject;
          finishTimer = setTimeout(
            () => fail('等待流式语音播放结束超时'),
            FINISH_TIMEOUT_MS,
          );
          try {
            socket?.send(JSON.stringify({ type: 'finish' }));
          } catch {
            fail('无法结束流式语音会话');
          }
        });
      })();
      return finishPromise;
    },

    cancel(): Promise<void> {
      if (cancelPromise) return cancelPromise;
      cancelPromise = (async () => {
        cancelled = true;
        clearTimers();
        if (!started && resolveStart) resolveStart(false);
        if (finishPromise && resolveFinish) resolveFinish();
        try {
          if (socket?.readyState === 1) socket.send(JSON.stringify({ type: 'cancel' }));
        } finally {
          closeSocket();
          await dependencies.stopPcmPlayback();
        }
      })();
      return cancelPromise;
    },
  };
}
