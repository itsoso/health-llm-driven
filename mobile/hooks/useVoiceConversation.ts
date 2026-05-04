import { useCallback, useEffect, useRef, useState } from 'react';
import Voice, {
  type SpeechResultsEvent,
  type SpeechErrorEvent,
} from '@react-native-voice/voice';
import * as Speech from 'expo-speech';
import api from '../services/api';

/**
 * 语音连续对话状态机.
 *
 * 流程:
 *   idle → listening → thinking → speaking → listening (循环直到 exit)
 *
 * 简化点 (MVP):
 * - tap-to-speak: 用户按一下开始说, 说完自动 onSpeechEnd 结束, 或点一下提前结束
 * - 完整响应收齐再 TTS 整段念 (不流式, 降低复杂度)
 * - TTS 期间点击 listening 能打断: 先 Speech.stop(), 再开始录音
 *
 * 后续迭代:
 * - 流式 TTS (边收 chunk 边念)
 * - VAD 自动静音检测
 * - 音频会话 category (后台播放 / duck 其他音频)
 */
export type VoiceState = 'idle' | 'listening' | 'thinking' | 'speaking' | 'error';

export interface VoiceTurn {
  role: 'user' | 'assistant';
  text: string;
  at: number;
}

export function useVoiceConversation() {
  const [state, setState] = useState<VoiceState>('idle');
  const [transcript, setTranscript] = useState('');
  const [turns, setTurns] = useState<VoiceTurn[]>([]);
  const [error, setError] = useState<string | null>(null);

  const latestPartialRef = useRef('');
  const conversationIdRef = useRef<string | undefined>(undefined);

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
      // 用户说完, 自动提交
      const text = (latestPartialRef.current || '').trim();
      if (text) {
        submit(text);
      } else {
        setState('idle');
      }
    };
    Voice.onSpeechError = (e: SpeechErrorEvent) => {
      const msg = e.error?.message || '语音识别失败';
      setError(msg);
      setState('error');
    };
    return () => {
      Voice.destroy().then(() => Voice.removeAllListeners());
      Speech.stop();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Actions ────────────────────────────────────────────────────
  const startListening = useCallback(async () => {
    try {
      await Speech.stop(); // 打断 TTS
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
    try {
      await Voice.stop();
    } catch {
      // ignore
    }
  }, []);

  const speak = useCallback((text: string) => {
    return new Promise<void>((resolve) => {
      Speech.speak(text, {
        language: 'zh-CN',
        rate: 1.0,
        pitch: 1.0,
        onDone: () => resolve(),
        onStopped: () => resolve(),
        onError: () => resolve(),
      });
    });
  }, []);

  const submit = useCallback(async (userText: string) => {
    setState('thinking');
    setTurns((prev) => [...prev, { role: 'user', text: userText, at: Date.now() }]);

    try {
      // 调 orchestrator, 带 source=siri 让后端走口语化 prompt.
      const { data } = await api.post('/orchestrator/chat', {
        query: userText,
        source: 'siri',
        conversation_id: conversationIdRef.current,
      });
      if (data.conversation_id) {
        conversationIdRef.current = data.conversation_id;
      }
      const reply = (data.synthesis || data.message || '').trim();
      if (!reply) {
        setState('idle');
        return;
      }
      setTurns((prev) => [...prev, { role: 'assistant', text: reply, at: Date.now() }]);
      setState('speaking');
      await speak(reply);
      // 念完自动回到 idle, 等用户点麦克风继续; 不自动开新录音避免误触发
      setState('idle');
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || '请求失败';
      setError(msg);
      setTurns((prev) => [...prev, { role: 'assistant', text: `[错误] ${msg}`, at: Date.now() }]);
      setState('error');
    }
  }, [speak]);

  const reset = useCallback(() => {
    Speech.stop();
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
