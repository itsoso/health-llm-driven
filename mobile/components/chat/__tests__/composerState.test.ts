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
    const textError = reduceComposerState(createInitialComposerState(), {
      type: 'fail', errorCode: 'dictation_start_failed',
    });
    const holdError = {
      ...textError,
      mode: 'hold' as const,
    };

    expect(canStartDictation(textError)).toBe(true);
    expect(canStartHold(holdError)).toBe(true);
  });
  it('starts in text mode with an available realtime microphone', () => {
    const state = createInitialComposerState();

    expect(state).toEqual({
      mode: 'text',
      phase: 'idle',
      dictationEnabled: true,
      gesture: null,
    });
    expect(canStartDictation(state)).toBe(true);
    expect(canStartHold(state)).toBe(false);
    expect(isComposerBusy(state)).toBe(false);
  });

  it('toggles into hold mode and moves through record and transcribe states', () => {
    const hold = reduceComposerState(createInitialComposerState(), { type: 'toggle_mode' });
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
    const dictating = reduceComposerState(createInitialComposerState(), { type: 'dictation_start' });
    const rejectedHold = reduceComposerState(dictating, { type: 'hold_start' });
    const rejectedToggle = reduceComposerState(dictating, { type: 'toggle_mode' });

    expect(dictating.phase).toBe('live_dictating');
    expect(rejectedHold).toEqual(dictating);
    expect(rejectedToggle).toEqual(dictating);
    expect(isComposerBusy(dictating)).toBe(true);
  });

  it('turns the realtime microphone into an explicit disabled state on second click', () => {
    const dictating = reduceComposerState(createInitialComposerState(), { type: 'dictation_start' });
    const stopped = reduceComposerState(dictating, { type: 'dictation_stop' });

    expect(stopped).toMatchObject({ phase: 'idle', dictationEnabled: false });
    expect(shouldShowDisabledMic(stopped)).toBe(true);
    expect(canStartDictation(stopped)).toBe(true);
  });

  it('cleans active audio state when submitting or moving to the background', () => {
    const dictating = reduceComposerState(createInitialComposerState(), { type: 'dictation_start' });
    const submitting = reduceComposerState(dictating, { type: 'submit' });
    const submitted = reduceComposerState(submitting, { type: 'submit_complete' });
    const hold = reduceComposerState(createInitialComposerState(), { type: 'toggle_mode' });
    const recording = reduceComposerState(
      reduceComposerState(hold, { type: 'hold_start' }),
      { type: 'hold_ready' },
    );
    const backgrounded = reduceComposerState(recording, { type: 'background' });

    expect(submitting).toMatchObject({ phase: 'submitting', dictationEnabled: false, gesture: null });
    expect(submitted).toMatchObject({ phase: 'idle', dictationEnabled: false });
    expect(backgrounded).toMatchObject({ mode: 'hold', phase: 'idle', gesture: null, dictationEnabled: false });
  });

  it('ignores hold completion events that arrive after cancellation', () => {
    const hold = reduceComposerState(createInitialComposerState(), { type: 'toggle_mode' });
    const starting = reduceComposerState(hold, { type: 'hold_start' });
    const cancelled = reduceComposerState(starting, { type: 'hold_cancel' });

    expect(reduceComposerState(cancelled, { type: 'hold_ready' })).toEqual(cancelled);
    expect(reduceComposerState(cancelled, { type: 'hold_transcribed' })).toEqual(cancelled);
  });
});
