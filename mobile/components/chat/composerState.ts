export type ComposerMode = 'text' | 'hold';
export type ComposerPhase =
  | 'idle'
  | 'hold_starting'
  | 'hold_recording'
  | 'hold_transcribing'
  | 'live_dictating'
  | 'submitting'
  | 'error';
export type ComposerGesture = 'send' | 'text' | 'cancel' | null;

export interface ComposerState {
  mode: ComposerMode;
  phase: ComposerPhase;
  dictationEnabled: boolean;
  gesture: ComposerGesture;
  errorCode?: string;
}

export type ComposerEvent =
  | { type: 'toggle_mode' }
  | { type: 'hold_start' }
  | { type: 'hold_ready' }
  | { type: 'hold_move'; gesture: Exclude<ComposerGesture, null> }
  | { type: 'hold_release' }
  | { type: 'hold_transcribed' }
  | { type: 'hold_cancel' }
  | { type: 'voice_draft_ready' }
  | { type: 'dictation_start' }
  | { type: 'dictation_stop' }
  | { type: 'dictation_end' }
  | { type: 'submit' }
  | { type: 'submit_complete' }
  | { type: 'background' }
  | { type: 'fail'; errorCode: string }
  | { type: 'clear_error' };

export function createInitialComposerState(): ComposerState {
  return {
    mode: 'text',
    phase: 'idle',
    dictationEnabled: true,
    gesture: null,
  };
}

export function reduceComposerState(state: ComposerState, event: ComposerEvent): ComposerState {
  switch (event.type) {
    case 'toggle_mode':
      if (state.phase !== 'idle' && state.phase !== 'error') return state;
      return {
        mode: state.mode === 'text' ? 'hold' : 'text',
        phase: 'idle',
        dictationEnabled: state.dictationEnabled,
        gesture: null,
      };
    case 'hold_start':
      if (!canStartHold(state)) return state;
      return { ...state, phase: 'hold_starting', gesture: 'send', errorCode: undefined };
    case 'hold_ready':
      if (state.phase !== 'hold_starting') return state;
      return { ...state, phase: 'hold_recording' };
    case 'hold_move':
      if (state.phase !== 'hold_starting' && state.phase !== 'hold_recording') return state;
      return { ...state, gesture: event.gesture };
    case 'hold_release':
      if (state.phase !== 'hold_starting' && state.phase !== 'hold_recording') return state;
      if (state.gesture === 'cancel') {
        return { ...state, phase: 'idle', gesture: null };
      }
      return { ...state, phase: 'hold_transcribing' };
    case 'hold_transcribed':
      if (state.phase !== 'hold_transcribing') return state;
      return {
        mode: state.gesture === 'text' ? 'text' : state.mode,
        phase: 'idle',
        dictationEnabled: state.dictationEnabled,
        gesture: null,
      };
    case 'hold_cancel':
      if (state.phase !== 'hold_starting' && state.phase !== 'hold_recording') return state;
      return { ...state, phase: 'idle', gesture: null };
    case 'voice_draft_ready':
      return { ...state, mode: 'text', phase: 'idle', dictationEnabled: false, gesture: null };
    case 'dictation_start':
      if (!canStartDictation(state)) return state;
      return {
        ...state,
        phase: 'live_dictating',
        dictationEnabled: true,
        gesture: null,
        errorCode: undefined,
      };
    case 'dictation_stop':
      if (state.phase !== 'live_dictating') return state;
      return { ...state, phase: 'idle', dictationEnabled: false, gesture: null };
    case 'dictation_end':
      if (state.phase !== 'live_dictating') return state;
      return { ...state, phase: 'idle', dictationEnabled: true, gesture: null };
    case 'submit':
      return {
        ...state,
        phase: 'submitting',
        dictationEnabled: false,
        gesture: null,
        errorCode: undefined,
      };
    case 'submit_complete':
      if (state.phase !== 'submitting') return state;
      return { ...state, phase: 'idle', dictationEnabled: true, gesture: null };
    case 'background':
      return {
        ...state,
        phase: 'idle',
        dictationEnabled: false,
        gesture: null,
        errorCode: undefined,
      };
    case 'fail':
      return { ...state, phase: 'error', gesture: null, errorCode: event.errorCode };
    case 'clear_error':
      if (state.phase !== 'error') return state;
      return { ...state, phase: 'idle', errorCode: undefined };
  }
}

export function canStartHold(state: ComposerState): boolean {
  return state.mode === 'hold' && (state.phase === 'idle' || state.phase === 'error');
}

export function canStartDictation(state: ComposerState): boolean {
  return state.mode === 'text' && (state.phase === 'idle' || state.phase === 'error');
}

export function shouldShowDisabledMic(state: ComposerState): boolean {
  return state.mode === 'text' && state.phase !== 'live_dictating' && !state.dictationEnabled;
}

export function isComposerBusy(state: ComposerState): boolean {
  return state.phase !== 'idle' && state.phase !== 'error';
}
