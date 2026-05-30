import {
  garminSleepHours,
  garminDeepSleepHours,
  SLEEP_DIRTY_FLOOR_MIN,
  DEEP_SLEEP_DIRTY_FLOOR_MIN,
} from '../garmin';

describe('garmin unit conversion (single source of truth)', () => {
  it('treats total_sleep_duration as MINUTES, not seconds', () => {
    // 420 min = 7h. The original bug divided by 3600 (seconds) → 0.1h.
    expect(garminSleepHours({ total_sleep_duration: 420 })).toBeCloseTo(7.0, 5);
    expect(garminSleepHours({ total_sleep_duration: 480 })).toBeCloseTo(8.0, 5);
    // guard against the seconds regression explicitly
    expect(garminSleepHours({ total_sleep_duration: 420 })).not.toBeCloseTo(0.1, 1);
  });

  it('returns null below the dirty-data floor (nap fragment / partial sync)', () => {
    expect(garminSleepHours({ total_sleep_duration: SLEEP_DIRTY_FLOOR_MIN - 1 })).toBeNull();
    expect(garminSleepHours({ total_sleep_duration: 30 })).toBeNull();
    expect(garminSleepHours({ total_sleep_duration: SLEEP_DIRTY_FLOOR_MIN })).toBeCloseTo(1.5, 5);
  });

  it('returns null for missing / nullish rows', () => {
    expect(garminSleepHours(null)).toBeNull();
    expect(garminSleepHours(undefined)).toBeNull();
    expect(garminSleepHours({ total_sleep_duration: null })).toBeNull();
    expect(garminSleepHours({})).toBeNull();
  });

  it('deep sleep: minutes → hours with its own floor', () => {
    expect(garminDeepSleepHours({ deep_sleep_duration: 60 })).toBeCloseTo(1.0, 5);
    expect(garminDeepSleepHours({ deep_sleep_duration: DEEP_SLEEP_DIRTY_FLOOR_MIN })).toBeCloseTo(0.5, 5);
    expect(garminDeepSleepHours({ deep_sleep_duration: DEEP_SLEEP_DIRTY_FLOOR_MIN - 1 })).toBeNull();
    expect(garminDeepSleepHours(null)).toBeNull();
  });
});
