import { resolveNotificationRoute } from '../notificationRoutes';

describe('resolveNotificationRoute', () => {
  it('returns plain expo-router paths unchanged', () => {
    expect(resolveNotificationRoute({ deep_link: '/calendar' })).toBe('/calendar');
    expect(resolveNotificationRoute({ deep_link: '/(tabs)/alerts' })).toBe('/(tabs)/alerts');
    expect(resolveNotificationRoute({ deep_link: '/voice-chat?intent=briefing' })).toBe(
      '/voice-chat?intent=briefing',
    );
  });

  it('strips the health:// scheme to a router path', () => {
    expect(resolveNotificationRoute({ deep_link: 'health://card/42' })).toBe('/card/42');
    expect(resolveNotificationRoute({ deep_link: 'health://settings/garmin' })).toBe(
      '/settings/garmin',
    );
  });

  it('strips mobile:// and life.executor.health:// schemes too', () => {
    expect(resolveNotificationRoute({ deep_link: 'mobile://diet' })).toBe('/diet');
    expect(resolveNotificationRoute({ deep_link: 'life.executor.health://calendar' })).toBe(
      '/calendar',
    );
  });

  it('normalizes /workout-detail/{id} path-segment to the real query route', () => {
    expect(resolveNotificationRoute({ deep_link: '/workout-detail/123' })).toBe(
      '/workout-detail?id=123',
    );
    expect(resolveNotificationRoute({ deep_link: 'health://workout-detail/9' })).toBe(
      '/workout-detail?id=9',
    );
  });

  it('accepts the deeplink alias key', () => {
    expect(resolveNotificationRoute({ deeplink: '/fitness-plan' })).toBe('/fitness-plan');
  });

  it('falls back to the legacy data.screen enum', () => {
    expect(resolveNotificationRoute({ screen: 'alerts' })).toBe('/(tabs)/alerts');
    expect(resolveNotificationRoute({ screen: 'record' })).toBe('/(tabs)/record');
    expect(resolveNotificationRoute({ screen: 'diet' })).toBe('/diet');
  });

  it('prefers deep_link over screen when both present', () => {
    expect(resolveNotificationRoute({ deep_link: '/supplement-inventory', screen: 'home' })).toBe(
      '/supplement-inventory',
    );
  });

  it('returns null for unroutable payloads (no destination fabricated)', () => {
    expect(resolveNotificationRoute(null)).toBeNull();
    expect(resolveNotificationRoute(undefined)).toBeNull();
    expect(resolveNotificationRoute({})).toBeNull();
    expect(resolveNotificationRoute({ deep_link: '' })).toBeNull();
    expect(resolveNotificationRoute({ deep_link: '   ' })).toBeNull();
    expect(resolveNotificationRoute({ screen: 'home' })).toBeNull(); // home is not a feed destination
    expect(resolveNotificationRoute({ screen: 'nonexistent' })).toBeNull();
  });

  it('leaves http(s) URLs untouched (not an app scheme)', () => {
    expect(resolveNotificationRoute({ deep_link: 'https://health.executor.life/x' })).toBe(
      'https://health.executor.life/x',
    );
  });
});


describe('medication reminder landing', () => {
  const slot = { reminder_type: 'medication', scheduled_date: '2026-10-24', scheduled_time: '18:00', scheduled_timezone: 'Asia/Shanghai' };
  const params = (route: string | null) => new URLSearchParams(route?.split('?')[1]);
  it('opens the actual server group payload as a reminder list, not a chat draft', () => {
    const route = resolveNotificationRoute({ ...slot, medication_ids: [7, 8], deep_link: '/(tabs)/chat' });
    expect(route?.split('?')[0]).toBe('/medication-reminders');
    expect(Object.fromEntries(params(route))).toEqual({ ids: '7,8', date: '2026-10-24', time: '18:00', sourceTimezone: 'Asia/Shanghai' });
  });
  it.each(['/medications', '/(tabs)/chat', '/(tabs)/record', '/notification-history?detailId=123'])('opens single detail from %s', deep_link => {
    const route = resolveNotificationRoute({ ...slot, medication_id: 7, deep_link, medication_name: 'private-secret' });
    expect(route?.split('?')[0]).toBe('/medication-reminder');
    expect(Object.fromEntries(params(route))).toEqual({ id: '7', date: '2026-10-24', time: '18:00', sourceTimezone: 'Asia/Shanghai' });
    expect(route).not.toContain('private');
  });
  it('deduplicates a singleton group and preserves a non-China timezone', () => {
    const route = resolveNotificationRoute({ ...slot, medication_ids: [7, 7], scheduled_timezone: 'America/New_York' });
    expect(route?.split('?')[0]).toBe('/medication-reminder');
    expect(params(route).get('id')).toBe('7');
    expect(params(route).get('sourceTimezone')).toBe('America/New_York');
  });
  it('preserves original local slot without inventing a date', () => {
    const route = resolveNotificationRoute({ kind: 'medication_reminder', medication_id: 7, taken_time: '06:00', scheduled_time: '08:00' });
    expect(route).toBe('/medication-reminder?id=7&time=06%3A00');
  });
  it('extracts only legacy medication occurrence fields', () => {
    expect(resolveNotificationRoute({ reminder_type: 'medication', deep_link: '/medication-reminder?id=7&date=2026-10-18&time=18%3A30' })).toBe('/medication-reminder?id=7&date=2026-10-18&time=18%3A30');
    expect(resolveNotificationRoute({ reminder_type: 'medication', deep_link: '/notification-detail?id=7&date=2026-10-18' })).toBe('/medication-reminder?invalid=1');
  });
  it.each([
    {}, { medication_id: '7x' }, { medication_ids: [] }, { medication_ids: [7, 'bad'] },
    { medication_ids: Array.from({ length: 51 }, (_, i) => i + 1) },
    { medication_id: 7, medication_ids: [8] },
    { medication_id: 7, scheduled_date: '2026-02-31' },
    { medication_id: 7, scheduled_time: '28:00' },
    { medication_id: 7, scheduled_timezone: 'bad-zone' },
  ])('rejects invalid occurrence without a model call or partial group: %j', fields => {
    expect(resolveNotificationRoute({ ...slot, ...fields })).toBe('/medication-reminder?invalid=1');
  });
  it('does not confuse catch-up summaries or unrelated destinations with a dose', () => {
    expect(resolveNotificationRoute({ reminder_type: 'medication_summary', deep_link: '/notification-history?detailId=81' })).toBe('/notification-history?detailId=81');
    expect(resolveNotificationRoute({ ...slot, deep_link: '/medication-edit?id=7' })).toBe('/medication-edit?id=7');
  });
});
