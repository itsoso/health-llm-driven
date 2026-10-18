import { protectLocationTelemetry } from '../locationTelemetry';

describe('location telemetry export boundary', () => {
  it.each([
    { request: { url: '/daily-journeys/sessions/x/points', data: 'private' } },
    { breadcrumbs: [{ data: { url: '/daily-journeys/sessions' } }] },
    { exception: { values: [{ stacktrace: { frames: [{ filename: 'services/dailyJourneyCapture.ts' }] } }] } },
    { extra: { coords: { latitude: 12.3, longitude: 45.6 } } },
  ])('drops private location events, traces and breadcrumbs before export', event => {
    expect(protectLocationTelemetry(event)).toBeNull();
  });
  it('preserves unrelated events', () => {
    const event = { message: 'dashboard failed', transaction: '/dashboard' };
    expect(protectLocationTelemetry(event)).toBe(event);
  });
});
