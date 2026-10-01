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

type PlayerSlot = { available: Promise<void>; owner: symbol | null };
// Dependencies may be copied per session; the native start function identifies
// the shared singleton player, not the dependencies object's identity.
const playerSlots = new WeakMap<StreamingTtsDependencies['startPcmPlayback'], PlayerSlot>();

export function createCloudStreamingTtsSession(
  options: StreamingTtsOptions,
  dependencies: StreamingTtsDependencies = defaultDependencies,
): StreamingTtsSession {
  let socket: SocketLike | null = null;
  let cancelled = false;
  let started = false;
  let completed = false;
  let finishing = false;
  let playerStartPromise: Promise<void> | null = null;
  let playerStopPromise: Promise<void> | null = null;
  let terminalError: Error | null = null;
  const playerOwner = Symbol('streaming-tts');
  let playerSlot: PlayerSlot | null = null;
  let releasePlayer: (() => void) | null = null;
  let rejectPlayerRelease: ((error: unknown) => void) | null = null;
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

  // Cancellation must finish native startup/cleanup before another session
  // acquires the shared player. Late callbacks may not stop its new owner.
  const stopPlayer = (): Promise<void> => {
    if (!playerStopPromise) {
      const stopOwnedPlayer = async () => {
        if (playerSlot?.owner !== playerOwner) {
          releasePlayer?.();
          return;
        }
        try {
          await dependencies.stopPcmPlayback();
          playerSlot.owner = null;
          releasePlayer?.();
        } catch (error) {
          rejectPlayerRelease?.(error);
          throw error;
        }
      };
      playerStopPromise = (playerStartPromise || Promise.resolve()).then(stopOwnedPlayer, stopOwnedPlayer);
    }
    return playerStopPromise;
  };

  const fail = (message: string) => {
    if (cancelled || completed) return;
    const error = new Error(message || '流式语音服务暂时不可用');
    terminalError = error;
    cancelled = true;
    clearTimers();
    closeSocket();
    void stopPlayer().catch(() => { terminalError = new Error('无法停止流式语音播放'); });
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
      if (started || playerStartPromise) return;
      if (message.encoding && message.encoding !== 'pcm_s16le') {
        fail('流式语音格式不受支持');
        return;
      }
      try {
        playerSlot = playerSlots.get(dependencies.startPcmPlayback) || { available: Promise.resolve(), owner: null };
        playerSlots.set(dependencies.startPcmPlayback, playerSlot);
        const predecessor = playerSlot.available;
        const released = new Promise<void>((resolve, reject) => {
          releasePlayer = resolve;
          rejectPlayerRelease = reject;
        });
        // A cleanup failure poisons the slot: a later session must not start
        // over a player whose ownership could not safely be relinquished.
        playerSlot.available = predecessor.then(() => released);
        void playerSlot.available.catch(() => { terminalError = new Error('语音播放器清理失败'); });
        playerStartPromise = predecessor.then(async () => {
          if (cancelled) return;
          playerSlot!.owner = playerOwner;
          await dependencies.startPcmPlayback(message.sample_rate || 24000);
        });
        await playerStartPromise;
        if (cancelled) return;
        started = true;
        if (startTimer) clearTimeout(startTimer);
        resolveStart?.(true);
      } catch (error: any) {
        fail(error?.message || '无法启动流式语音播放');
      }
      return;
    }
    if (message.type === 'audio' && message.audio) {
      if (!playerStartPromise || finishing) {
        fail('流式语音返回了无效音频顺序');
        return;
      }
      playerChain = playerChain.then(async () => {
        await playerStartPromise;
        if (cancelled || completed || playerSlot?.owner !== playerOwner) return;
        return dependencies.enqueuePcmPlayback(message.audio!);
      });
      playerChain.catch(error => fail(error?.message || '流式语音播放失败'));
      return;
    }
    if (message.type === 'done') {
      if (finishing) return;
      if (!playerStartPromise) {
        fail('流式语音返回了无效结束顺序');
        return;
      }
      finishing = true;
      try {
        await playerStartPromise;
        await playerChain;
        if (cancelled || completed || playerSlot?.owner !== playerOwner) return;
        await dependencies.finishPcmPlayback();
        if (cancelled) return;
        completed = true;
        playerSlot.owner = null;
        releasePlayer?.();
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
          if (!cancelled && !completed && !finishing) {
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
      if (terminalError) throw terminalError;
      if (!didStart || cancelled || !socket || socket.readyState > 1) {
        throw new Error('流式语音会话不可用');
      }
      socket.send(JSON.stringify({ type: 'append', text: clean }));
    },

    finish(): Promise<void> {
      if (finishPromise) return finishPromise;
      finishPromise = (async () => {
        const didStart = await this.start();
        if (terminalError) throw terminalError;
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
          await stopPlayer();
        }
      })();
      return cancelPromise;
    },
  };
}
