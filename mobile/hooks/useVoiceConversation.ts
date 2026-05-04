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

  // iOS 端 AVAudioSession 模式: 允许后台播 + 混音
  useEffect(() => {
    setAudioModeAsync({
      playsInSilentMode: true,
      shouldPlayInBackground: false,
      interruptionMode: 'duckOthers',
      allowsRecording: true,
    }).catch(() => {});
  }, []);

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
      // 兜底: player 若永不触发 finish (比如 mp3 损坏), 1.5x 预估时长后硬结束
      // 预估每 10 个字 ~ 1 秒; 最小 2 秒, 最多 30 秒
      const estMs = Math.max(2000, Math.min(30000, text.length * 120));
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
      for await (const evt of streamChat(userText, conversationIdRef.current, undefined, ac.signal)) {
        if (evt.type === 'token' || evt.type === 'tool') {
          const chunk = evt.content || '';
          if (!chunk) continue;
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
          enqueueSentences(chunk);
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
    Voice.onSpeechPartialResults = (e: SpeechResultsEvent) => {
      const val = e.value?.[0] || '';
      latestPartialRef.current = val;
      setTranscript(val);
    };
    Voice.onSpeechResults = (e: SpeechResultsEvent) => {
      const val = e.value?.[0] || latestPartialRef.current;
      latestPartialRef.current = val;
      setTranscript(val);
    };
    Voice.onSpeechEnd = () => {
      const text = (latestPartialRef.current || '').trim();
      if (text) submit(text);
      else setState('idle');
    };
    Voice.onSpeechError = (e: SpeechErrorEvent) => {
      const msg = e.error?.message || '语音识别失败';
      setError(msg);
      setState('error');
    };
    return () => {
      Voice.destroy().then(() => Voice.removeAllListeners());
      stopCurrentSpeech();
      abortRef.current?.abort();
      cleanupTmpTts().catch(() => {});
    };
  }, [submit, stopCurrentSpeech]);

  const startListening = useCallback(async () => {
    try {
      stopCurrentSpeech();
      ttsQueueRef.current = [];
      abortRef.current?.abort();
      setError(null);
      setTranscript('');
      latestPartialRef.current = '';
      setState('listening');
      await Voice.start('zh-CN');
    } catch (e: any) {
      setError(String(e?.message || e));
      setState('error');
    }
  }, [stopCurrentSpeech]);

  const stopListening = useCallback(async () => {
    try { await Voice.stop(); } catch {}
  }, []);

  const reset = useCallback(() => {
    stopCurrentSpeech();
    ttsQueueRef.current = [];
    abortRef.current?.abort();
    Voice.stop().catch(() => {});
    setState('idle');
    setTranscript('');
    setError(null);
  }, [stopCurrentSpeech]);

  return {
    state,
    transcript,
    turns,
    error,
    startListening,
    stopListening,
    reset,
    isActive: state !== 'idle' && state !== 'error',
  };
}
