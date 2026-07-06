import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert } from 'react-native';
import Voice, {
  type SpeechResultsEvent,
} from '@react-native-voice/voice';
import {
  useAudioRecorder,
  RecordingPresets,
  setAudioModeAsync,
  requestRecordingPermissionsAsync,
} from 'expo-audio';
import * as Haptics from 'expo-haptics';
import { transcribeAudio } from '../services/transcribe';

export interface VoiceRecordingState {
  isRecording: boolean;
  isTranscribing: boolean;
  durationMs: number;
  partialText: string;
}

/**
 * 按住说话 → 文字。
 *
 * 主路径:iOS 端上识别(@react-native-voice/voice = Speech framework,zh-CN)。
 *   - 识别在说话过程中已实时进行,松手即出字 —— 对齐 DeepSeek/豆包 的速度感;
 *   - 边说边出 partialText,录音蒙层实时显示;
 *   - 不依赖网络/云端配额(2026-07-06 实锤:云端 Whisper 代理 429 quota 全挂,
 *     旧「录完→base64 上传→等云端」链路又慢又脆)。
 * 备胎:Voice.start 本身抛错(系统听写被禁用等)→ 自动降级旧链路
 *   expo-audio 录音 + 后端 /chat/transcribe。
 */
export function useVoiceRecording(opts?: {
  onTranscript?: (text: string) => void;
}) {
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [durationMs, setDurationMs] = useState(0);
  const [partialText, setPartialText] = useState('');

  // 备胎(云端)路径才用的录音器;端上路径不碰它。
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const cancelledRef = useRef(false);
  const readyRef = useRef(false);
  const usingFallbackRef = useRef(false);
  const latestTextRef = useRef('');
  // stopAndTranscribe 等待最终结果的 resolver;Voice 事件回调经它交卷。
  const finalizeRef = useRef<((text: string) => void) | null>(null);

  const clearTimer = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      clearTimer();
      Voice.stop().catch(() => {});
      try { recorder.stop(); } catch {}
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clearTimer]);

  /**
   * 每次开录都重挂 Voice 全局回调:voice-chat 页 unmount 时会 Voice.destroy +
   * removeAllListeners(Voice 是全局单例),挂载期一次性绑定会被它清掉。
   */
  const attachVoiceHandlers = useCallback(() => {
    Voice.onSpeechPartialResults = (e: SpeechResultsEvent) => {
      const v = e.value?.[0] || '';
      if (v) {
        latestTextRef.current = v;
        setPartialText(v);
      }
    };
    Voice.onSpeechResults = (e: SpeechResultsEvent) => {
      const v = e.value?.[0] || latestTextRef.current;
      latestTextRef.current = v;
      setPartialText(v);
      finalizeRef.current?.(v);
    };
    Voice.onSpeechEnd = () => {
      finalizeRef.current?.(latestTextRef.current);
    };
    Voice.onSpeechError = () => {
      // 已有 partial 时不当失败:iOS 在 stop 边缘常报 1110(no speech)之类,
      // 拿已识别文本交卷;完全没字的情形由 stopAndTranscribe 的空文本分支提示。
      finalizeRef.current?.(latestTextRef.current);
    };
  }, []);

  const startRecording = useCallback(async () => {
    try {
      readyRef.current = false;
      cancelledRef.current = false;
      latestTextRef.current = '';
      setPartialText('');

      const perm = await requestRecordingPermissionsAsync();
      if (!perm.granted) {
        Alert.alert('需要麦克风权限', '请在 iPhone 设置 → 小巴 → 麦克风 中开启权限');
        return;
      }

      await setAudioModeAsync({
        allowsRecording: true,
        playsInSilentMode: true,
      });

      try {
        attachVoiceHandlers();
        await Voice.start('zh-CN');
        usingFallbackRef.current = false;
      } catch {
        // 端上识别不可用(系统听写被关等)→ 降级旧链路:录音 + 云端转写
        usingFallbackRef.current = true;
        await recorder.prepareToRecordAsync();
        recorder.record();
      }

      if (cancelledRef.current) {
        // 按下后极快松手(轻点):start 还在途中就被 cancelRecording — 不得进入
        // 录音态, 否则出「幽灵录音」(蒙层常驻、无人来 stop)。
        readyRef.current = false;
        if (usingFallbackRef.current) {
          try { recorder.stop(); } catch {}
        } else {
          Voice.cancel().catch(() => {});
        }
        try { await setAudioModeAsync({ allowsRecording: false }); } catch {}
        return;
      }
      readyRef.current = true;
      setIsRecording(true);
      setDurationMs(0);

      const start = Date.now();
      timerRef.current = setInterval(() => {
        setDurationMs(Date.now() - start);
      }, 200);

      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    } catch (err: any) {
      try { await setAudioModeAsync({ allowsRecording: false }); } catch {}
      setIsRecording(false);
      clearTimer();
      const msg = err?.message || String(err);
      Alert.alert('录音启动失败', msg);
    }
  }, [attachVoiceHandlers, clearTimer, recorder]);

  const stopAndTranscribe = useCallback(async () => {
    if (!readyRef.current) return;
    clearTimer();
    setIsRecording(false);

    if (cancelledRef.current) {
      if (usingFallbackRef.current) {
        try { await recorder.stop(); } catch {}
      } else {
        Voice.cancel().catch(() => {});
      }
      setPartialText('');
      return;
    }

    setIsTranscribing(true);
    try {
      let text = '';
      if (usingFallbackRef.current) {
        // 备胎:旧链路 录音 → base64 → 后端 Whisper
        await recorder.stop();
        const uri = recorder.uri;
        if (uri) {
          text = await transcribeAudio(uri);
        }
      } else {
        // 端上:识别已实时完成,stop 后最终结果通常 <300ms 就位。
        // 1.2s 兜底超时拿最新 partial 交卷,绝不让用户干等。
        text = await new Promise<string>((resolve) => {
          let done = false;
          const finish = (t: string) => {
            if (done) return;
            done = true;
            resolve(t || '');
          };
          finalizeRef.current = finish;
          Voice.stop().catch(() => finish(latestTextRef.current));
          setTimeout(() => finish(latestTextRef.current), 1200);
        });
        finalizeRef.current = null;
      }

      const trimmed = (text || '').trim();
      if (trimmed) {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
        opts?.onTranscript?.(trimmed);
      } else {
        Alert.alert('未识别到语音', '请靠近麦克风重试');
      }
    } catch {
      Alert.alert('语音识别失败', '请稍后再试');
    } finally {
      setIsTranscribing(false);
      setPartialText('');
      try { await setAudioModeAsync({ allowsRecording: false }); } catch {}
    }
  }, [opts, clearTimer, recorder]);

  const cancelRecording = useCallback(async () => {
    cancelledRef.current = true;
    clearTimer();
    setIsRecording(false);
    setPartialText('');
    if (usingFallbackRef.current) {
      try { await recorder.stop(); } catch {}
    } else {
      Voice.cancel().catch(() => {});
    }
    try { await setAudioModeAsync({ allowsRecording: false }); } catch {}
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
  }, [clearTimer, recorder]);

  return {
    isRecording,
    isTranscribing,
    durationMs,
    partialText,
    startRecording,
    stopAndTranscribe,
    cancelRecording,
  };
}
