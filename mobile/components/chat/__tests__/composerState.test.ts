import {
  canStartDictation,
  canStartHold,
  createInitialComposerState,
  isComposerBusy,
  reduceComposerState,
  shouldShowDisabledMic,
} from '../composerState';

describe('composerState', () => {
  it('allows either voice path to retry directly after a recoverable error', () => {
    const text = reduceComposerState(createInitialComposerState(), { type: 'toggle_mode' });
    const textError = reduceComposerState(text, {
      type: 'fail', errorCode: 'dictation_start_failed',
    });
    const holdError = {
      ...textError,
      mode: 'hold' as const,
    };

    expect(canStartDictation(textError)).toBe(true);
    expect(canStartHold(holdError)).toBe(true);
  });
  it('starts in hold-to-talk mode and keeps keyboard entry one tap away', () => {
    const state = createInitialComposerState();

    expect(state).toEqual({
      mode: 'hold',
      phase: 'idle',
      dictationEnabled: true,
      gesture: null,
    });
    expect(canStartDictation(state)).toBe(false);
    expect(canStartHold(state)).toBe(true);
    expect(isComposerBusy(state)).toBe(false);
  });

  it('moves through hold record and transcribe states before switching to editable text', () => {
    const hold = createInitialComposerState();
    const starting = reduceComposerState(hold, { type: 'hold_start' });
    const recording = reduceComposerState(starting, { type: 'hold_ready' });
    const moved = reduceComposerState(recording, { type: 'hold_move', gesture: 'text' });
    const transcribing = reduceComposerState(moved, { type: 'hold_release' });
    const completed = reduceComposerState(transcribing, { type: 'hold_transcribed' });

    expect(hold).toMatchObject({ mode: 'hold', phase: 'idle' });
    expect(starting).toMatchObject({ phase: 'hold_starting', gesture: 'send' });
    expect(recording).toMatchObject({ phase: 'hold_recording' });
    expect(transcribing).toMatchObject({ phase: 'hold_transcribing', gesture: 'text' });
    expect(completed).toEqual({
      mode: 'text',
      phase: 'idle',
      dictationEnabled: true,
      gesture: null,
    });
  });

  it('keeps hold and realtime dictation mutually exclusive', () => {
    const text = reduceComposerState(createInitialComposerState(), { type: 'toggle_mode' });
    const dictating = reduceComposerState(text, { type: 'dictation_start' });
    const rejectedHold = reduceComposerState(dictating, { type: 'hold_start' });
    const rejectedToggle = reduceComposerState(dictating, { type: 'toggle_mode' });

    expect(dictating.phase).toBe('live_dictating');
    expect(rejectedHold).toEqual(dictating);
    expect(rejectedToggle).toEqual(dictating);
    expect(isComposerBusy(dictating)).toBe(true);
  });

  it('turns the realtime microphone into an explicit disabled state on second click', () => {
    const text = reduceComposerState(createInitialComposerState(), { type: 'toggle_mode' });
    const dictating = reduceComposerState(text, { type: 'dictation_start' });
    const stopped = reduceComposerState(dictating, { type: 'dictation_stop' });

    expect(stopped).toMatchObject({ phase: 'idle', dictationEnabled: false });
    expect(shouldShowDisabledMic(stopped)).toBe(true);
    expect(canStartDictation(stopped)).toBe(true);
  });

  it('moves a rejected hold-to-talk transcript back into editable text mode', () => {
    const hold = createInitialComposerState();
    const submitting = reduceComposerState(hold, { type: 'submit' });
    const draftReady = reduceComposerState(submitting, { type: 'voice_draft_ready' });

    expect(draftReady).toEqual({
      mode: 'text',
      phase: 'idle',
      dictationEnabled: false,
      gesture: null,
    });
    expect(canStartDictation(draftReady)).toBe(true);
  });

  it('cleans active audio state when submitting or moving to the background', () => {
    const text = reduceComposerState(createInitialComposerState(), { type: 'toggle_mode' });
    const dictating = reduceComposerState(text, { type: 'dictation_start' });
    const submitting = reduceComposerState(dictating, { type: 'submit' });
    const submitted = reduceComposerState(submitting, { type: 'submit_complete' });
    const hold = createInitialComposerState();
    const recording = reduceComposerState(
      reduceComposerState(hold, { type: 'hold_start' }),
      { type: 'hold_ready' },
    );
    const backgrounded = reduceComposerState(recording, { type: 'background' });

    expect(submitting).toMatchObject({ phase: 'submitting', dictationEnabled: false, gesture: null });
    expect(submitted).toMatchObject({ phase: 'idle', dictationEnabled: true });
    expect(backgrounded).toMatchObject({ mode: 'hold', phase: 'idle', gesture: null, dictationEnabled: false });
  });

  it('re-enables dictation after an accepted submit so the next voice input can start immediately', () => {
    const text = reduceComposerState(createInitialComposerState(), { type: 'toggle_mode' });
    const submitting = reduceComposerState(text, { type: 'submit' });
    const submitted = reduceComposerState(submitting, { type: 'submit_complete' });

    expect(submitted).toMatchObject({ phase: 'idle', dictationEnabled: true });
    expect(canStartDictation(submitted)).toBe(true);
  });

  it('ignores hold completion events that arrive after cancellation', () => {
    const hold = createInitialComposerState();
    const starting = reduceComposerState(hold, { type: 'hold_start' });
    const cancelled = reduceComposerState(starting, { type: 'hold_cancel' });

    expect(reduceComposerState(cancelled, { type: 'hold_ready' })).toEqual(cancelled);
    expect(reduceComposerState(cancelled, { type: 'hold_transcribed' })).toEqual(cancelled);
  });

  it('keeps a cancelled hold release from entering transcription', () => {
    const starting = reduceComposerState(createInitialComposerState(), { type: 'hold_start' });
    const recording = reduceComposerState(starting, { type: 'hold_ready' });
    const cancelled = reduceComposerState(
      reduceComposerState(recording, { type: 'hold_move', gesture: 'cancel' }),
      { type: 'hold_release' },
    );

    expect(cancelled).toMatchObject({ mode: 'hold', phase: 'idle', gesture: null });
    expect(reduceComposerState(cancelled, { type: 'hold_transcribed' })).toEqual(cancelled);
  });

  it('returns to hold mode after a normal voice send release', () => {
    const starting = reduceComposerState(createInitialComposerState(), { type: 'hold_start' });
    const recording = reduceComposerState(starting, { type: 'hold_ready' });
    const transcribing = reduceComposerState(recording, { type: 'hold_release' });
    const complete = reduceComposerState(transcribing, { type: 'hold_transcribed' });

    expect(complete).toEqual({
      mode: 'hold',
      phase: 'idle',
      dictationEnabled: true,
      gesture: null,
    });
  });

  it('clears an input error when the user toggles modes to retry', () => {
    const text = reduceComposerState(createInitialComposerState(), { type: 'toggle_mode' });
    const failed = reduceComposerState(text, { type: 'fail', errorCode: 'cloud_asr_failed' });
    const hold = reduceComposerState(failed, { type: 'toggle_mode' });

    expect(hold).toEqual({
      mode: 'hold',
      phase: 'idle',
      dictationEnabled: true,
      gesture: null,
    });
  });

  it('ignores completion events when the composer is no longer submitting', () => {
    const initial = createInitialComposerState();

    expect(reduceComposerState(initial, { type: 'submit_complete' })).toEqual(initial);
    expect(reduceComposerState(initial, { type: 'dictation_end' })).toEqual(initial);
  });
});
