import { useCallback, useEffect, useRef, useState } from 'react';
import { durationBucket, emitClientEvent } from '../services/clientEvents';
import {
  createCloudRealtimeAsrSession,
  type RealtimeAsrSession,
} from '../services/cloudRealtimeAsr';
import { estimateVoiceDraftConfidence } from '../services/voiceDraft';
import type { TranscribeAudioResult } from '../services/transcribe';

interface UseRealtimeDictationOptions {
  onTranscript: (text: string, result?: TranscribeAudioResult) => void;
  onEnd?: () => void;
  onError?: (message: string) => void;
  locale?: string;
}

function emptyCloudResult(text: string, startedAt: number): TranscribeAudioResult {
  const clean = text.trim();
  return {
    text: clean,
    provider: 'dashscope_qwen_asr_realtime',
    model: 'qwen3-asr-flash-realtime',
    durationMs: Math.max(0, Date.now() - startedAt),
    confidence: estimateVoiceDraftConfidence(clean),
    empty: clean.length === 0,
  };
}

/**
 * Mobile composer ASR.
 *
 * There is one recognition provider for this path: Alibaba Cloud Qwen
 * realtime ASR. The phone only captures 16 kHz PCM and renders cloud partial
 * results; finalization is committed once and waits for the cloud `done`
 * event, so provider switching cannot overwrite a user's edited draft.
 */
