export type VoiceSessionOwner = 'hold' | 'dictation';

export interface VoiceSessionLease {
  id: number;
  owner: VoiceSessionOwner;
}

let nextLeaseId = 0;
let activeLeaseId: number | null = null;
let nativeOperationQueue: Promise<void> = Promise.resolve();

function enqueueNativeOperation<T>(operation: () => Promise<T>): Promise<T> {
  const result = nativeOperationQueue
    .catch(() => undefined)
    .then(operation);
  nativeOperationQueue = result.then(() => undefined, () => undefined);
  return result;
}

export function claimVoiceSession(owner: VoiceSessionOwner): VoiceSessionLease {
  const lease = { id: ++nextLeaseId, owner };
  activeLeaseId = lease.id;
  return lease;
}

export function isVoiceSessionOwner(lease: VoiceSessionLease | null | undefined): boolean {
  return Boolean(lease && activeLeaseId === lease.id);
}

export function releaseVoiceSession(lease: VoiceSessionLease | null | undefined): void {
  if (isVoiceSessionOwner(lease)) activeLeaseId = null;
}

/**
 * Serializes native starts across both composer voice paths. If another path
 * claims ownership while a start is in flight, stale cleanup runs before the
 * newer start is allowed onto the process-wide Voice singleton.
 */
export function runVoiceSessionStart(
  lease: VoiceSessionLease,
  start: () => Promise<void>,
  cleanupIfSuperseded: () => Promise<void>,
): Promise<boolean> {
  return enqueueNativeOperation(async () => {
    if (!isVoiceSessionOwner(lease)) return false;
    await start();
    if (isVoiceSessionOwner(lease)) return true;
    await cleanupIfSuperseded();
    return false;
  });
}

/** Run stop/cancel only when the caller still owns the shared native session. */
export function runVoiceSessionCommand(
  lease: VoiceSessionLease | null | undefined,
  command: () => Promise<void>,
): Promise<boolean> {
  return enqueueNativeOperation(async () => {
    if (!isVoiceSessionOwner(lease)) return false;
    await command();
    return true;
  });
}

export function resetVoiceSessionCoordinatorForTests(): void {
  nextLeaseId = 0;
  activeLeaseId = null;
  nativeOperationQueue = Promise.resolve();
}
