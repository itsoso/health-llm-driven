export class DietEditTimeoutError extends Error {
  constructor() {
    super('diet_edit_timeout');
    this.name = 'DietEditTimeoutError';
  }
}

export function assertDietEditActive(signal: AbortSignal): void {
  if (signal.aborted) throw new DietEditTimeoutError();
}

/** Bound the whole edit, including revision joins and request interceptors.
 * Aborting transport does not prove the server rolled back an accepted write.
 */
export async function runDietEditWithDeadline<T>(
  operation: (signal: AbortSignal) => Promise<T>,
): Promise<T> {
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout> | undefined;
  const deadline = new Promise<never>((_resolve, reject) => {
    timer = setTimeout(() => {
      controller.abort();
      reject(new DietEditTimeoutError());
    }, 35000);
  });
  try {
    return await Promise.race([operation(controller.signal), deadline]);
  } finally {
    if (timer !== undefined) clearTimeout(timer);
  }
}
