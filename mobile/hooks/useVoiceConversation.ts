import { useCallback, useEffect, useRef, useState } from 'react';
import Voice, {
  type SpeechResultsEvent,
  type SpeechErrorEvent,
} from '@react-native-voice/voice';
import * as Speech from 'expo-speech';
import { createAudioPlayer, setAudioModeAsync } from 'expo-audio';
import { streamChat } from '../services/chat';
import {
  loadVoiceStyle, resolveIosSpeechOptions, getVoiceStyle, type VoiceStyle,
} from '../services/voiceStyle';
import { synthesize as cloudSynthesize, cleanupTmpTts } from '../services/cloudTts';

/**
 * 语音连续对话状态机.
 *
 * idle → listening → thinking → speaking → idle
 *
 * TTS provider 双栈:
 *   - ios   : expo-speech AVSpeechSynthesizer (离线, 机械感)
 *   - cloud : 后端 /tts/synthesize 代理阿里云 CosyVoice (真人级, 需联网)
 *
 * 云端失败 (网络 / 后端错误) 自动降级到 ios 档, 保证不哑巴.
 *
 * TTS 用"句尾符号"(。！？.!?\n) 切段, 收到一整句就入队播. 串行播放, 避免并发打架.
 * 打断: startListening 会 stop() + 清队列, 让用户随时插话.
 */
export type VoiceState = 'idle' | 'listening' | 'thinking' | 'speaking' | 'error';

export interface VoiceTurn {
  role: 'user' | 'assistant';
  text: string;
  at: number;
}

const SENTENCE_END = /[。！？.!?\n]/;

function stripMarkdownForTTS(s: string): string {
  return s
    .replace(/```[\s\S]*?```/g, '')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/\*([^*]+)\*/g, '$1')
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/^\s*[-*+]\s+/gm, '')
    .replace(/^\s*\d+\.\s+/gm, '')
    .replace(/\|/g, ' ')
    .replace(/^[\s|:\-]+$/gm, '')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/!\[[^\]]*\]\([^)]+\)/g, '')
    .replace(/~~([^~]+)~~/g, '$1');
}

interface ActivePlayer {
  cancel: () => void;
}

