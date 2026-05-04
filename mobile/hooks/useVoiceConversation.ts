import { useCallback, useEffect, useRef, useState } from 'react';
import Voice, {
  type SpeechResultsEvent,
  type SpeechErrorEvent,
} from '@react-native-voice/voice';
import * as Speech from 'expo-speech';
import { streamChat } from '../services/chat';

/**
 * 语音连续对话状态机.
 *
 * idle → listening → thinking → speaking → idle (等下一轮)
 *
 * 走 /agent/stream (OpenClaw gateway): 后端按 needsSkill 自动分流到 skill
 * (记录类写库) 或 orchestrator (分析类). 30s 超时变 120s, 并且流式边收边念.
 *
 * TTS 用"句尾符号"(。！？.!?\n) 切段, 收到一整句就入队播, 降低首音等待.
 * Speech.speak 并发会打架, 所以用 isSpeakingRef + pending 队列串行化.
 *
 * 打断: startListening 会 Speech.stop() + 清空 pending, 让用户随时能插话.
 */
export type VoiceState = 'idle' | 'listening' | 'thinking' | 'speaking' | 'error';

export interface VoiceTurn {
  role: 'user' | 'assistant';
  text: string;
  at: number;
}

const SENTENCE_END = /[。！？.!?\n]/;

export function useVoiceConversation() {
  const [state, setState] = useState<VoiceState>('idle');
  const [transcript, setTranscript] = useState('');
  const [turns, setTurns] = useState<VoiceTurn[]>([]);
  const [error, setError] = useState<string | null>(null);

  const latestPartialRef = useRef('');
  const conversationIdRef = useRef<number | undefined>(undefined);

  // 流式累积 + TTS 队列
  const pendingTextRef = useRef('');           // 未切成句的 tail
  const assistantTextRef = useRef('');         // 本轮完整回复 (用于 UI)
  const ttsQueueRef = useRef<string[]>([]);
  const isSpeakingRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);

  const flushTTS = useCallback(() => {
    if (isSpeakingRef.current) return;
    const next = ttsQueueRef.current.shift();
    if (!next) return;
    isSpeakingRef.current = true;
    Speech.speak(next, {
      language: 'zh-CN', rate: 1.0, pitch: 1.0,
      onDone: () => { isSpeakingRef.current = false; flushTTS(); },
      onStopped: () => { isSpeakingRef.current = false; ttsQueueRef.current = []; },
      onError: () => { isSpeakingRef.current = false; flushTTS(); },
    });
  }, []);

  const enqueueSentences = useCallback((chunk: string) => {
    pendingTextRef.current += chunk;
    // 反复切出末尾句尾符号之前的部分
    while (true) {
      const m = pendingTextRef.current.match(SENTENCE_END);
      if (!m || m.index === undefined) break;
      const cut = m.index + 1;
      const sentence = pendingTextRef.current.slice(0, cut).trim();
      pendingTextRef.current = pendingTextRef.current.slice(cut);
      if (sentence) ttsQueueRef.current.push(sentence);
    }
    flushTTS();
  }, [flushTTS]);

  const flushTail = useCallback(() => {
    const tail = pendingTextRef.current.trim();
    pendingTextRef.current = '';
    if (tail) {
      ttsQueueRef.current.push(tail);
      flushTTS();
    }
  }, [flushTTS]);

  const waitTTSDrain = useCallback(() => {
    return new Promise<void>((resolve) => {
      const check = () => {
        if (ttsQueueRef.current.length === 0 && !isSpeakingRef.current) {
          resolve();
        } else {
          setTimeout(check, 200);
        }
      };
      check();
    });
  }, []);

  const submit = useCallback(async (userText: string) => {
    setState('thinking');
    setTurns((prev) => [...prev, { role: 'user', text: userText, at: Date.now() }]);

    // 重置本轮状态
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
  }, [enqueueSentences, flushTail, waitTTSDrain]);

  // ── STT handlers ───────────────────────────────────────────────
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
      Speech.stop();
      abortRef.current?.abort();
    };
  }, [submit]);

  const startListening = useCallback(async () => {
    try {
      // 打断进行中的 TTS / 请求
      Speech.stop();
      ttsQueueRef.current = [];
      isSpeakingRef.current = false;
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
  }, []);

  const stopListening = useCallback(async () => {
    try { await Voice.stop(); } catch {}
  }, []);

  const reset = useCallback(() => {
    Speech.stop();
    ttsQueueRef.current = [];
    isSpeakingRef.current = false;
    abortRef.current?.abort();
    Voice.stop().catch(() => {});
    setState('idle');
    setTranscript('');
    setError(null);
  }, []);

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
