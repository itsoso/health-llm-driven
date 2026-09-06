import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert } from 'react-native';
import {
  useAudioRecorder,
  RecordingPresets,
  setAudioModeAsync,
  setIsAudioActiveAsync,
  requestRecordingPermissionsAsync,
} from 'expo-audio';
import * as Haptics from 'expo-haptics';
import { transcribeAudioDetailed, type TranscribeAudioResult } from '../services/transcribe';
import { durationBucket, emitClientEvent } from '../services/clientEvents';
import { ensureAIConsent } from '../services/aiConsent';
import { subscribeAIConsentInvalidation } from '../services/aiConsentState';

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
  const audioSessionOwnedRef = useRef(false);

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

  // doNotMix 会暂停其他 App。结束时必须 deactivate 并通知 iOS, 外部音频才会恢复。
  const releaseAudioSession = useCallback(async () => {
    if (!audioSessionOwnedRef.current) return;
    let released = true;
    try {
      await setIsAudioActiveAsync(false);
    } catch (error) {
      released = false;
      if (__DEV__) console.warn('[useVoiceRecording] deactivate audio session failed:', error);
    }
    try {
      await setAudioModeAsync({
        allowsRecording: false,
        playsInSilentMode: false,
        shouldPlayInBackground: false,
        interruptionMode: 'mixWithOthers',
      });
    } catch (error) {
      released = false;
      if (__DEV__) console.warn('[useVoiceRecording] restore audio mode failed:', error);
    }
    if (released) audioSessionOwnedRef.current = false;
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
      void (async () => {
        if (shouldStopRecorder) {
          try {
            await recorder.stop();
          } catch (error) {
            if (__DEV__) console.warn('[useVoiceRecording] unmount stop failed:', error);
          }
        }
        await releaseAudioSession();
      })();
    };
  }, [clearTimer, emitTerminal, recorder, releaseAudioSession]);

  const startRecording = useCallback(async () => {
    sessionStartedAtRef.current = Date.now();
    terminalSentRef.current = false;
    transcriptionSeqRef.current += 1;
    const seq = startSeqRef.current + 1;
    startSeqRef.current = seq;
    const isCurrentStart = () => startSeqRef.current === seq;
    try {
      readyRef.current = false;

      if (!await ensureAIConsent() || !isCurrentStart()) return false;

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

      audioSessionOwnedRef.current = true;
      await setAudioModeAsync({
        allowsRecording: true,
        playsInSilentMode: true,
        shouldPlayInBackground: false,
        interruptionMode: 'doNotMix',
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
      await releaseAudioSession();
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

  useEffect(() => subscribeAIConsentInvalidation(() => {
    if (sessionStartedAtRef.current) void cancelRecording();
  }), [cancelRecording]);

  return {
    isRecording,
    isTranscribing,
    durationMs,
    startRecording,
    stopAndTranscribe,
    cancelRecording,
  };
}
