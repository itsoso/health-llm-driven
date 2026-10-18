/** Do not export precise routes, payloads or their breadcrumbs to telemetry. */
export function protectLocationTelemetry<T>(event: T): T | null {
  const visited = new WeakSet<object>();
  function containsLocation(value: unknown): boolean {
    if (typeof value === 'string') {
      return /daily[-_]?journey|daily-journeys|share-location|REVA_DAILY_JOURNEY|restapi\.amap\.com/i.test(value)
        || (value.includes('"latitude"') && value.includes('"longitude"'));
    }
    if (!value || typeof value !== 'object' || visited.has(value)) return false;
    visited.add(value);
    if ('latitude' in value || 'longitude' in value) return true;
    return Object.values(value).some(containsLocation);
  }
  return containsLocation(event) ? null : event;
}
