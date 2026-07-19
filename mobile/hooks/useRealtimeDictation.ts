import { useCallback, useEffect, useRef, useState } from 'react';
import Voice, {
  type SpeechErrorEvent,
  type SpeechRecognizedEvent,
  type SpeechResultsEvent,
} from '@react-native-voice/voice';
import { setAudioModeAsync } from 'expo-audio';
import { durationBucket, emitClientEvent } from '../services/clientEvents';
import { estimateVoiceDraftConfidence } from '../services/voiceDraft';
import {
  bindVoiceEventHandlers,
  isVoiceEventHandlerOwner,
  releaseVoiceEventHandlers,
  type VoiceEventLease,
} from '../services/voiceEventRouter';
import type { TranscribeAudioResult } from '../services/transcribe';

interface UseRealtimeDictationOptions {
  onTranscript: (text: string, result?: TranscribeAudioResult) => void;
  onEnd?: () => void;
  onError?: (message: string) => void;
  locale?: string;
}

const FINAL_RESULT_GRACE_MS = 750;

function nativeResult(text: string, startedAt: number): TranscribeAudioResult {
  const clean = text.trim();
  return {
    text: clean,
    provider: 'native_realtime',
    model: 'apple_speech',
    durationMs: Math.max(0, Date.now() - startedAt),
    confidence: estimateVoiceDraftConfidence(clean),
    empty: clean.length === 0,
  };
}

/**
 * Mobile composer ASR.
 *
 * The primary path is iOS Speech.framework through @react-native-voice/voice:
 * partial results are available while speaking and releasing the control only
 * waits for the native final marker. The cloud PCM/WebSocket path is kept as a
 * separate service for experiments and fallback work, but is intentionally not
 * on the hot path because its network round-trip makes short push-to-talk
 * phrases lose their final syllables.
 */
