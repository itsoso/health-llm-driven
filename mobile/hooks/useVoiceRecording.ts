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

  // 录音结束后把 audio session 从「录音模式」放回来 (allowsRecording:false)。
  // iOS 上录音期间 session 是 record/playAndRecord 类别, 占着麦克风; 不显式释放,
  // 下次点输入框键盘可能弹不出 / TextInput 摸不到 (键盘与麦克风 audio session 互斥)。
  // stopAndTranscribe / cancelRecording 都必须走这里 —— 否则语音后键盘失效。
  const releaseAudioSession = useCallback(async () => {
    try {
      await setAudioModeAsync({ allowsRecording: false });
    } catch {
      // 释放失败不阻断 UI; 但不静默吞掉调试信息。
      if (__DEV__) console.warn('[useVoiceRecording] release audio session failed');
    }
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      clearTimer();
      Voice.stop().catch(() => {});
      try { recorder.stop(); } catch {}
      // 卸载时若还占着录音 session, 放回来 (不阻塞卸载, fire-and-forget)。
      void setAudioModeAsync({ allowsRecording: false }).catch(() => {});
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
        await releaseAudioSession();
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
  }, [attachVoiceHandlers, clearTimer, recorder, releaseAudioSession]);

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
      await releaseAudioSession();  // 释放录音 session, 否则语音后键盘弹不出。
      return;
    }

    setIsTranscribing(true);
    try {
      let text = '';
      if (usingFallbackRef.current) {
        // 备胎:旧链路 录音 → base64 → 后端 Whisper
        await recorder.stop();
        // 停录音后立刻放回 session (在转写网络请求之前) —— 转写可能耗时几秒,
        // 期间键盘/输入应已可用, 不必等转写回来才释放麦克风占用。
        await releaseAudioSession();
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
      await releaseAudioSession();
    }
  }, [opts, clearTimer, recorder, releaseAudioSession]);

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
    await releaseAudioSession();  // 取消同样要释放, 否则语音后键盘弹不出。
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
  }, [clearTimer, recorder, releaseAudioSession]);

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
