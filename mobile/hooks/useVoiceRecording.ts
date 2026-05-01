import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert } from 'react-native';
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
}

export function useVoiceRecording(opts?: {
  onTranscript?: (text: string) => void;
}) {
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [durationMs, setDurationMs] = useState(0);

  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const cancelledRef = useRef(false);
  const readyRef = useRef(false);

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
      try { recorder.stop(); } catch {}
    };
  }, [clearTimer, recorder]);

  const startRecording = useCallback(async () => {
    try {
      readyRef.current = false;

      const perm = await requestRecordingPermissionsAsync();
      if (!perm.granted) {
        Alert.alert('需要麦克风权限', '请在 iPhone 设置 → HealthPilot → 麦克风 中开启权限');
        return;
      }

      await setAudioModeAsync({
        allowsRecording: true,
        playsInSilentMode: true,
      });

      await recorder.prepareToRecordAsync();
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
    } catch (err: any) {
      try { await setAudioModeAsync({ allowsRecording: false }); } catch {}
      setIsRecording(false);
      clearTimer();
      const msg = err?.message || String(err);
      Alert.alert('录音启动失败', msg);
    }
  }, [clearTimer, recorder]);

  const stopAndTranscribe = useCallback(async () => {
    if (!readyRef.current) return;
    clearTimer();
    setIsRecording(false);

    if (cancelledRef.current) {
      try { await recorder.stop(); } catch {}
      return;
    }

    setIsTranscribing(true);
    try {
      await recorder.stop();
      const uri = recorder.uri;

      if (!uri) {
        setIsTranscribing(false);
        return;
      }

      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      const text = await transcribeAudio(uri);

      if (text && opts?.onTranscript) {
        opts.onTranscript(text);
      } else if (!text) {
        Alert.alert('未识别到语音', '请靠近麦克风重试');
      }
    } catch {
      Alert.alert('语音识别失败', '请稍后再试');
    } finally {
      setIsTranscribing(false);
    }
  }, [opts, clearTimer, recorder]);

  const cancelRecording = useCallback(async () => {
    cancelledRef.current = true;
    clearTimer();
    setIsRecording(false);
    try { await recorder.stop(); } catch {}
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
  }, [clearTimer, recorder]);

  return {
    isRecording,
    isTranscribing,
    durationMs,
    startRecording,
    stopAndTranscribe,
    cancelRecording,
  };
}
