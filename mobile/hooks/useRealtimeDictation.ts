import { useCallback, useEffect, useRef, useState } from 'react';
import Voice, {
  type SpeechErrorEvent,
  type SpeechResultsEvent,
} from '@react-native-voice/voice';
import { setAudioModeAsync } from 'expo-audio';
import { durationBucket, emitClientEvent } from '../services/clientEvents';

interface UseRealtimeDictationOptions {
  onTranscript: (text: string) => void;
  onEnd?: () => void;
  onError?: (message: string) => void;
  locale?: string;
}

const FINAL_RESULT_GRACE_MS = 750;

export function useRealtimeDictation({
  onTranscript,
  onEnd,
  onError,
  locale = 'zh-CN',
}: UseRealtimeDictationOptions) {
  const [isDictating, setIsDictating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const activeRef = useRef(false);
  const acceptingFinalResultsRef = useRef(false);
  const manualStopRef = useRef(false);
  const finalResultFinishRef = useRef<(() => void) | null>(null);
  const finalResultPromiseRef = useRef<Promise<void> | null>(null);
  const latestTextRef = useRef('');
  const sessionStartedAtRef = useRef(0);
  const terminalSentRef = useRef(false);
  const startGenerationRef = useRef(0);
  const startingRef = useRef(false);
  const onTranscriptRef = useRef(onTranscript);
  const onEndRef = useRef(onEnd);
  const onErrorRef = useRef(onError);

  const emitTerminal = useCallback((
    phase: 'completed' | 'failed' | 'cancelled',
    errorCode?: string,
  ) => {
    if (!sessionStartedAtRef.current || terminalSentRef.current) return;
    terminalSentRef.current = true;
    void emitClientEvent('voice_input_terminal', {
      phase,
      duration_bucket: durationBucket(sessionStartedAtRef.current),
      action_type: 'dictation',
      ...(errorCode ? { error_code: errorCode } : {}),
    });
  }, []);

  useEffect(() => {
    onTranscriptRef.current = onTranscript;
    onEndRef.current = onEnd;
    onErrorRef.current = onError;
  }, [onEnd, onError, onTranscript]);

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

  const waitForFinalResult = useCallback((): Promise<void> => {
    if (finalResultPromiseRef.current) return finalResultPromiseRef.current;
    let timer: ReturnType<typeof setTimeout>;
    let finish!: () => void;
    const promise = new Promise<void>((resolve) => {
      let settled = false;
      finish = () => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        if (finalResultFinishRef.current === finish) finalResultFinishRef.current = null;
        resolve();
      };
      timer = setTimeout(finish, FINAL_RESULT_GRACE_MS);
      finalResultFinishRef.current = finish;
    });
    finalResultPromiseRef.current = promise;
    void promise.then(() => {
      if (finalResultPromiseRef.current === promise) finalResultPromiseRef.current = null;
    });
    return promise;
  }, []);

  const emitTranscript = useCallback((rawText?: string, final = false) => {
    if (!activeRef.current && !acceptingFinalResultsRef.current) return;
    const text = rawText?.trim();
    if (text) {
      const previous = latestTextRef.current;
      const best = final ? text : (text.length >= previous.length ? text : previous);
      latestTextRef.current = best;
      onTranscriptRef.current(best);
    }
    if (final) finalResultFinishRef.current?.();
  }, []);

  useEffect(() => {
    Voice.onSpeechPartialResults = (event: SpeechResultsEvent) => {
      emitTranscript(event.value?.[0]);
    };
    Voice.onSpeechResults = (event: SpeechResultsEvent) => {
      emitTranscript(event.value?.[0], true);
    };
    Voice.onSpeechEnd = () => {
      if (!activeRef.current) return;
      activeRef.current = false;
      setIsDictating(false);
      acceptingFinalResultsRef.current = true;
      if (manualStopRef.current) return;
      void waitForFinalResult().finally(async () => {
        if (manualStopRef.current) return;
        acceptingFinalResultsRef.current = false;
        emitTerminal('completed');
        await releaseRecordingMode();
        onEndRef.current?.();
      });
    };
    Voice.onSpeechError = (event: SpeechErrorEvent) => {
      if (!activeRef.current && !acceptingFinalResultsRef.current) return;
      const message = event.error?.message || '语音识别失败';
      activeRef.current = false;
      acceptingFinalResultsRef.current = false;
      finalResultFinishRef.current?.();
      setError(message);
      setIsDictating(false);
      emitTerminal('failed', 'speech_recognition_failed');
      void releaseRecordingMode().finally(() => onErrorRef.current?.(message));
    };

    return () => {
      const wasStarting = startingRef.current;
      startGenerationRef.current += 1;
      startingRef.current = false;
      if (activeRef.current || wasStarting) emitTerminal('cancelled', 'component_unmounted');
      activeRef.current = false;
      acceptingFinalResultsRef.current = false;
      manualStopRef.current = false;
      finalResultFinishRef.current?.();
      try {
        Voice.stop().catch(() => undefined);
      } catch {
        // Some native shims throw synchronously when no session exists.
      }
      Voice.destroy().then(() => Voice.removeAllListeners()).catch(() => undefined);
      void releaseRecordingMode();
    };
  }, [emitTerminal, emitTranscript, releaseRecordingMode, waitForFinalResult]);

  const startDictation = useCallback(async () => {
    if (activeRef.current || startingRef.current) return false;
    const generation = startGenerationRef.current + 1;
    startGenerationRef.current = generation;
    startingRef.current = true;
    sessionStartedAtRef.current = Date.now();
    terminalSentRef.current = false;
    latestTextRef.current = '';
    acceptingFinalResultsRef.current = false;
    manualStopRef.current = false;
    setError(null);
    try {
      const available = await Voice.isAvailable();
      if (generation !== startGenerationRef.current) {
        await releaseRecordingMode();
        return false;
      }
      if (!available) {
        const message = '当前设备不可用语音识别';
        setError(message);
        emitTerminal('failed', 'speech_recognition_unavailable');
        onErrorRef.current?.(message);
        return false;
      }
      await setRecordingMode(true);
      if (generation !== startGenerationRef.current) {
        await releaseRecordingMode();
        return false;
      }
      activeRef.current = true;
      setIsDictating(true);
      await Voice.start(locale);
      if (generation !== startGenerationRef.current) {
        try {
          await Voice.stop();
        } catch {
          // Cancellation already owns the user-visible terminal state.
        }
        activeRef.current = false;
        setIsDictating(false);
        await releaseRecordingMode();
        return false;
      }
      return true;
    } catch (e: any) {
      activeRef.current = false;
      setIsDictating(false);
      if (generation !== startGenerationRef.current) {
        await releaseRecordingMode();
        return false;
      }
      const message = e?.message || String(e);
      setError(message);
      await releaseRecordingMode();
      emitTerminal('failed', 'speech_recognition_start_failed');
      onErrorRef.current?.(message);
      return false;
    } finally {
      if (generation === startGenerationRef.current) {
        startingRef.current = false;
      }
    }
  }, [emitTerminal, locale, releaseRecordingMode, setRecordingMode]);

  const stopDictation = useCallback(async (): Promise<string> => {
    const wasStarting = startingRef.current;
    if (wasStarting) {
      startGenerationRef.current += 1;
      startingRef.current = false;
    }
    const wasActive = activeRef.current;
    const wasAwaitingFinal = acceptingFinalResultsRef.current;
    let stopFailed = false;
    let finalResultPromise: Promise<void> | null = null;
    try {
      if (wasActive || wasAwaitingFinal) {
        manualStopRef.current = true;
        acceptingFinalResultsRef.current = true;
        finalResultPromise = waitForFinalResult();
        if (wasActive) await Voice.stop();
        await finalResultPromise;
      }
    } catch (e) {
      stopFailed = true;
      if (__DEV__) console.warn('[useRealtimeDictation] stop failed:', e);
    } finally {
      finalResultFinishRef.current?.();
      activeRef.current = false;
      acceptingFinalResultsRef.current = false;
      manualStopRef.current = false;
      setIsDictating(false);
      await releaseRecordingMode();
      if (wasStarting) {
        emitTerminal('cancelled', 'start_cancelled');
      } else if (wasActive || wasAwaitingFinal) {
        emitTerminal(
          stopFailed ? 'failed' : 'completed',
          stopFailed ? 'speech_recognition_stop_failed' : undefined,
        );
      }
    }
    return latestTextRef.current;
  }, [emitTerminal, releaseRecordingMode, waitForFinalResult]);

  const cancelDictation = useCallback(async () => {
    const wasStarting = startingRef.current;
    if (wasStarting) {
      startGenerationRef.current += 1;
      startingRef.current = false;
    }
    const wasActive = activeRef.current;
    activeRef.current = false;
    acceptingFinalResultsRef.current = false;
    manualStopRef.current = false;
    finalResultFinishRef.current?.();
    try {
      if (wasActive) {
        await Voice.cancel();
      }
    } catch (e) {
      if (__DEV__) console.warn('[useRealtimeDictation] cancel failed:', e);
    } finally {
      latestTextRef.current = '';
      setIsDictating(false);
      await releaseRecordingMode();
      if (wasStarting || wasActive) {
        emitTerminal('cancelled', wasStarting ? 'start_cancelled' : undefined);
      }
    }
  }, [emitTerminal, releaseRecordingMode]);

  return {
    isDictating,
    error,
    startDictation,
    stopDictation,
    cancelDictation,
  };
}
