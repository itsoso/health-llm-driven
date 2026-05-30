/**
 * Typed contract for one daily Garmin row (GET /daily-health/garmin/me).
 *
 * ⚠️ UNIT CONVENTIONS — must match backend `GarminData` model. Getting these
 * wrong is silent (everything is a `number`): treating `total_sleep_duration`
 * as seconds (÷3600 instead of ÷60) once rendered 7h as "0.1h". Never hand-divide
 * these fields — go through the helpers below so the conversion lives in one place.
 */
export interface GarminDailyRow {
  record_date?: string | null;
  steps?: number | null;
  active_minutes?: number | null;
  active_calories?: number | null;
  /** total sleep — MINUTES (not seconds) */
  total_sleep_duration?: number | null;
  /** deep sleep — MINUTES (not seconds) */
  deep_sleep_duration?: number | null;
  sleep_score?: number | null;
  resting_heart_rate?: number | null;
  /** HRV — milliseconds */
  hrv?: number | null;
  /** body battery 0–100 */
  body_battery_current?: number | null;
  body_battery_most_charged?: number | null;
  // API may carry more fields; tolerate them without weakening the typed ones.
  [key: string]: unknown;
}

const MINUTES_PER_HOUR = 60;

/** Below this many minutes a "night" is a nap fragment / partial sync → treat as dirty. */
export const SLEEP_DIRTY_FLOOR_MIN = 90; // 1.5h
export const DEEP_SLEEP_DIRTY_FLOOR_MIN = 30; // 0.5h

/**
 * Total sleep in hours, or `null` if missing or below the dirty-data floor.
 * Single source of truth — do not divide `total_sleep_duration` elsewhere.
 */
export function garminSleepHours(
  row: Pick<GarminDailyRow, 'total_sleep_duration'> | null | undefined,
): number | null {
  const min = row?.total_sleep_duration;
  return typeof min === 'number' && min >= SLEEP_DIRTY_FLOOR_MIN ? min / MINUTES_PER_HOUR : null;
}

/** Deep sleep in hours, or `null` if missing/dirty. */
export function garminDeepSleepHours(
  row: Pick<GarminDailyRow, 'deep_sleep_duration'> | null | undefined,
): number | null {
  const min = row?.deep_sleep_duration;
  return typeof min === 'number' && min >= DEEP_SLEEP_DIRTY_FLOOR_MIN ? min / MINUTES_PER_HOUR : null;
}
