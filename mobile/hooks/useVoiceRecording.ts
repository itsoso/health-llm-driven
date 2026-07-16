import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert } from 'react-native';
import {
  useAudioRecorder,
  RecordingPresets,
  setAudioModeAsync,
  requestRecordingPermissionsAsync,
} from 'expo-audio';
import * as Haptics from 'expo-haptics';
import { transcribeAudioDetailed, type TranscribeAudioResult } from '../services/transcribe';
import { durationBucket, emitClientEvent } from '../services/clientEvents';

export interface VoiceRecordingState {
  isRecording: boolean;
  isTranscribing: boolean;
  durationMs: number;
}

export function useVoiceRecording(opts?: {
  onTranscript?: (text: string, result?: TranscribeAudioResult) => void;
}) {
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [durationMs, setDurationMs] = useState(0);

  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const cancelledRef = useRef(false);
  const readyRef = useRef(false);
  const startSeqRef = useRef(0);
  const transcriptionSeqRef = useRef(0);
  const sessionStartedAtRef = useRef(0);
  const terminalSentRef = useRef(false);

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

  const emitAsrTerminal = useCallback((
    phase: 'completed' | 'failed',
    startedAt: number,
    result?: TranscribeAudioResult,
    errorCode?: string,
  ) => {
    void emitClientEvent('voice_asr_terminal', {
      phase,
      duration_bucket: durationBucket(
        startedAt,
        result?.durationMs !== undefined ? startedAt + result.durationMs : Date.now(),
      ),
      action_type: 'hold',
      provider: result?.provider || 'cloud_asr',
      ...(result?.confidence ? { confidence: result.confidence } : {}),
      empty: result?.empty ?? true,
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
      const shouldStopRecorder = readyRef.current;
      readyRef.current = false;
      if (shouldStopRecorder) {
        try {
          void Promise.resolve(recorder.stop()).catch((error) => {
            if (__DEV__) console.warn('[useVoiceRecording] unmount stop failed:', error);
          });
        } catch (error) {
          if (__DEV__) console.warn('[useVoiceRecording] unmount stop failed:', error);
        }
      }
      // 卸载时若还占着录音 session, 放回来 (不阻塞卸载, fire-and-forget)。
      void setAudioModeAsync({ allowsRecording: false }).catch(() => {});
    };
  }, [clearTimer, emitTerminal, recorder]);

  const startRecording = useCallback(async () => {
    sessionStartedAtRef.current = Date.now();
    terminalSentRef.current = false;
    transcriptionSeqRef.current += 1;
    const seq = startSeqRef.current + 1;
    startSeqRef.current = seq;
    const isCurrentStart = () => startSeqRef.current === seq;
    try {
      readyRef.current = false;

      const perm = await requestRecordingPermissionsAsync();
      if (!isCurrentStart()) {
        await releaseAudioSession();
        return false;
      }
      if (!perm.granted) {
        emitTerminal('failed', 'microphone_permission_denied');
        Alert.alert('需要麦克风权限', '请在 iPhone 设置 → 小巴 → 麦克风 中开启权限');
        return false;
      }

      await setAudioModeAsync({
        allowsRecording: true,
        playsInSilentMode: true,
      });
      if (!isCurrentStart()) {
        await releaseAudioSession();
        return false;
      }

      await recorder.prepareToRecordAsync();
      if (!isCurrentStart()) {
        await releaseAudioSession();
        return false;
      }
      recorder.record();

      cancelledRef.current = false;
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
      try { await setAudioModeAsync({ allowsRecording: false }); } catch {}
      readyRef.current = false;
      setIsRecording(false);
      clearTimer();
      const msg = err?.message || String(err);
      emitTerminal('failed', 'recording_start_failed');
      Alert.alert('录音启动失败', msg);
      return false;
    }
  }, [clearTimer, emitTerminal, recorder, releaseAudioSession]);

  const stopAndTranscribe = useCallback(async () => {
    if (!readyRef.current) {
      startSeqRef.current += 1;
      clearTimer();
      setIsRecording(false);
      await releaseAudioSession();
      emitTerminal('cancelled', 'released_before_ready');
      return;
    }
    clearTimer();
    setIsRecording(false);

    if (cancelledRef.current) {
      try { await recorder.stop(); } catch {}
      readyRef.current = false;
      await releaseAudioSession();  // 释放录音 session, 否则语音后键盘弹不出。
      emitTerminal('cancelled');
      return;
    }

    const transcriptionSeq = transcriptionSeqRef.current + 1;
    transcriptionSeqRef.current = transcriptionSeq;
    setIsTranscribing(true);
    try {
      try {
        await recorder.stop();
      } finally {
        readyRef.current = false;
        // 原生 stop 失败也必须释放 session, 否则下一次键盘和录音都会被占用。
        await releaseAudioSession();
      }
      const uri = recorder.uri;

      if (!uri) {
        setIsTranscribing(false);
        emitTerminal('failed', 'recording_uri_missing');
        return;
      }

      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      const asrStartedAt = Date.now();
      const result = await transcribeAudioDetailed(uri);
      const text = result.text;

      if (transcriptionSeqRef.current !== transcriptionSeq || cancelledRef.current) {
        return;
      }

      if (text && opts?.onTranscript) {
        opts.onTranscript(text, result);
        emitAsrTerminal('completed', asrStartedAt, result);
        emitTerminal('completed');
      } else if (text) {
        emitAsrTerminal('completed', asrStartedAt, result);
        emitTerminal('completed');
      } else if (!text) {
        emitAsrTerminal('failed', asrStartedAt, result, 'empty_transcript');
        emitTerminal('failed', 'empty_transcript');
        Alert.alert('未识别到语音', '请靠近麦克风重试');
      }
    } catch {
      readyRef.current = false;
      if (transcriptionSeqRef.current === transcriptionSeq && !cancelledRef.current) {
        emitAsrTerminal('failed', Date.now(), undefined, 'transcription_failed');
        emitTerminal('failed', 'transcription_failed');
        Alert.alert('语音识别失败', '请稍后再试');
      }
    } finally {
      if (transcriptionSeqRef.current === transcriptionSeq) {
        setIsTranscribing(false);
      }
    }
  }, [opts, clearTimer, emitAsrTerminal, emitTerminal, recorder, releaseAudioSession]);

  const cancelRecording = useCallback(async () => {
    cancelledRef.current = true;
    transcriptionSeqRef.current += 1;
    setIsTranscribing(false);
    if (!readyRef.current) {
      startSeqRef.current += 1;
      clearTimer();
      setIsRecording(false);
      await releaseAudioSession();
      emitTerminal('cancelled');
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
      return;
    }
    clearTimer();
    setIsRecording(false);
    try { await recorder.stop(); } catch {}
    readyRef.current = false;
    await releaseAudioSession();  // 取消同样要释放, 否则语音后键盘弹不出。
    emitTerminal('cancelled');
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
  }, [clearTimer, emitTerminal, recorder, releaseAudioSession]);

  return {
    isRecording,
    isTranscribing,
    durationMs,
    startRecording,
    stopAndTranscribe,
    cancelRecording,
  };
}
