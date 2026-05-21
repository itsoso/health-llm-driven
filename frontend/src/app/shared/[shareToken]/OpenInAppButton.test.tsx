// @vitest-environment jsdom

import { describe, expect, it, vi } from 'vitest';
import { buildSharedDeepLinks, openSharedInApp } from './OpenInAppButton';

describe('OpenInAppButton deep links', () => {
  it('uses app schemes first and the universal link as the final fallback', () => {
    expect(buildSharedDeepLinks('abc123')).toEqual([
      'health://shared/abc123',
      'mobile://shared/abc123',
      'https://health.executor.life/shared/abc123',
    ]);
  });

  it('tries fallbacks when the page is still visible', () => {
    vi.useFakeTimers();
    const navigate = vi.fn();

    openSharedInApp('token123', navigate, () => true);
    expect(navigate).toHaveBeenCalledWith('health://shared/token123');

    vi.advanceTimersByTime(700);
    expect(navigate).toHaveBeenCalledWith('mobile://shared/token123');

    vi.advanceTimersByTime(700);
    expect(navigate).toHaveBeenCalledWith('https://health.executor.life/shared/token123');
    vi.useRealTimers();
  });

  it('does not try fallback after the app has backgrounded the page', () => {
    vi.useFakeTimers();
    const navigate = vi.fn();

    openSharedInApp('token123', navigate, () => false);
    vi.advanceTimersByTime(700);

    expect(navigate).toHaveBeenCalledTimes(1);
    expect(navigate).toHaveBeenCalledWith('health://shared/token123');
    vi.useRealTimers();
  });
});
