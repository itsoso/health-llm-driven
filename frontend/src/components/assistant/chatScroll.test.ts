// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import {
  CHAT_SCROLL_SETTLE_DELAYS_MS,
  clearChatScrollTimers,
  scheduleSettledScrollToBottom,
} from './chatScroll';

describe('chat scroll helpers', () => {
  it('schedules several bottom scrolls so late layout growth is captured', () => {
    const callbacks: Array<() => void> = [];
    const delays: number[] = [];
    const scrollTo = vi.fn();
    const element = {
      scrollHeight: 1200,
      scrollTo,
    } as unknown as HTMLElement;

    const timers = scheduleSettledScrollToBottom({
      getElement: () => element,
      setTimer: ((callback: TimerHandler, delay?: number) => {
        callbacks.push(callback as () => void);
        delays.push(Number(delay));
        return callbacks.length as unknown as ReturnType<typeof window.setTimeout>;
      }) as typeof window.setTimeout,
    });

    expect(timers).toHaveLength(CHAT_SCROLL_SETTLE_DELAYS_MS.length);
    expect(delays).toEqual([...CHAT_SCROLL_SETTLE_DELAYS_MS]);

    callbacks.forEach(callback => callback());

    expect(scrollTo).toHaveBeenCalledTimes(CHAT_SCROLL_SETTLE_DELAYS_MS.length);
    expect(scrollTo).toHaveBeenNthCalledWith(1, { top: 1200, behavior: 'smooth' });
    expect(scrollTo).toHaveBeenLastCalledWith({ top: 1200, behavior: 'auto' });
  });

  it('clears previous timers before scheduling a new scroll batch', () => {
    const clearExisting = vi.fn();

    scheduleSettledScrollToBottom({
      getElement: () => null,
      clearExisting,
      setTimer: ((callback: TimerHandler, delay?: number) => {
        return Number(delay) as unknown as ReturnType<typeof window.setTimeout>;
      }) as typeof window.setTimeout,
    });

    expect(clearExisting).toHaveBeenCalledTimes(1);
  });

  it('clears every stored timer', () => {
    const clearSpy = vi.spyOn(window, 'clearTimeout');

    clearChatScrollTimers([
      1 as unknown as ReturnType<typeof window.setTimeout>,
      2 as unknown as ReturnType<typeof window.setTimeout>,
    ]);

    expect(clearSpy).toHaveBeenCalledTimes(2);
    clearSpy.mockRestore();
  });
});