export function useVoiceConversation() {
  const [state, setState] = useState<VoiceState>('idle');
  const [transcript, setTranscript] = useState('');
  const [turns, setTurns] = useState<VoiceTurn[]>([]);
  const [error, setError] = useState<string | null>(null);

  const latestPartialRef = useRef('');
  const conversationIdRef = useRef<number | undefined>(undefined);

  // 静默自动提交 — onSpeechPartialResults 收到新文字就重置 timer,
  // 持续 1.2s 没新内容 → 自动 stop + submit, 不用用户主动点停止.
  const silenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const SILENCE_AUTO_SUBMIT_MS = 1200;

  const pendingTextRef = useRef('');
  const assistantTextRef = useRef('');
  const ttsQueueRef = useRef<string[]>([]);
  const isSpeakingRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);

  // 当前 voice style (读 AsyncStorage, 每轮开播前刷新)
  const voiceStyleRef = useRef<VoiceStyle>('cloud_cloned_private_female');
  const iosOptsRef = useRef<Speech.SpeechOptions>({ language: 'zh-CN', rate: 1.0, pitch: 1.0 });

  // 云端播放中的 player, stop 时用于打断
  const activePlayerRef = useRef<ActivePlayer | null>(null);

  /**
   * iOS AVAudioSession 模式动态切换 (修复音量变小问题):
   *
   *   播放模式 (.playback category):        默认外放, 音量正常
   *   录音模式 (.playAndRecord category):   需要录音; 默认会路由到 receiver (听筒)
   *                                         导致 TTS 回放音量小
   *
   * 策略:
   *   - 初始默认 playback (allowsRecording=false) → 外放
   *   - startListening 前切到 playAndRecord (allowsRecording=true)
   *   - stopListening 后切回 playback
   *
   * 注: expo-audio 当前 API 不支持 .defaultToSpeaker / proximity 监听,
   *   要做到"贴耳自动听筒"需要原生代码, 先实现 80% 场景的音量问题.
   */
  const setPlaybackMode = useCallback(async () => {
    try {
      await setAudioModeAsync({
        playsInSilentMode: true,
        shouldPlayInBackground: false,
        interruptionMode: 'duckOthers',
        allowsRecording: false,  // → .playback category, 外放
      });
    } catch {}
  }, []);

  const setRecordingMode = useCallback(async () => {
    try {
      await setAudioModeAsync({
        playsInSilentMode: true,
        shouldPlayInBackground: false,
        interruptionMode: 'duckOthers',
        allowsRecording: true,  // → .playAndRecord category
      });
    } catch {}
  }, []);

  useEffect(() => {
    // 进入页面默认外放
    setPlaybackMode();
  }, [setPlaybackMode]);

  const refreshVoiceStyle = useCallback(async () => {
    try {
      const style = await loadVoiceStyle();
      voiceStyleRef.current = style;
      const opt = getVoiceStyle(style);
      if (opt.provider === 'ios') {
        iosOptsRef.current = await resolveIosSpeechOptions(style);
      }
    } catch {}
  }, []);

  useEffect(() => {
    refreshVoiceStyle();
  }, [refreshVoiceStyle]);

  const stopCurrentSpeech = useCallback(() => {
    try { Speech.stop(); } catch {}
    activePlayerRef.current?.cancel();
    activePlayerRef.current = null;
    isSpeakingRef.current = false;
  }, []);

  const speakViaIos = useCallback((text: string, onDone: () => void) => {
    Speech.speak(text, {
      ...iosOptsRef.current,
      onDone: () => { isSpeakingRef.current = false; onDone(); },
      onStopped: () => { isSpeakingRef.current = false; },
      onError: () => { isSpeakingRef.current = false; onDone(); },
    });
  }, []);

  const speakViaCloud = useCallback(async (text: string, onDone: () => void) => {
    const opt = getVoiceStyle(voiceStyleRef.current);
    const voiceKey = opt.cloudVoiceKey ?? 'cloned_private_female';
    try {
      const { localUri } = await cloudSynthesize({ text, voiceKey });
      // 新 player 每句一个, 简化生命周期 (非高频场景, 代价可接受)
      const player = createAudioPlayer({ uri: localUri });
      let finished = false;
      const finish = () => {
        if (finished) return;
        finished = true;
        try { player.remove(); } catch {}
        activePlayerRef.current = null;
        isSpeakingRef.current = false;
        onDone();
      };
      activePlayerRef.current = {
        cancel: () => {
          try { player.pause(); } catch {}
          finish();
        },
      };
      // 监听播放完成; expo-audio 的 status 回调通过 addListener
      const sub = player.addListener('playbackStatusUpdate', (status: any) => {
        if (status?.didJustFinish || status?.finished) {
          sub?.remove?.();
          finish();
        }
      });
      // 兜底: player 若永不触发 finish (比如 mp3 损坏), 硬超时后 finish.
      // CosyVoice 实测约每字 200-250ms (中文), 取 280ms + 8s 安全余量,
      // 必须比真实播放时长长, 否则兜底先触发 finish → 下一句重叠播.
      // 80 字 → ~22s + 8s = 30s. 最大 60s.
      const estMs = Math.max(8000, Math.min(60000, text.length * 280 + 8000));
      setTimeout(() => { if (!finished) { try { sub?.remove?.(); } catch {}; finish(); } }, estMs);
      player.play();
    } catch (e) {
      // 云端失败 → 降级 iOS
      if (__DEV__) console.warn('[TTS] cloud failed, fallback to iOS:', e);
      // 首次失败时也刷新一次 iOS voice opts 保证有得用
      if (!iosOptsRef.current.voice) {
        iosOptsRef.current = { language: 'zh-CN', rate: 1.0, pitch: 1.0 };
      }
      speakViaIos(text, onDone);
    }
  }, [speakViaIos]);

  const flushTTS = useCallback(() => {
    if (isSpeakingRef.current) return;
    const next = ttsQueueRef.current.shift();
    if (!next) return;
    isSpeakingRef.current = true;
    const provider = getVoiceStyle(voiceStyleRef.current).provider;
    const onDone = () => { isSpeakingRef.current = false; flushTTS(); };
    if (provider === 'cloud') {
      void speakViaCloud(next, onDone);
    } else {
      speakViaIos(next, onDone);
    }
  }, [speakViaCloud, speakViaIos]);

  const enqueueSentences = useCallback((chunk: string) => {
    pendingTextRef.current += chunk;
    while (true) {
      const m = pendingTextRef.current.match(SENTENCE_END);
      if (!m || m.index === undefined) break;
      const cut = m.index + 1;
      const sentence = pendingTextRef.current.slice(0, cut).trim();
      pendingTextRef.current = pendingTextRef.current.slice(cut);
      if (sentence) {
        const clean = stripMarkdownForTTS(sentence).trim();
        if (clean) ttsQueueRef.current.push(clean);
      }
    }
    flushTTS();
  }, [flushTTS]);

  const flushTail = useCallback(() => {
    const tail = pendingTextRef.current.trim();
    pendingTextRef.current = '';
    if (tail) {
      const clean = stripMarkdownForTTS(tail).trim();
      if (clean) {
        ttsQueueRef.current.push(clean);
        flushTTS();
      }
    }
  }, [flushTTS]);

  const waitTTSDrain = useCallback(() => {
    return new Promise<void>((resolve) => {
      const check = () => {
        if (ttsQueueRef.current.length === 0 && !isSpeakingRef.current) resolve();
        else setTimeout(check, 200);
      };
      check();
    });
  }, []);

  const submit = useCallback(async (userText: string) => {
    setState('thinking');
    setTurns((prev) => [...prev, { role: 'user', text: userText, at: Date.now() }]);

    await refreshVoiceStyle();

    pendingTextRef.current = '';
    assistantTextRef.current = '';
    ttsQueueRef.current = [];

    const ac = new AbortController();
    abortRef.current = ac;

    let replyStarted = false;

    try {
      let lastFailedTool = '';  // 同一 tool 连续失败只提示一次
      for await (const evt of streamChat(userText, conversationIdRef.current, undefined, ac.signal)) {
        if (evt.type === 'token' || evt.type === 'tool') {
          const chunk = evt.content || '';
          if (!chunk) continue;

          // tool 失败的可见提示文本不进 TTS 队列 — 用户听到 LLM 重试时连说 5 遍'操作未成功'噪音大
          // 同一个 tool 连续失败也只显示一次
          const isToolFailure = evt.type === 'tool' && chunk.includes('⚠️ 操作未成功');
          if (isToolFailure) {
            const toolName = evt.toolName || '';
            if (toolName && toolName === lastFailedTool) continue;  // 同 tool 重复, 跳过
            lastFailedTool = toolName;
          } else if (evt.type === 'tool') {
            lastFailedTool = '';  // 非失败事件重置去重锁
          }

          if (!replyStarted) {
            replyStarted = true;
            setState('speaking');
            setTurns((prev) => [...prev, { role: 'assistant', text: '', at: Date.now() }]);
          }
          assistantTextRef.current += chunk;
          setTurns((prev) => {
            const copy = prev.slice();
            const last = copy[copy.length - 1];
            if (last && last.role === 'assistant') {
              copy[copy.length - 1] = { ...last, text: assistantTextRef.current };
            }
            return copy;
          });
          // 失败提示不入 TTS, 用户看文字就够了
          if (!isToolFailure) {
            enqueueSentences(chunk);
          }
        } else if (evt.type === 'done') {
          if (evt.conversationId && !conversationIdRef.current) {
            conversationIdRef.current = evt.conversationId;
          }
          flushTail();
        } else if (evt.type === 'error') {
          throw new Error(evt.content || '请求出错');
        }
      }
      if (!replyStarted) {
        setState('idle');
        return;
      }
      flushTail();
      await waitTTSDrain();
      setState('idle');
    } catch (e: any) {
      const msg = e?.message || '请求失败';
      if (msg === 'aborted') {
        setState('idle');
        return;
      }
      setError(msg);
      setTurns((prev) => [...prev, { role: 'assistant', text: `[错误] ${msg}`, at: Date.now() }]);
      setState('error');
    } finally {
      abortRef.current = null;
    }
  }, [refreshVoiceStyle, enqueueSentences, flushTail, waitTTSDrain]);

  useEffect(() => {
    // 收到 partial 时重置 silence timer; 1.2s 内没新内容 → 自动 stop + submit.
    // 这比 iOS 系统的 onSpeechEnd (2-3s 才触发) 快得多, 体验上"说完即送".
    const armSilenceTimer = () => {
      if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = setTimeout(() => {
        const text = (latestPartialRef.current || '').trim();
        if (text) {
          // Voice.stop() 让 onSpeechEnd 走流程; 但 onSpeechEnd 会再次 submit,
          // 用 latestPartialRef 清空 + 直接 submit 防止双发.
          latestPartialRef.current = '';
          Voice.stop().catch(() => {});
          setPlaybackMode();
          submit(text);
        }
      }, SILENCE_AUTO_SUBMIT_MS);
    };

    Voice.onSpeechPartialResults = (e: SpeechResultsEvent) => {
      const val = e.value?.[0] || '';
      if (val && val !== latestPartialRef.current) {
        latestPartialRef.current = val;
        setTranscript(val);
        armSilenceTimer();
      }
    };
    Voice.onSpeechResults = (e: SpeechResultsEvent) => {
      const val = e.value?.[0] || latestPartialRef.current;
      latestPartialRef.current = val;
      setTranscript(val);
      armSilenceTimer();
    };
    Voice.onSpeechEnd = () => {
      // silence timer 可能已经先触发提交了, 这时 latestPartialRef 是空的, 不会重发
      if (silenceTimerRef.current) {
        clearTimeout(silenceTimerRef.current);
        silenceTimerRef.current = null;
      }
      const text = (latestPartialRef.current || '').trim();
      // 用户自然说完: 切回 playback 让后续 LLM reply TTS 走外放
      setPlaybackMode();
      if (text) submit(text);
      else if (state !== 'thinking' && state !== 'speaking') setState('idle');
    };
    Voice.onSpeechError = (e: SpeechErrorEvent) => {
      if (silenceTimerRef.current) {
        clearTimeout(silenceTimerRef.current);
        silenceTimerRef.current = null;
      }
      const msg = e.error?.message || '语音识别失败';
      setError(msg);
      setState('error');
      setPlaybackMode();
    };
    return () => {
      if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
      Voice.destroy().then(() => Voice.removeAllListeners());
      stopCurrentSpeech();
      abortRef.current?.abort();
      cleanupTmpTts().catch(() => {});
    };
  }, [submit, stopCurrentSpeech, setPlaybackMode, state]);

  const startListening = useCallback(async () => {
    try {
      stopCurrentSpeech();
      ttsQueueRef.current = [];
      abortRef.current?.abort();
      setError(null);
      setTranscript('');
      latestPartialRef.current = '';
      // 先切到 .playAndRecord, 再启动 Voice — 顺序很重要, Voice.start 依赖 session 已经就绪
      await setRecordingMode();
      setState('listening');
      await Voice.start('zh-CN');
    } catch (e: any) {
      setError(String(e?.message || e));
      setState('error');
      // 失败也切回 playback, 免得下次 TTS 又走听筒
      setPlaybackMode();
    }
  }, [stopCurrentSpeech, setRecordingMode, setPlaybackMode]);

  const stopListening = useCallback(async () => {
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }
    try { await Voice.stop(); } catch {}
    // 录音结束切回 .playback, 后续 TTS 走外放
    await setPlaybackMode();
  }, [setPlaybackMode]);

  const reset = useCallback(() => {
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }
    stopCurrentSpeech();
    ttsQueueRef.current = [];
    pendingTextRef.current = '';
    assistantTextRef.current = '';
    abortRef.current?.abort();
    Voice.stop().catch(() => {});
    Voice.cancel?.().catch(() => {});
    setPlaybackMode();
    setState('idle');
    setTranscript('');
    setError(null);
  }, [stopCurrentSpeech, setPlaybackMode]);

  /**
   * 直接喂一段文本走 TTS 播 (不走 LLM, 用于晨间简报 / 系统播报场景).
   *
   * 行为:
   *   - 把 text 作为 assistant turn 加到 turns
   *   - 按句切段入 TTS 队列, 串行播完
   *   - opts.thenListen=true: 播完自动进 listening, 接用户接话 (Agent Native 闭环)
   */
  const speakDirect = useCallback(
    async (text: string, opts?: { thenListen?: boolean }) => {
      if (!text || !text.trim()) return;
      await refreshVoiceStyle();
      // 清当前播放队列, 防止冲撞
      stopCurrentSpeech();
      ttsQueueRef.current = [];

      setState('speaking');
      setTurns((prev) => [...prev, { role: 'assistant', text, at: Date.now() }]);

      // 整段入队 (不流式, 已经是完整一段)
      pendingTextRef.current = text;
      flushTail();

      // 等队列播完
      await new Promise<void>((resolve) => {
        const check = () => {
          if (ttsQueueRef.current.length === 0 && !isSpeakingRef.current) resolve();
          else setTimeout(check, 200);
        };
        check();
      });

      if (opts?.thenListen) {
        setState('idle');
        // 等 200ms 让用户感知"该我说了"
        setTimeout(() => {
          startListening();
        }, 200);
      } else {
        setState('idle');
      }
    },
    [refreshVoiceStyle, stopCurrentSpeech, flushTail, startListening],
  );

  return {
    state,
    transcript,
    turns,
    error,
    startListening,
    stopListening,
    reset,
    speakDirect,
    isActive: state !== 'idle' && state !== 'error',
  };
}