export function useRealtimeDictation({
  onTranscript,
  onEnd,
  onError,
  locale = 'zh-CN',
}: UseRealtimeDictationOptions) {
  const [isDictating, setIsDictating] = useState(false);
  const [durationMs, setDurationMs] = useState(0);
  const [audioLevel, setAudioLevel] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const activeRef = useRef(false);
  const acceptingFinalResultsRef = useRef(false);
  const manualStopRef = useRef(false);
  const finalResultFinishRef = useRef<(() => void) | null>(null);
  const finalResultPromiseRef = useRef<Promise<void> | null>(null);
  const latestTextRef = useRef('');
  const pendingResultRef = useRef('');
  const sessionStartedAtRef = useRef(0);
  const terminalSentRef = useRef(false);
  const asrTerminalSentRef = useRef(false);
  const startGenerationRef = useRef(0);
  const startingRef = useRef(false);
  const onTranscriptRef = useRef(onTranscript);
  const onEndRef = useRef(onEnd);
  const onErrorRef = useRef(onError);
  const voiceEventLeaseRef = useRef<VoiceEventLease | null>(null);

  useEffect(() => {
    onTranscriptRef.current = onTranscript;
    onEndRef.current = onEnd;
    onErrorRef.current = onError;
  }, [onEnd, onError, onTranscript]);

  useEffect(() => {
    if (!isDictating) return;
    const timer = setInterval(() => {
      setDurationMs(Math.max(0, Date.now() - sessionStartedAtRef.current));
    }, 200);
    return () => clearInterval(timer);
  }, [isDictating]);

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

  const emitAsrTerminal = useCallback((
    phase: 'completed' | 'failed',
    text: string,
    errorCode?: string,
  ) => {
    if (!sessionStartedAtRef.current || asrTerminalSentRef.current) return;
    asrTerminalSentRef.current = true;
    const result = nativeResult(text, sessionStartedAtRef.current);
    void emitClientEvent('voice_asr_terminal', {
      phase,
      duration_bucket: durationBucket(sessionStartedAtRef.current),
      action_type: 'dictation',
      provider: result.provider,
      confidence: result.confidence,
      empty: result.empty,
      ...(errorCode ? { error_code: errorCode } : {}),
    });
  }, []);

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

  const emitTranscript = useCallback((
    rawText?: string,
    final = false,
    authoritative = final,
  ) => {
    if (!activeRef.current && !acceptingFinalResultsRef.current) return;
    const text = rawText?.trim();
    if (text) {
      const previous = latestTextRef.current;
      const best = authoritative ? text : (text.length >= previous.length ? text : previous);
      latestTextRef.current = best;
      onTranscriptRef.current(best, nativeResult(best, sessionStartedAtRef.current));
    }
    if (final) finalResultFinishRef.current?.();
  }, []);

  const releaseEventLease = useCallback(() => {
    releaseVoiceEventHandlers(voiceEventLeaseRef.current);
    voiceEventLeaseRef.current = null;
  }, []);

  const bindEventLease = useCallback(() => {
    releaseEventLease();
    voiceEventLeaseRef.current = bindVoiceEventHandlers({
      onSpeechPartialResults: (event: SpeechResultsEvent) => {
        emitTranscript(event.value?.[0]);
      },
      onSpeechResults: (event: SpeechResultsEvent) => {
        pendingResultRef.current = event.value?.[0]?.trim() || '';
        emitTranscript(pendingResultRef.current, false, true);
      },
      onSpeechRecognized: (event: SpeechRecognizedEvent) => {
        if (!event.isFinal) return;
        emitTranscript(pendingResultRef.current || latestTextRef.current, true, true);
      },
      onSpeechEnd: () => {
        if (!activeRef.current) return;
        activeRef.current = false;
        setIsDictating(false);
        acceptingFinalResultsRef.current = true;
        if (manualStopRef.current) return;
        void waitForFinalResult().finally(async () => {
          if (manualStopRef.current) return;
          acceptingFinalResultsRef.current = false;
          emitAsrTerminal(
            latestTextRef.current.trim() ? 'completed' : 'failed',
            latestTextRef.current,
            latestTextRef.current.trim() ? undefined : 'empty_transcript',
          );
          emitTerminal('completed');
          releaseEventLease();
          await releaseRecordingMode();
          onEndRef.current?.();
        });
      },
      onSpeechError: (event: SpeechErrorEvent) => {
        if (!activeRef.current && !acceptingFinalResultsRef.current) return;
        const message = event.error?.message || '语音识别失败';
        activeRef.current = false;
        acceptingFinalResultsRef.current = false;
        finalResultFinishRef.current?.();
        setError(message);
        setIsDictating(false);
        emitAsrTerminal('failed', latestTextRef.current, 'speech_recognition_failed');
        emitTerminal('failed', 'speech_recognition_failed');
        releaseEventLease();
        void releaseRecordingMode().finally(() => onErrorRef.current?.(message));
      },
    });
  }, [emitAsrTerminal, emitTerminal, emitTranscript, releaseEventLease, releaseRecordingMode, waitForFinalResult]);

  useEffect(() => {
    return () => {
      const wasStarting = startingRef.current;
      const ownsNativeSession = isVoiceEventHandlerOwner(voiceEventLeaseRef.current);
      startGenerationRef.current += 1;
      startingRef.current = false;
      if (activeRef.current || wasStarting) emitTerminal('cancelled', 'component_unmounted');
      activeRef.current = false;
      acceptingFinalResultsRef.current = false;
      manualStopRef.current = false;
      finalResultFinishRef.current?.();
      if (ownsNativeSession) {
        try {
          Voice.stop().catch(() => undefined);
        } catch {
          // Some native shims throw synchronously when no session exists.
        }
        Voice.destroy().catch(() => undefined);
      }
      releaseEventLease();
      void releaseRecordingMode();
    };
  }, [emitTerminal, releaseEventLease, releaseRecordingMode]);

  const startDictation = useCallback(async (): Promise<boolean> => {
    if (activeRef.current || startingRef.current) return false;
    const generation = startGenerationRef.current + 1;
    startGenerationRef.current = generation;
    startingRef.current = true;
    sessionStartedAtRef.current = Date.now();
    terminalSentRef.current = false;
    asrTerminalSentRef.current = false;
    latestTextRef.current = '';
    pendingResultRef.current = '';
    acceptingFinalResultsRef.current = false;
    manualStopRef.current = false;
    setDurationMs(0);
    setAudioLevel(0);
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
        emitAsrTerminal('failed', '', 'speech_recognition_unavailable');
        emitTerminal('failed', 'speech_recognition_unavailable');
        onErrorRef.current?.(message);
        return false;
      }
      await setRecordingMode(true);
      if (generation !== startGenerationRef.current) {
        await releaseRecordingMode();
        return false;
      }
      bindEventLease();
      activeRef.current = true;
      setIsDictating(true);
      await Voice.start(locale);
      if (generation !== startGenerationRef.current) {
        if (isVoiceEventHandlerOwner(voiceEventLeaseRef.current)) {
          try {
            await Voice.stop();
          } catch {
            // Cancellation already owns the user-visible terminal state.
          }
        }
        releaseEventLease();
        activeRef.current = false;
        setIsDictating(false);
        await releaseRecordingMode();
        return false;
      }
      return true;
    } catch (e: any) {
      releaseEventLease();
      activeRef.current = false;
      setIsDictating(false);
      if (generation !== startGenerationRef.current) {
        await releaseRecordingMode();
        return false;
      }
      const message = e?.message || String(e);
      setError(message);
      await releaseRecordingMode();
      emitAsrTerminal('failed', '', 'speech_recognition_start_failed');
      emitTerminal('failed', 'speech_recognition_start_failed');
      onErrorRef.current?.(message);
      return false;
    } finally {
      if (generation === startGenerationRef.current) startingRef.current = false;
    }
  }, [bindEventLease, emitAsrTerminal, emitTerminal, locale, releaseEventLease, releaseRecordingMode, setRecordingMode]);

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
      if (!wasStarting) releaseEventLease();
      await releaseRecordingMode();
      if (wasStarting) {
        emitTerminal('cancelled', 'start_cancelled');
      } else if (wasActive || wasAwaitingFinal) {
        emitAsrTerminal(
          stopFailed || !latestTextRef.current.trim() ? 'failed' : 'completed',
          latestTextRef.current,
          stopFailed ? 'speech_recognition_stop_failed' : (!latestTextRef.current.trim() ? 'empty_transcript' : undefined),
        );
        emitTerminal(
          stopFailed ? 'failed' : 'completed',
          stopFailed ? 'speech_recognition_stop_failed' : undefined,
        );
      }
    }
    return latestTextRef.current;
  }, [emitAsrTerminal, emitTerminal, releaseEventLease, releaseRecordingMode, waitForFinalResult]);

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
      if (wasActive) await Voice.cancel();
    } catch (e) {
      if (__DEV__) console.warn('[useRealtimeDictation] cancel failed:', e);
    } finally {
      latestTextRef.current = '';
      pendingResultRef.current = '';
      setIsDictating(false);
      if (!wasStarting) releaseEventLease();
      await releaseRecordingMode();
      if (wasStarting || wasActive) {
        emitTerminal('cancelled', wasStarting ? 'start_cancelled' : undefined);
      }
    }
  }, [emitTerminal, releaseEventLease, releaseRecordingMode]);

  return {
    isDictating,
    durationMs,
    audioLevel,
    error,
    startDictation,
    stopDictation,
    cancelDictation,
  };
}
