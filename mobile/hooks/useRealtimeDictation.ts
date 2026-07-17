import { useCallback, useEffect, useRef, useState } from 'react';

import { durationBucket, emitClientEvent } from '../services/clientEvents';
import { createCloudRealtimeAsrSession } from '../services/cloudRealtimeAsr';
import type { TranscribeAudioResult } from '../services/transcribe';

interface UseRealtimeDictationOptions {
  onTranscript: (text: string, result?: TranscribeAudioResult) => void;
  onEnd?: () => void;
  onError?: (message: string) => void;
  locale?: string;
}

type CloudSession = ReturnType<typeof createCloudRealtimeAsrSession>;

export function useRealtimeDictation({
  onTranscript,
  onEnd,
  onError,
}: UseRealtimeDictationOptions) {
  const [isDictating, setIsDictating] = useState(false);
  const [durationMs, setDurationMs] = useState(0);
  const [audioLevel, setAudioLevel] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const sessionRef = useRef<CloudSession | null>(null);
  const startingRef = useRef(false);
  const stoppingRef = useRef(false);
  const mountedRef = useRef(true);
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
    result?: TranscribeAudioResult,
    errorCode?: string,
  ) => {
    if (!sessionStartedAtRef.current || asrTerminalSentRef.current) return;
    asrTerminalSentRef.current = true;
    void emitClientEvent('voice_asr_terminal', {
      phase,
      duration_bucket: durationBucket(
        sessionStartedAtRef.current,
        result?.durationMs !== undefined
          ? sessionStartedAtRef.current + result.durationMs
          : Date.now(),
      ),
      action_type: 'dictation',
      provider: result?.provider || 'cloud_asr',
      ...(result?.confidence ? { confidence: result.confidence } : {}),
      empty: result?.empty ?? true,
      ...(errorCode ? { error_code: errorCode } : {}),
    });
  }, []);

  const startDictation = useCallback(async (): Promise<boolean> => {
    if (startingRef.current || stoppingRef.current || sessionRef.current) return false;
    startingRef.current = true;
    sessionStartedAtRef.current = Date.now();
    terminalSentRef.current = false;
    asrTerminalSentRef.current = false;
    setDurationMs(0);
    setAudioLevel(0);
    setError(null);

    const session = createCloudRealtimeAsrSession({
      onTranscript: (text, result) => onTranscriptRef.current(text, result),
      onLevel: level => {
        if (mountedRef.current) setAudioLevel(Math.max(0, Math.min(1, level)));
      },
    });
    sessionRef.current = session;
    try {
      const started = await session.start();
      if (sessionRef.current !== session) return false;
      if (!started) {
        sessionRef.current = null;
        emitTerminal('failed', 'realtime_session_not_started');
        return false;
      }
      if (mountedRef.current) setIsDictating(true);
      return true;
    } catch (caught: any) {
      if (sessionRef.current !== session) return false;
      sessionRef.current = null;
      const message = caught?.message || '云端实时语音识别启动失败';
      if (mountedRef.current) {
        setIsDictating(false);
        setError(message);
      }
      emitTerminal('failed', 'realtime_session_start_failed');
      onErrorRef.current?.(message);
      return false;
    } finally {
      startingRef.current = false;
    }
  }, [emitTerminal]);

  const stopDictation = useCallback(async (): Promise<string> => {
    const session = sessionRef.current;
    if (!session || stoppingRef.current) return '';
    stoppingRef.current = true;
    if (mountedRef.current) setIsDictating(false);
    try {
      const result = await session.stop();
      if (sessionRef.current !== session) return '';
      sessionRef.current = null;
      const text = result.text.trim();
      if (!text) {
        emitAsrTerminal('failed', result, 'empty_transcript');
        emitTerminal('failed', 'empty_transcript');
        return '';
      }
      emitAsrTerminal('completed', result);
      emitTerminal('completed');
      onEndRef.current?.();
      return text;
    } catch (caught: any) {
      if (sessionRef.current !== session) return '';
      sessionRef.current = null;
      const message = caught?.message || '云端实时语音识别失败';
      if (mountedRef.current) setError(message);
      emitAsrTerminal('failed', undefined, 'transcription_failed');
      emitTerminal('failed', 'transcription_failed');
      onErrorRef.current?.(message);
      return '';
    } finally {
      stoppingRef.current = false;
      if (mountedRef.current) setAudioLevel(0);
    }
  }, [emitAsrTerminal, emitTerminal]);

  const cancelDictation = useCallback(async (): Promise<void> => {
    const session = sessionRef.current;
    sessionRef.current = null;
    if (mountedRef.current) {
      setIsDictating(false);
      setAudioLevel(0);
    }
    if (!session) return;
    try {
      await session.cancel();
    } finally {
      emitTerminal('cancelled');
    }
  }, [emitTerminal]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      const session = sessionRef.current;
      sessionRef.current = null;
      if (session) {
        emitTerminal('cancelled', 'component_unmounted');
        void session.cancel();
      }
    };
  }, [emitTerminal]);

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
