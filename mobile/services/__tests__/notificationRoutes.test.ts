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
  it.each([
    { reminder_type: 'medication', screen: 'home' },
    { kind: 'medication_reminder', screen: 'home' },
    { category: 'MEDICATION_REMINDER', deep_link: '/(tabs)/record' },
    { reminder_type: 'medication', deep_link: 'health://(tabs)/record' },
    { reminder_type: 'medication', deep_link: '/(tabs)' },
    { reminder_type: 'medication' },
  ])('opens medications for existing reminder payload %j', (data) => {
    expect(resolveNotificationRoute(data)).toBe('/medication-reminder');
  });
  it('preserves a specific destination and unrelated record notifications', () => {
    expect(resolveNotificationRoute({ reminder_type: 'medication', deep_link: '/medication-edit?id=7' })).toBe('/medication-edit?id=7');
    expect(resolveNotificationRoute({ deep_link: '/(tabs)/record' })).toBe('/(tabs)/record');
  });
});


describe('precise medication reminder target', () => {
  it('carries remote occurrence without private display fields', () => {
    expect(resolveNotificationRoute({ reminder_type: 'medication', medication_id: 7, scheduled_date: '2026-10-16', scheduled_time: '18:00', scheduled_timezone: 'Asia/Shanghai', medication_name: 'secret', dosage: 'secret', deep_link: '/medications' })).toBe('/medication-reminder?id=7&date=2026-10-16&time=18%3A00&sourceTimezone=Asia%2FShanghai');
  });
  it('preserves original local slot and leaves date unconfirmed', () => {
    expect(resolveNotificationRoute({ kind: 'medication_reminder', medication_id: 7, taken_time: '06:00', scheduled_time: '08:00', deep_link: '/medications' })).toBe('/medication-reminder?id=7&time=06%3A00');
  });
  it('does not infer an id or use malformed time/date', () => {
    expect(resolveNotificationRoute({ reminder_type: 'medication', medication_id: '7x', scheduled_date: '2026-02-31', scheduled_time: '28:00' })).toBe('/medication-reminder?invalid=1');
  });
});