export function useRealtimeDictation({
  onTranscript,
  onEnd,
  onError,
}: UseRealtimeDictationOptions) {
  const [isDictating, setIsDictating] = useState(false);
  const [durationMs, setDurationMs] = useState(0);
  const [audioLevel, setAudioLevel] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const activeRef = useRef(false);
  const acceptingFinalResultsRef = useRef(false);
  const startingRef = useRef(false);
  const startGenerationRef = useRef(0);
  const sessionRef = useRef<RealtimeAsrSession | null>(null);
  const stopPromiseRef = useRef<Promise<string> | null>(null);
  const latestTextRef = useRef('');
  const latestResultRef = useRef<TranscribeAudioResult | undefined>(undefined);
  const sessionStartedAtRef = useRef(0);
  const terminalSentRef = useRef(false);
  const asrTerminalSentRef = useRef(false);
  const onTranscriptRef = useRef(onTranscript);
  const onEndRef = useRef(onEnd);
  const onErrorRef = useRef(onError);

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
    const result = latestResultRef.current || emptyCloudResult(text, sessionStartedAtRef.current);
    void emitClientEvent('voice_asr_terminal', {
      phase,
      duration_bucket: durationBucket(sessionStartedAtRef.current),
      action_type: 'dictation',
      provider: result.provider,
      model: result.model,
      confidence: result.confidence,
      empty: result.empty,
      ...(errorCode ? { error_code: errorCode } : {}),
    });
  }, []);

  const acceptCloudTranscript = useCallback((
    rawText: string,
    result?: TranscribeAudioResult,
  ) => {
    if (!activeRef.current && !acceptingFinalResultsRef.current) return;
    const text = rawText.trim();
    if (!text) return;

    // Qwen partials are cumulative, but an old websocket frame can arrive
    // after a newer one. Keep the longest partial and always let stop() apply
    // the authoritative final result below.
    const previous = latestTextRef.current;
    const best = text.length >= previous.length ? text : previous;
    latestTextRef.current = best;
    latestResultRef.current = result
      ? { ...result, text: best, empty: best.length === 0 }
      : emptyCloudResult(best, sessionStartedAtRef.current);
    onTranscriptRef.current(best, latestResultRef.current);
  }, []);

  const disposeSession = useCallback(async (session: RealtimeAsrSession | null) => {
    if (!session) return;
    try {
      await session.cancel();
    } catch (e) {
      if (__DEV__) console.warn('[useRealtimeDictation] cloud session cleanup failed:', e);
    }
  }, []);

  useEffect(() => {
    return () => {
      const session = sessionRef.current;
      const wasActive = activeRef.current || startingRef.current || Boolean(stopPromiseRef.current);
      startGenerationRef.current += 1;
      activeRef.current = false;
      acceptingFinalResultsRef.current = false;
      startingRef.current = false;
      sessionRef.current = null;
      if (wasActive) emitTerminal('cancelled', 'component_unmounted');
      void disposeSession(session);
    };
  }, [disposeSession, emitTerminal]);

  const startDictation = useCallback(async (): Promise<boolean> => {
    if (activeRef.current || startingRef.current || stopPromiseRef.current) return false;
    const generation = startGenerationRef.current + 1;
    startGenerationRef.current = generation;
    startingRef.current = true;
    sessionStartedAtRef.current = Date.now();
    terminalSentRef.current = false;
    asrTerminalSentRef.current = false;
    latestTextRef.current = '';
    latestResultRef.current = undefined;
    acceptingFinalResultsRef.current = false;
    setDurationMs(0);
    setAudioLevel(0);
    setError(null);

    const session = createCloudRealtimeAsrSession({
      onTranscript: acceptCloudTranscript,
      onLevel: setAudioLevel,
    });
    sessionRef.current = session;

    try {
      const started = await session.start();
      if (generation !== startGenerationRef.current || !started) {
        await disposeSession(session);
        if (sessionRef.current === session) sessionRef.current = null;
        return false;
      }
      activeRef.current = true;
      setIsDictating(true);
      return true;
    } catch (e: any) {
      await disposeSession(session);
      if (sessionRef.current === session) sessionRef.current = null;
      if (generation !== startGenerationRef.current) return false;
      const message = e?.message || '阿里云实时语音识别失败，请稍后重试';
      setError(message);
      emitAsrTerminal('failed', '', 'cloud_asr_start_failed');
      emitTerminal('failed', 'cloud_asr_start_failed');
      onErrorRef.current?.(message);
      return false;
    } finally {
      if (generation === startGenerationRef.current) startingRef.current = false;
    }
  }, [acceptCloudTranscript, disposeSession, emitAsrTerminal, emitTerminal]);

  const stopDictation = useCallback((): Promise<string> => {
    if (stopPromiseRef.current) return stopPromiseRef.current;
    const session = sessionRef.current;
    if (!session || !activeRef.current) return Promise.resolve(latestTextRef.current);

    activeRef.current = false;
    acceptingFinalResultsRef.current = true;
    const promise = (async () => {
      try {
        const finalResult = await session.stop();
        const finalText = finalResult.text.trim();
        if (finalText) {
          latestTextRef.current = finalText;
          latestResultRef.current = finalResult;
          onTranscriptRef.current(finalText, finalResult);
        }
        emitAsrTerminal(
          finalText ? 'completed' : 'failed',
          finalText,
          finalText ? undefined : 'empty_transcript',
        );
        emitTerminal('completed');
        onEndRef.current?.();
        return finalText;
      } catch (e: any) {
        const message = e?.message || '阿里云实时语音识别失败，请稍后重试';
        setError(message);
        emitAsrTerminal('failed', latestTextRef.current, 'cloud_asr_stop_failed');
        emitTerminal('failed', 'cloud_asr_stop_failed');
        onErrorRef.current?.(message);
        await disposeSession(session);
        return latestTextRef.current;
      } finally {
        acceptingFinalResultsRef.current = false;
        sessionRef.current = null;
        setIsDictating(false);
        stopPromiseRef.current = null;
      }
    })();
    stopPromiseRef.current = promise;
    return promise;
  }, [disposeSession, emitAsrTerminal, emitTerminal]);

  const cancelDictation = useCallback(async () => {
    const session = sessionRef.current;
    const wasActive = activeRef.current || startingRef.current || Boolean(stopPromiseRef.current);
    startGenerationRef.current += 1;
    activeRef.current = false;
    acceptingFinalResultsRef.current = false;
    startingRef.current = false;
    sessionRef.current = null;
    await disposeSession(session);
    latestTextRef.current = '';
    latestResultRef.current = undefined;
    stopPromiseRef.current = null;
    setIsDictating(false);
    setAudioLevel(0);
    if (wasActive) emitTerminal('cancelled');
  }, [disposeSession, emitTerminal]);

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
