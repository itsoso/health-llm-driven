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
import { durationBucket, emitClientEvent } from '../services/clientEvents';
import {
  claimVoiceSession,
  isVoiceSessionOwner,
  releaseVoiceSession,
  runVoiceSessionCommand,
  runVoiceSessionStart,
  type VoiceSessionLease,
} from '../services/voiceSessionCoordinator';

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
  const startSeqRef = useRef(0);
  const transcriptionSeqRef = useRef(0);
  const sessionStartedAtRef = useRef(0);
  const terminalSentRef = useRef(false);
  const voiceLeaseRef = useRef<VoiceSessionLease | null>(null);

  const emitTerminal = useCallback((
    phase: 'completed' | 'failed' | 'cancelled',
    errorCode?: string,
  ) => {
    if (!sessionStartedAtRef.current || terminalSentRef.current) return;
    terminalSentRef.current = true;
    void emitClientEvent('voice_input_terminal', {
      phase,
      duration_bucket: durationBucket(sessionStartedAtRef.current),
      action_type: 'hold',
      ...(errorCode ? { error_code: errorCode } : {}),
    });
  }, []);

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
      if (sessionStartedAtRef.current && !terminalSentRef.current) {
        emitTerminal('cancelled', 'component_unmounted');
      }
      startSeqRef.current += 1;
      transcriptionSeqRef.current += 1;
      clearTimer();
      const lease = voiceLeaseRef.current;
      void runVoiceSessionCommand(lease, async () => {
        try { await Voice.stop(); } catch {}
        try { await recorder.stop(); } catch {}
        await setAudioModeAsync({ allowsRecording: false }).catch(() => {});
      }).finally(() => releaseVoiceSession(lease));
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clearTimer, emitTerminal, recorder]);

  /**
   * 每次开录都重挂 Voice 全局回调:voice-chat 页 unmount 时会 Voice.destroy +
   * removeAllListeners(Voice 是全局单例),挂载期一次性绑定会被它清掉。
   */
  const attachVoiceHandlers = useCallback(() => {
    Voice.onSpeechPartialResults = (e: SpeechResultsEvent) => {
      if (!isVoiceSessionOwner(voiceLeaseRef.current)) return;
      const v = e.value?.[0] || '';
      if (v) {
        latestTextRef.current = v;
        setPartialText(v);
      }
    };
    Voice.onSpeechResults = (e: SpeechResultsEvent) => {
      if (!isVoiceSessionOwner(voiceLeaseRef.current)) return;
      const v = e.value?.[0] || latestTextRef.current;
      latestTextRef.current = v;
      setPartialText(v);
      finalizeRef.current?.(v);
    };
    Voice.onSpeechEnd = () => {
      if (!isVoiceSessionOwner(voiceLeaseRef.current)) return;
      finalizeRef.current?.(latestTextRef.current);
    };
    Voice.onSpeechError = () => {
      if (!isVoiceSessionOwner(voiceLeaseRef.current)) return;
      // 已有 partial 时不当失败:iOS 在 stop 边缘常报 1110(no speech)之类,
      // 拿已识别文本交卷;完全没字的情形由 stopAndTranscribe 的空文本分支提示。
      finalizeRef.current?.(latestTextRef.current);
    };
  }, []);

  const startRecording = useCallback(async () => {
    const lease = claimVoiceSession('hold');
    voiceLeaseRef.current = lease;
    sessionStartedAtRef.current = Date.now();
    terminalSentRef.current = false;
    transcriptionSeqRef.current += 1;
    const seq = startSeqRef.current + 1;
    startSeqRef.current = seq;
    const isCurrentStart = () => (
      startSeqRef.current === seq && isVoiceSessionOwner(lease)
    );
    try {
      readyRef.current = false;
      cancelledRef.current = false;
      latestTextRef.current = '';
      setPartialText('');

      const perm = await requestRecordingPermissionsAsync();
      if (!isCurrentStart()) {
        await runVoiceSessionCommand(lease, releaseAudioSession);
        releaseVoiceSession(lease);
        return false;
      }
      if (!perm.granted) {
        releaseVoiceSession(lease);
        emitTerminal('failed', 'microphone_permission_denied');
        Alert.alert('需要麦克风权限', '请在 iPhone 设置 → 小巴 → 麦克风 中开启权限');
        return false;
      }

      const nativeStarted = await runVoiceSessionStart(
        lease,
        async () => {
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
            if (startSeqRef.current === seq && !cancelledRef.current) recorder.record();
          }
        },
        async () => {
          if (usingFallbackRef.current) {
            try { await recorder.stop(); } catch {}
          } else {
            try { await Voice.cancel(); } catch {}
          }
          await releaseAudioSession();
        },
      );
      if (!nativeStarted) {
        readyRef.current = false;
        releaseVoiceSession(lease);
        return false;
      }
      if (!isCurrentStart()) {
        readyRef.current = false;
        await runVoiceSessionCommand(lease, async () => {
          if (usingFallbackRef.current) {
            try { await recorder.stop(); } catch {}
          } else {
            try { await Voice.cancel(); } catch {}
          }
          await releaseAudioSession();
        });
        releaseVoiceSession(lease);
        return false;
      }

      if (cancelledRef.current) {
        // 按下后极快松手(轻点):start 还在途中就被 cancelRecording — 不得进入
        // 录音态, 否则出「幽灵录音」(蒙层常驻、无人来 stop)。
        readyRef.current = false;
        if (usingFallbackRef.current) {
          try { recorder.stop(); } catch {}
        } else {
          await runVoiceSessionCommand(lease, async () => {
            try { await Voice.cancel(); } catch {}
          });
        }
        await releaseAudioSession();
        releaseVoiceSession(lease);
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
      return true;
    } catch (err: any) {
      await runVoiceSessionCommand(lease, async () => {
        try { await Voice.cancel(); } catch {}
        try { await setAudioModeAsync({ allowsRecording: false }); } catch {}
      });
      releaseVoiceSession(lease);
      readyRef.current = false;
      setIsRecording(false);
      clearTimer();
      const msg = err?.message || String(err);
      emitTerminal('failed', 'recording_start_failed');
      Alert.alert('录音启动失败', msg);
      return false;
    }
  }, [attachVoiceHandlers, clearTimer, emitTerminal, recorder, releaseAudioSession]);

  const stopAndTranscribe = useCallback(async () => {
    const lease = voiceLeaseRef.current;
    if (!readyRef.current) {
      startSeqRef.current += 1;
      clearTimer();
      setIsRecording(false);
      void runVoiceSessionCommand(lease, async () => {
        if (usingFallbackRef.current) {
          try { await recorder.stop(); } catch {}
        } else {
          try { await Voice.cancel(); } catch {}
        }
        await releaseAudioSession();
      }).finally(() => releaseVoiceSession(lease));
      emitTerminal('cancelled', 'released_before_ready');
      return;
    }
    clearTimer();
    setIsRecording(false);

    if (cancelledRef.current) {
      await runVoiceSessionCommand(lease, async () => {
        if (usingFallbackRef.current) {
          try { await recorder.stop(); } catch {}
        } else {
          try { await Voice.cancel(); } catch {}
        }
        await releaseAudioSession();
      });
      setPartialText('');
      readyRef.current = false;
      releaseVoiceSession(lease);
      emitTerminal('cancelled');
      return;
    }

    const transcriptionSeq = transcriptionSeqRef.current + 1;
    transcriptionSeqRef.current = transcriptionSeq;
    setIsTranscribing(true);
    try {
      let text = '';
      if (usingFallbackRef.current) {
        // 备胎:旧链路 录音 → base64 → 后端 Whisper
        await runVoiceSessionCommand(lease, async () => {
          await recorder.stop();
          await releaseAudioSession();
        });
        releaseVoiceSession(lease);
        // 停录音后立刻放回 session (在转写网络请求之前) —— 转写可能耗时几秒,
        // 期间键盘/输入应已可用, 不必等转写回来才释放麦克风占用。
        const uri = recorder.uri;
        if (!uri) {
          emitTerminal('failed', 'recording_uri_missing');
          return;
        }
        text = await transcribeAudio(uri);
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
          void runVoiceSessionCommand(lease, async () => {
            await Voice.stop();
          }).then((ran) => {
            if (!ran) finish(latestTextRef.current);
          }).catch(() => finish(latestTextRef.current));
          setTimeout(() => finish(latestTextRef.current), 1200);
        });
        finalizeRef.current = null;
      }
      readyRef.current = false;

      if (transcriptionSeqRef.current !== transcriptionSeq || cancelledRef.current) {
        return;
      }

      const trimmed = (text || '').trim();
      if (trimmed) {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
        opts?.onTranscript?.(trimmed);
        emitTerminal('completed');
      } else {
        emitTerminal('failed', 'empty_transcript');
        Alert.alert('未识别到语音', '请靠近麦克风重试');
      }
    } catch {
      readyRef.current = false;
      if (transcriptionSeqRef.current === transcriptionSeq && !cancelledRef.current) {
        emitTerminal('failed', 'transcription_failed');
        Alert.alert('语音识别失败', '请稍后再试');
      }
    } finally {
      if (transcriptionSeqRef.current === transcriptionSeq) {
        setIsTranscribing(false);
      }
      setPartialText('');
      await runVoiceSessionCommand(lease, releaseAudioSession);
      releaseVoiceSession(lease);
    }
  }, [opts, clearTimer, emitTerminal, recorder, releaseAudioSession]);

  const cancelRecording = useCallback(async () => {
    const lease = voiceLeaseRef.current;
    cancelledRef.current = true;
    transcriptionSeqRef.current += 1;
    setIsTranscribing(false);
    if (!readyRef.current) {
      startSeqRef.current += 1;
      clearTimer();
      setIsRecording(false);
      void runVoiceSessionCommand(lease, async () => {
        if (usingFallbackRef.current) {
          try { await recorder.stop(); } catch {}
        } else {
          try { await Voice.cancel(); } catch {}
        }
        await releaseAudioSession();
      }).finally(() => releaseVoiceSession(lease));
      emitTerminal('cancelled');
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
      return;
    }
    clearTimer();
    setIsRecording(false);
    setPartialText('');
    await runVoiceSessionCommand(lease, async () => {
      if (usingFallbackRef.current) {
        try { await recorder.stop(); } catch {}
      } else {
        try { await Voice.cancel(); } catch {}
      }
      await releaseAudioSession();
    });
    readyRef.current = false;
    releaseVoiceSession(lease);
    emitTerminal('cancelled');
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
  }, [clearTimer, emitTerminal, recorder, releaseAudioSession]);

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
