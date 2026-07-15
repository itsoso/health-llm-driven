import Voice, {
  type SpeechEndEvent,
  type SpeechErrorEvent,
  type SpeechRecognizedEvent,
  type SpeechResultsEvent,
} from '@react-native-voice/voice';

export type VoiceEventHandlers = {
  onSpeechPartialResults?: (event: SpeechResultsEvent) => void;
  onSpeechResults?: (event: SpeechResultsEvent) => void;
  onSpeechRecognized?: (event: SpeechRecognizedEvent) => void;
  onSpeechEnd?: (event: SpeechEndEvent) => void;
  onSpeechError?: (event: SpeechErrorEvent) => void;
};

export type VoiceEventLease = { id: number };

let nextLeaseId = 0;
let active: { lease: VoiceEventLease; handlers: VoiceEventHandlers } | null = null;

function installDispatchers(): void {
  // @react-native-voice/voice exposes process-wide callback slots. Keep those
  // slots owned by this router and switch only the active logical session.
  Voice.onSpeechPartialResults = event => active?.handlers.onSpeechPartialResults?.(event);
  Voice.onSpeechResults = event => active?.handlers.onSpeechResults?.(event);
  Voice.onSpeechRecognized = event => active?.handlers.onSpeechRecognized?.(event);
  Voice.onSpeechEnd = event => active?.handlers.onSpeechEnd?.(event);
  Voice.onSpeechError = event => active?.handlers.onSpeechError?.(event);
}

export function bindVoiceEventHandlers(handlers: VoiceEventHandlers): VoiceEventLease {
  installDispatchers();
  const lease = { id: ++nextLeaseId };
  active = { lease, handlers };
  return lease;
}

export function isVoiceEventHandlerOwner(lease: VoiceEventLease | null | undefined): boolean {
  return Boolean(lease && active?.lease.id === lease.id);
}

export function releaseVoiceEventHandlers(lease: VoiceEventLease | null | undefined): void {
  if (isVoiceEventHandlerOwner(lease)) active = null;
}

export function resetVoiceEventRouterForTests(): void {
  nextLeaseId = 0;
  active = null;
  installDispatchers();
}
