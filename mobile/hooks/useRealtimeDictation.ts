import { useCallback, useEffect, useRef, useState } from 'react';
import {
  RecordingPresets,
  requestRecordingPermissionsAsync,
  setAudioModeAsync,
  useAudioRecorder,
} from 'expo-audio';
import { durationBucket, emitClientEvent } from '../services/clientEvents';
import { transcribeAudioDetailed, type TranscribeAudioResult } from '../services/transcribe';

interface UseRealtimeDictationOptions {
  onTranscript: (text: string, result?: TranscribeAudioResult) => void;
  onEnd?: () => void;
  onError?: (message: string) => void;
  locale?: string;
}

export function useRealtimeDictation({
  onTranscript,
  onEnd,
  onError,
}: UseRealtimeDictationOptions) {
  const [isDictating, setIsDictating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);

  const readyRef = useRef(false);
  const startingRef = useRef(false);
  const transcribingRef = useRef(false);
  const cancelledRef = useRef(false);
  const startSeqRef = useRef(0);
  const transcriptionSeqRef = useRef(0);
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

  const releaseRecordingMode = useCallback(async () => {
    try {
      await setAudioModeAsync({ allowsRecording: false });
    } catch (e) {
      if (__DEV__) console.warn('[useRealtimeDictation] release audio session failed:', e);
    }
  }, []);

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

  useEffect(() => {
    return () => {
      const hadSession = startingRef.current || readyRef.current || transcribingRef.current;
      startSeqRef.current += 1;
      transcriptionSeqRef.current += 1;
      startingRef.current = false;
      cancelledRef.current = true;
      if (hadSession) emitTerminal('cancelled', 'component_unmounted');
      const shouldStopRecorder = readyRef.current;
      readyRef.current = false;
      setIsDictating(false);
      if (shouldStopRecorder) {
        try {
          void Promise.resolve(recorder.stop()).catch((e) => {
            if (__DEV__) console.warn('[useRealtimeDictation] unmount stop failed:', e);
          });
        } catch (e) {
          if (__DEV__) console.warn('[useRealtimeDictation] unmount stop failed:', e);
        }
      }
      void releaseRecordingMode();
    };
  }, [emitTerminal, recorder, releaseRecordingMode]);

  const startDictation = useCallback(async () => {
    if (startingRef.current || readyRef.current || transcribingRef.current) return false;
    const seq = startSeqRef.current + 1;
    startSeqRef.current = seq;
    startingRef.current = true;
    cancelledRef.current = false;
    sessionStartedAtRef.current = Date.now();
    terminalSentRef.current = false;
    asrTerminalSentRef.current = false;
    setError(null);

    const isCurrentStart = () => startSeqRef.current === seq;

    try {
      const perm = await requestRecordingPermissionsAsync();
      if (!isCurrentStart()) {
        await releaseRecordingMode();
        return false;
      }
      if (!perm.granted) {
        const message = '需要麦克风权限才能实时听写';
        setError(message);
        emitTerminal('failed', 'microphone_permission_denied');
        onErrorRef.current?.(message);
        return false;
      }

      await setAudioModeAsync({
        allowsRecording: true,
        playsInSilentMode: true,
      });
      if (!isCurrentStart()) {
        await releaseRecordingMode();
        return false;
      }

      await recorder.prepareToRecordAsync();
      if (!isCurrentStart()) {
        await releaseRecordingMode();
        return false;
      }

      recorder.record();
      readyRef.current = true;
      setIsDictating(true);
      return true;
    } catch (e: any) {
      readyRef.current = false;
      setIsDictating(false);
      await releaseRecordingMode();
      const message = e?.message || String(e);
      setError(message);
      emitTerminal('failed', 'recording_start_failed');
      onErrorRef.current?.(message);
      return false;
    } finally {
      if (isCurrentStart()) startingRef.current = false;
    }
  }, [emitTerminal, recorder, releaseRecordingMode]);

  const stopDictation = useCallback(async (): Promise<string> => {
    const wasStarting = startingRef.current;
    if (wasStarting) {
      startSeqRef.current += 1;
      startingRef.current = false;
    }

    if (!readyRef.current) {
      setIsDictating(false);
      await releaseRecordingMode();
      if (wasStarting) emitTerminal('cancelled', 'start_cancelled');
      return '';
    }

    const transcriptionSeq = transcriptionSeqRef.current + 1;
    transcriptionSeqRef.current = transcriptionSeq;
    transcribingRef.current = true;
    cancelledRef.current = false;
    setIsDictating(false);

    try {
      try {
        await recorder.stop();
      } finally {
        readyRef.current = false;
        await releaseRecordingMode();
      }

      const uri = recorder.uri;
      if (!uri) {
        emitAsrTerminal('failed', undefined, 'recording_uri_missing');
        emitTerminal('failed', 'recording_uri_missing');
        return '';
      }

      const result = await transcribeAudioDetailed(uri);
      if (transcriptionSeqRef.current !== transcriptionSeq || cancelledRef.current) {
        return '';
      }

      const text = result.text.trim();
      if (text) {
        onTranscriptRef.current(text, result);
        emitAsrTerminal('completed', result);
        emitTerminal('completed');
        onEndRef.current?.();
        return text;
      }

      emitAsrTerminal('failed', result, 'empty_transcript');
      emitTerminal('failed', 'empty_transcript');
      return '';
    } catch (e: any) {
      readyRef.current = false;
      if (transcriptionSeqRef.current === transcriptionSeq && !cancelledRef.current) {
        const message = e?.message || '语音识别失败';
        setError(message);
        emitAsrTerminal('failed', undefined, 'transcription_failed');
        emitTerminal('failed', 'transcription_failed');
        onErrorRef.current?.(message);
      }
      return '';
    } finally {
      if (transcriptionSeqRef.current === transcriptionSeq) {
        transcribingRef.current = false;
      }
    }
  }, [emitAsrTerminal, emitTerminal, recorder, releaseRecordingMode]);

  const cancelDictation = useCallback(async () => {
    const wasStarting = startingRef.current;
    if (wasStarting) {
      startSeqRef.current += 1;
      startingRef.current = false;
    }
    const wasReady = readyRef.current;
    cancelledRef.current = true;
    transcriptionSeqRef.current += 1;
    readyRef.current = false;
    transcribingRef.current = false;
    setIsDictating(false);

    try {
      if (wasReady) await recorder.stop();
    } catch (e) {
      if (__DEV__) console.warn('[useRealtimeDictation] cancel stop failed:', e);
    } finally {
      await releaseRecordingMode();
      if (wasStarting || wasReady) {
        emitTerminal('cancelled', wasStarting ? 'start_cancelled' : undefined);
      }
    }
  }, [emitTerminal, recorder, releaseRecordingMode]);

  return {
    isDictating,
    error,
    startDictation,
    stopDictation,
    cancelDictation,
  };
}
