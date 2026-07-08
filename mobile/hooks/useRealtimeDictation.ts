import { useCallback, useEffect, useRef, useState } from 'react';
import Voice, {
  type SpeechErrorEvent,
  type SpeechResultsEvent,
} from '@react-native-voice/voice';
import { setAudioModeAsync } from 'expo-audio';

interface UseRealtimeDictationOptions {
  onTranscript: (text: string) => void;
  locale?: string;
}

export function useRealtimeDictation({
  onTranscript,
  locale = 'zh-CN',
}: UseRealtimeDictationOptions) {
  const [isDictating, setIsDictating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const activeRef = useRef(false);
  const latestTextRef = useRef('');
  const onTranscriptRef = useRef(onTranscript);

  useEffect(() => {
    onTranscriptRef.current = onTranscript;
  }, [onTranscript]);

  const setRecordingMode = useCallback(async (allowsRecording: boolean) => {
    await setAudioModeAsync({
      playsInSilentMode: true,
      shouldPlayInBackground: false,
      interruptionMode: 'duckOthers',
      allowsRecording,
    });
  }, []);

  const releaseRecordingMode = useCallback(async () => {
    try {
      await setRecordingMode(false);
    } catch (e) {
      if (__DEV__) console.warn('[useRealtimeDictation] release audio session failed:', e);
    }
  }, [setRecordingMode]);

  const emitTranscript = useCallback((rawText?: string) => {
    if (!activeRef.current) return;
    const text = rawText?.trim();
    if (!text) return;
    const previous = latestTextRef.current;
    const best = text.length >= previous.length ? text : previous;
    latestTextRef.current = best;
    onTranscriptRef.current(best);
  }, []);

  useEffect(() => {
    Voice.onSpeechPartialResults = (event: SpeechResultsEvent) => {
      emitTranscript(event.value?.[0]);
    };
    Voice.onSpeechResults = (event: SpeechResultsEvent) => {
      emitTranscript(event.value?.[0]);
    };
    Voice.onSpeechEnd = () => {
      if (!activeRef.current) return;
      activeRef.current = false;
      setIsDictating(false);
      void releaseRecordingMode();
    };
    Voice.onSpeechError = (event: SpeechErrorEvent) => {
      const message = event.error?.message || '语音识别失败';
      activeRef.current = false;
      setError(message);
      setIsDictating(false);
      void releaseRecordingMode();
    };

    return () => {
      activeRef.current = false;
      try {
        Voice.stop().catch(() => undefined);
      } catch {
        // Some native shims throw synchronously when no session exists.
      }
      Voice.destroy().then(() => Voice.removeAllListeners()).catch(() => undefined);
      void releaseRecordingMode();
    };
  }, [emitTranscript, releaseRecordingMode]);

  const startDictation = useCallback(async () => {
    if (activeRef.current) return;
    latestTextRef.current = '';
    setError(null);
    try {
      const available = await Voice.isAvailable();
      if (!available) {
        setError('当前设备不可用语音识别');
        return;
      }
      await setRecordingMode(true);
      activeRef.current = true;
      setIsDictating(true);
      await Voice.start(locale);
    } catch (e: any) {
      activeRef.current = false;
      setIsDictating(false);
      const message = e?.message || String(e);
      setError(message);
      await releaseRecordingMode();
    }
  }, [locale, releaseRecordingMode, setRecordingMode]);

  const stopDictation = useCallback(async () => {
    const wasActive = activeRef.current;
    activeRef.current = false;
    try {
      if (wasActive) {
        await Voice.stop();
      }
    } catch (e) {
      if (__DEV__) console.warn('[useRealtimeDictation] stop failed:', e);
    } finally {
      setIsDictating(false);
      await releaseRecordingMode();
    }
  }, [releaseRecordingMode]);

  return {
    isDictating,
    error,
    startDictation,
    stopDictation,
  };
}
