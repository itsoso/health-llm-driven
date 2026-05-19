/**
 * 按用户偏好播报文本 — cloud / iOS provider 自动分支, 返回可取消句柄.
 *
 * 直接 Speech.speak(text, { language: 'zh-CN' }) 会忽略用户在"语音风格"页选的
 * 私享女声 / 港普 / 知性等档位, 永远走 iOS 默认嗓音 — 因此所有播报点都该走这个 helper.
 *
 * voice-style.tsx 的 preview 路径有同款实现, 但是行内的; 这里抽出来给 ChatBubble 等
 * 其它播报点复用.
 *
 * 不依赖 React, 可在任意调用点使用.
 */
import * as Speech from 'expo-speech';
import { createAudioPlayer } from 'expo-audio';
import {
  loadVoiceStyle, getVoiceStyle, resolveIosSpeechOptions,
} from './voiceStyle';
import { synthesize as cloudSynthesize } from './cloudTts';
import { estimateTtsFallbackMs, shouldFinishAudioPlayback } from '../utils/audioPlayback';
import { splitTextForCloudTts } from '../utils/ttsText';

export interface SpeakHandle {
  /** 立即停止播放; 多次调用安全. 已结束的句柄调用也安全. */
  cancel: () => void;
}

export interface SpeakCallbacks {
  onDone?: () => void;     // 自然播完
  onStopped?: () => void;  // cancel() / Speech.stop() 触发
  onError?: (e: unknown) => void;
  /**
   * 云端合成失败,自动降级到 iOS 系统嗓音前触发一次. 调用方可以借此提示用户
   * "云端语音暂不可用,临时使用系统嗓音" — 否则用户只听到嗓音变了不知道为何.
   */
  onFallback?: (kind: 'cloud_to_ios') => void;
}

/**
 * 按用户保存的语音偏好播报一段文本.
 *
 * 行为:
 * - cloud provider: 调后端 /tts/synthesize 拿 mp3, 用 expo-audio 播; 失败降级 iOS 默认
 * - ios provider: 用 resolveIosSpeechOptions 拿到合法 voice id, Speech.speak
 * - 返回 handle 后, cancel() 会停掉播放并触发 onStopped (cloud 路径同理)
 *
 * 调用方负责: setAudioMode (静音模式播放 / duckOthers 等)
 * 不在这里设, 避免重复 / 跨场景污染.
 */
