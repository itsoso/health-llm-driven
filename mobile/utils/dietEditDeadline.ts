export class DietEditTimeoutError extends Error {
  constructor() {
    super('diet_edit_timeout');
    this.name = 'DietEditTimeoutError';
  }
}

export class DietEditCancelledError extends Error {
  constructor() { super('diet_edit_cancelled'); this.name = 'DietEditCancelledError'; }
}

export function assertDietEditActive(signal: AbortSignal): void {
  if (signal.aborted) throw new DietEditTimeoutError();
}

/** Bound the whole edit, including revision joins and request interceptors.
 * Aborting transport does not prove the server rolled back an accepted write.
 */
export async function runDietEditWithDeadline<T>(
  operation: (signal: AbortSignal) => Promise<T>,
  externalSignal?: AbortSignal,
): Promise<T> {
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout> | undefined;
  let cancel = () => {};
  const cancelled = new Promise<never>((_resolve, reject) => {
    cancel = () => { controller.abort(); reject(new DietEditCancelledError()); };
    if (externalSignal?.aborted) cancel();
    else externalSignal?.addEventListener('abort', cancel);
  });
  const deadline = new Promise<never>((_resolve, reject) => {
    timer = setTimeout(() => {
      controller.abort();
      reject(new DietEditTimeoutError());
    }, 35000);
  });
  try {
    return await Promise.race([externalSignal?.aborted ? Promise.reject(new DietEditCancelledError()) : operation(controller.signal), deadline, cancelled]);
  } finally {
    externalSignal?.removeEventListener('abort', cancel);
    if (timer !== undefined) clearTimeout(timer);
  }
}
