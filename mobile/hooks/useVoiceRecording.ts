import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert } from 'react-native';
import { Audio } from 'expo-av';
import * as Haptics from 'expo-haptics';
import { transcribeAudio } from '@/services/transcribe';

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

  const recordingRef = useRef<Audio.Recording | null>(null);
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
      if (recordingRef.current) {
        try { recordingRef.current.stopAndUnloadAsync(); } catch {}
        recordingRef.current = null;
      }
    };
  }, [clearTimer]);

  const startRecording = useCallback(async () => {
    try {
      readyRef.current = false;

      // 清理残留的录音对象
      if (recordingRef.current) {
        try { await recordingRef.current.stopAndUnloadAsync(); } catch {}
        recordingRef.current = null;
      }

      const perm = await Audio.requestPermissionsAsync();
      if (!perm.granted) {
        Alert.alert('需要麦克风权限', '请在 iPhone 设置 → HealthPilot → 麦克风 中开启权限');
        return;
      }

      await Audio.setAudioModeAsync({
        allowsRecordingIOS: true,
        playsInSilentModeIOS: true,
      });

      const { recording } = await Audio.Recording.createAsync(
        Audio.RecordingOptionsPresets.HIGH_QUALITY,
      );
      recordingRef.current = recording;
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
      // 如果仍然冲突，强制重置音频系统
      try { await Audio.setAudioModeAsync({ allowsRecordingIOS: false }); } catch {}
      setIsRecording(false);
      clearTimer();
      const msg = err?.message || String(err);
      Alert.alert('录音启动失败', msg);
    }
  }, [clearTimer]);

  const stopAndTranscribe = useCallback(async () => {
    if (!recordingRef.current || !readyRef.current) return;
    clearTimer();
    setIsRecording(false);

    if (cancelledRef.current) {
      try { await recordingRef.current.stopAndUnloadAsync(); } catch {}
      recordingRef.current = null;
      return;
    }

    setIsTranscribing(true);
    try {
      const uri = recordingRef.current.getURI();
      await recordingRef.current.stopAndUnloadAsync();
      recordingRef.current = null;

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
  }, [opts, clearTimer]);

  const cancelRecording = useCallback(async () => {
    cancelledRef.current = true;
    clearTimer();
    setIsRecording(false);
    if (recordingRef.current) {
      try { await recordingRef.current.stopAndUnloadAsync(); } catch {}
      recordingRef.current = null;
    }
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
  }, [clearTimer]);

  return {
    isRecording,
    isTranscribing,
    durationMs,
    startRecording,
    stopAndTranscribe,
    cancelRecording,
  };
}
