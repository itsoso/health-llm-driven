import { assertDietEditActive, DietEditTimeoutError, runDietEditWithDeadline } from '../dietEditDeadline';

describe('diet edit deadline', () => {
  afterEach(() => jest.useRealTimers());

  it('releases an indefinitely pending save and aborts transport', async () => {
    jest.useFakeTimers();
    let signal!: AbortSignal;
    const promise = runDietEditWithDeadline(async s => {
      signal = s;
      return new Promise<never>(() => {});
    });
    const check = expect(promise).rejects.toBeInstanceOf(DietEditTimeoutError);
    jest.advanceTimersByTime(35000);
    await check;
    expect(signal.aborted).toBe(true);
  });

  it('does not dispatch a correction after a timed-out revision join resolves', async () => {
    jest.useFakeTimers();
    let release!: () => void;
    const join = new Promise<void>(resolve => { release = resolve; });
    const send = jest.fn();
    const promise = runDietEditWithDeadline(async signal => {
      await join;
      assertDietEditActive(signal);
      send();
    });
    const check = expect(promise).rejects.toBeInstanceOf(DietEditTimeoutError);
    jest.advanceTimersByTime(35000);
    await check;
    release();
    await Promise.resolve();
    expect(send).not.toHaveBeenCalled();
  });

  it('cleans the timer and preserves the result and original error', async () => {
    jest.useFakeTimers();
    expect(await runDietEditWithDeadline(async () => 42)).toBe(42);
    const error = new Error('synthetic');
    await expect(runDietEditWithDeadline(async () => { throw error; })).rejects.toBe(error);
    expect(jest.getTimerCount()).toBe(0);
  });
});
