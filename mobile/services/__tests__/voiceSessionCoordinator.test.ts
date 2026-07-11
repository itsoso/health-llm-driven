import {
  claimVoiceSession,
  isVoiceSessionOwner,
  releaseVoiceSession,
  resetVoiceSessionCoordinatorForTests,
  runVoiceSessionCommand,
  runVoiceSessionStart,
} from '../voiceSessionCoordinator';

describe('voiceSessionCoordinator', () => {
  beforeEach(() => {
    resetVoiceSessionCoordinatorForTests();
  });

  it('cleans a superseded native start before the newer session starts', async () => {
    const events: string[] = [];
    let releaseOldStart!: () => void;
    const oldStartGate = new Promise<void>((resolve) => { releaseOldStart = resolve; });
    let markOldStartEntered!: () => void;
    const oldStartEntered = new Promise<void>((resolve) => { markOldStartEntered = resolve; });
    const oldLease = claimVoiceSession('hold');
    const oldStart = runVoiceSessionStart(
      oldLease,
      async () => {
        events.push('old-start');
        markOldStartEntered();
        await oldStartGate;
      },
      async () => {
        events.push('old-cleanup');
      },
    );
    await oldStartEntered;

    const newLease = claimVoiceSession('dictation');
    const newStart = runVoiceSessionStart(
      newLease,
      async () => {
        events.push('new-start');
      },
      async () => {
        events.push('new-cleanup');
      },
    );
    releaseOldStart();

    await expect(oldStart).resolves.toBe(false);
    await expect(newStart).resolves.toBe(true);
    expect(events).toEqual(['old-start', 'old-cleanup', 'new-start']);
    expect(isVoiceSessionOwner(newLease)).toBe(true);
  });

  it('never runs a stale stop or cancel command against a newer owner', async () => {
    const staleCommand = jest.fn();
    const oldLease = claimVoiceSession('hold');
    const newLease = claimVoiceSession('dictation');

    await expect(runVoiceSessionCommand(oldLease, staleCommand)).resolves.toBe(false);

    expect(staleCommand).not.toHaveBeenCalled();
    expect(isVoiceSessionOwner(newLease)).toBe(true);
    releaseVoiceSession(newLease);
    expect(isVoiceSessionOwner(newLease)).toBe(false);
  });
});