export async function speakWithUserVoice(
  text: string,
  callbacks: SpeakCallbacks = {},
): Promise<SpeakHandle> {
  const trimmed = text.trim();
  if (!trimmed) {
    callbacks.onError?.(new Error('text empty'));
    return { cancel: () => {} };
  }

  const style = await loadVoiceStyle();
  const opt = getVoiceStyle(style);

  // iOS 路径 — 同步 Speech.speak, cancel = Speech.stop
  if (opt.provider === 'ios') {
    const speechOpts = await resolveIosSpeechOptions(style);
    let finished = false;
    const finishOnce = (kind: 'done' | 'stopped' | 'error', err?: unknown) => {
      if (finished) return;
      finished = true;
      if (kind === 'done') callbacks.onDone?.();
      else if (kind === 'stopped') callbacks.onStopped?.();
      else callbacks.onError?.(err);
    };
    Speech.speak(trimmed, {
      ...speechOpts,
      onDone: () => finishOnce('done'),
      onStopped: () => finishOnce('stopped'),
      onError: (e) => finishOnce('error', e),
    });
    return {
      cancel: () => {
        try { Speech.stop(); } catch {}
        finishOnce('stopped');
      },
    };
  }

  // cloud / voxcpm 路径 — 按后端句级 TTS 限制切段, 拉 mp3 后串行播放.
  // 私教长回复如果整段提交会超过 backend max_length=500, 触发 422 后降级到
  // iOS 默认嗓音; 这里统一在公共入口切段, 避免每个 UI 调用点重复处理。
  // 段间预合成 (chunk N 播放时并发 synth N+1), 让多段播放接近无缝。
  try {
    const voiceKey = opt.cloudVoiceKey ?? 'cloned_private_female';
    const chunks = splitTextForCloudTts(trimmed);
    if (chunks.length === 0) throw new Error('text empty');

    let finished = false;
    let currentPlayer: ReturnType<typeof createAudioPlayer> | null = null;
    let currentSub: { remove?: () => void } | null = null;
    let timeout: ReturnType<typeof setTimeout> | null = null;

    const synthCache = new Map<number, Promise<{ localUri: string }>>();
    const startSynth = (i: number) => {
      if (i < 0 || i >= chunks.length) return null;
      let p = synthCache.get(i);
      if (!p) {
        p = cloudSynthesize({ text: chunks[i], voiceKey });
        synthCache.set(i, p);
      }
      return p;
    };

    const finishOnce = (kind: 'done' | 'stopped' | 'error', err?: unknown) => {
      if (finished) return;
      finished = true;
      if (timeout) {
        clearTimeout(timeout);
        timeout = null;
      }
      try { currentSub?.remove?.(); } catch {}
      try { currentPlayer?.remove(); } catch {}
      currentSub = null;
      currentPlayer = null;
      // 取消还在进行的 prefetch — promise 本身没法 abort, 但避免后续 await
      synthCache.clear();
      if (kind === 'done') callbacks.onDone?.();
      else if (kind === 'stopped') callbacks.onStopped?.();
      else callbacks.onError?.(err);
    };

    const playChunk = async (index: number) => {
      if (finished) return;
      if (index >= chunks.length) {
        finishOnce('done');
        return;
      }
      const chunk = chunks[index];
      const synthPromise = startSynth(index);
      if (!synthPromise) {
        finishOnce('done');
        return;
      }
      const { localUri } = await synthPromise;
      if (finished) return;

      // 预合成下一段, 失败先吞掉; 真正轮到它播放时再 throw.
      startSynth(index + 1)?.catch(() => {});

      const player = createAudioPlayer({ uri: localUri });
      currentPlayer = player;
      let chunkFinished = false;
      const finishChunk = () => {
        if (chunkFinished || finished) return;
        chunkFinished = true;
        if (timeout) {
          clearTimeout(timeout);
          timeout = null;
        }
        try { currentSub?.remove?.(); } catch {}
        try { player.remove(); } catch {}
        currentSub = null;
        currentPlayer = null;
        synthCache.delete(index);
        playChunk(index + 1).catch((e) => finishOnce('error', e));
      };

      currentSub = player.addListener('playbackStatusUpdate', (s: any) => {
        if (shouldFinishAudioPlayback(s)) finishChunk();
      });
      timeout = setTimeout(finishChunk, estimateTtsFallbackMs(chunk, (player as any).duration));
      player.play();
    };

    // 等第一段完成合成并启动播放后再返回句柄；这样如果首段云端合成失败，
    // 仍会落到下面的 iOS fallback, 保持原有降级语义。
    await playChunk(0);

    return {
      cancel: () => {
        if (timeout) {
          clearTimeout(timeout);
          timeout = null;
        }
        try { currentPlayer?.pause(); } catch {}
        finishOnce('stopped');
      },
    };
  } catch (e) {
    // 云端不通 → 降级到 iOS, 但不要用裸 zh-CN (那会让 iOS 选系统默认嗓音,
    // 听起来和 "没读用户偏好" 一样, 是真实用户报过的 bug).
    // 用 resolveIosSpeechOptions 至少保留 language/rate/pitch; cloud 用户
    // 没选 iOS voice → 仍是系统默认音色, 但 dev 日志能看到是因为云端挂了.
    if (__DEV__) {
      console.warn('[speakWithUserVoice] cloud failed, falling back to iOS:', e);
    }
    callbacks.onFallback?.('cloud_to_ios');
    try {
      const fallbackOpts = await resolveIosSpeechOptions(style);
      // iOS 引擎对超长中文会切到中途, 复用 cloud 的切段器 (用更小的 maxChars,
      // iOS 比 CosyVoice 更敏感, 300 字一段比较稳).
      const iosChunks = splitTextForCloudTts(trimmed, 300);
      let stopped = false;
      const speakIndex = (i: number) => {
        if (stopped) return;
        if (i >= iosChunks.length) {
          callbacks.onDone?.();
          return;
        }
        Speech.speak(iosChunks[i], {
          ...fallbackOpts,
          onDone: () => speakIndex(i + 1),
          onStopped: () => {
            if (stopped) return;
            stopped = true;
            callbacks.onStopped?.();
          },
          onError: (err) => {
            if (stopped) return;
            stopped = true;
            callbacks.onError?.(err);
          },
        });
      };
      speakIndex(0);
      return {
        cancel: () => {
          stopped = true;
          try { Speech.stop(); } catch {}
        },
      };
    } catch (fallbackErr) {
      callbacks.onError?.(fallbackErr);
    }
    return {
      cancel: () => { try { Speech.stop(); } catch {} },
    };
  }
}
