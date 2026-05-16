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

export interface SpeakHandle {
  /** 立即停止播放; 多次调用安全. 已结束的句柄调用也安全. */
  cancel: () => void;
}

export interface SpeakCallbacks {
  onDone?: () => void;     // 自然播完
  onStopped?: () => void;  // cancel() / Speech.stop() 触发
  onError?: (e: unknown) => void;
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

  // cloud / voxcpm 路径 — 拉 mp3 后用 expo-audio 播
  try {
    const voiceKey = opt.cloudVoiceKey ?? 'cloned_private_female';
    const { localUri } = await cloudSynthesize({ text: trimmed, voiceKey });
    const player = createAudioPlayer({ uri: localUri });

    let finished = false;
    let sub: { remove?: () => void } | null = null;
    const finishOnce = (kind: 'done' | 'stopped' | 'error', err?: unknown) => {
      if (finished) return;
      finished = true;
      try { sub?.remove?.(); } catch {}
      try { player.remove(); } catch {}
      if (kind === 'done') callbacks.onDone?.();
      else if (kind === 'stopped') callbacks.onStopped?.();
      else callbacks.onError?.(err);
    };

    sub = player.addListener('playbackStatusUpdate', (s: any) => {
      if (s?.didJustFinish || s?.finished) finishOnce('done');
    });
    player.play();

    return {
      cancel: () => {
        try { player.pause(); } catch {}
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
    try {
      const fallbackOpts = await resolveIosSpeechOptions(style);
      Speech.speak(trimmed, {
        ...fallbackOpts,
        onDone: callbacks.onDone,
        onStopped: callbacks.onStopped,
        onError: callbacks.onError,
      });
    } catch (fallbackErr) {
      callbacks.onError?.(fallbackErr);
    }
    return {
      cancel: () => { try { Speech.stop(); } catch {} },
    };
  }
}
