// @vitest-environment jsdom

import { describe, expect, it, vi } from 'vitest';
import { buildSharedDeepLinks, openSharedInApp } from './OpenInAppButton';

describe('OpenInAppButton deep links', () => {
  it('uses the legacy mobile scheme first and health scheme as fallback', () => {
    expect(buildSharedDeepLinks('abc123')).toEqual([
      'mobile://shared/abc123',
      'health://shared/abc123',
    ]);
  });

  it('tries the fallback scheme when the page is still visible', () => {
    vi.useFakeTimers();
    const navigate = vi.fn();

    openSharedInApp('token123', navigate, () => true);
    expect(navigate).toHaveBeenCalledWith('mobile://shared/token123');

    vi.advanceTimersByTime(700);
    expect(navigate).toHaveBeenCalledWith('health://shared/token123');
    vi.useRealTimers();
  });

  it('does not try fallback after the app has backgrounded the page', () => {
    vi.useFakeTimers();
    const navigate = vi.fn();

    openSharedInApp('token123', navigate, () => false);
    vi.advanceTimersByTime(700);

    expect(navigate).toHaveBeenCalledTimes(1);
    expect(navigate).toHaveBeenCalledWith('mobile://shared/token123');
    vi.useRealTimers();
  });
});
