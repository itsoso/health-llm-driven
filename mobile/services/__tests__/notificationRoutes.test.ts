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
    expect(resolveNotificationRoute(data)).toMatch(/^\/\(tabs\)\/chat\?prompt=/);
  });
  it('preserves a specific destination and unrelated record notifications', () => {
    expect(resolveNotificationRoute({ reminder_type: 'medication', deep_link: '/medication-edit?id=7' })).toBe('/medication-edit?id=7');
    expect(resolveNotificationRoute({ deep_link: '/(tabs)/record' })).toBe('/(tabs)/record');
  });
});


describe('precise medication reminder target', () => {
  it('carries remote occurrence without private display fields', () => {
    const route = resolveNotificationRoute({ reminder_type: 'medication', medication_id: 7, scheduled_date: '2026-10-16', scheduled_time: '18:00', scheduled_timezone: 'Asia/Shanghai', medication_name: 'secret', dosage: 'secret', deep_link: '/medications' })!;
    const params = new URLSearchParams(route.split('?')[1]);
    expect(params.has('context')).toBe(false);
    expect(params.get('prompt')).toContain('2026-10-16 18:00 （北京时间）');
    expect(decodeURIComponent(route)).not.toContain('secret');
  });
  it('preserves original local slot and leaves date unconfirmed', () => {
    const route = resolveNotificationRoute({ kind: 'medication_reminder', medication_id: 7, taken_time: '06:00', scheduled_time: '08:00', deep_link: '/medications' })!;
    expect(new URLSearchParams(route.split('?')[1]).get('prompt')).toContain('日期未确认 06:00');
  });
  it('does not infer an id or use malformed time/date', () => {
    const route = resolveNotificationRoute({ reminder_type: 'medication', medication_id: '7x', scheduled_date: '2026-02-31', scheduled_time: '28:00' })!;
    expect(new URLSearchParams(route.split('?')[1]).get('prompt')).toContain('通知信息不完整');
  });
});

describe('medication reminder Agent destination', () => {
  it.each(['/medications', '/medication-reminder?id=7&date=2026-10-18&time=18%3A30', '/(tabs)/chat'])('opens a draft for %s without automatic send or private text', (deep_link) => {
    const route = resolveNotificationRoute({ reminder_type: 'medication', medication_id: 7, scheduled_date: '2026-10-18', scheduled_time: '18:30', scheduled_timezone: 'Asia/Shanghai', deep_link, medication_name: 'private-secret' })!;
    expect(route.split('?')[0]).toBe('/(tabs)/chat');
    const params = new URLSearchParams(route.split('?')[1]);
    expect(params.get('prompt')).toContain('2026-10-18');
    expect(params.get('prompt')).toContain('18:30');
    expect(params.has('autoSend')).toBe(false);
    expect(params.has('context')).toBe(false);
    expect(decodeURIComponent(route)).not.toContain('private-secret');
  });
  it('old date-less local notices do not invent today or authorize taking medication', () => {
    const route = resolveNotificationRoute({ kind: 'medication_reminder', medication_id: 7, taken_time: '18:30' })!;
    expect(route.split('?')[0]).toBe('/(tabs)/chat');
    expect(new URLSearchParams(route.split('?')[1]).get('prompt')).toContain('日期未确认');
  });
});

 it('routes old medication pre-event notifications to an unsent Agent draft', () => {
    const route = resolveNotificationRoute({ reminder_type: 'pre_event', kind: 'medication', category: 'AGENDA_ACTION', deep_link: '/(tabs)/record', complete_ref: { object_type: 'medication', object_id: 7, slot: '18:30' }, item_title: 'private' })!;
    expect(route.split('?')[0]).toBe('/(tabs)/chat');
    expect(new URLSearchParams(route.split('?')[1]).get('prompt')).toContain('日期未确认');
    expect(new URLSearchParams(route.split('?')[1]).has('context')).toBe(false);
    expect(decodeURIComponent(route)).not.toContain('private');
 });

 it('retains validated non-China reminder timezone without passing a context payload', () => {
   const route = resolveNotificationRoute({ reminder_type: 'medication', scheduled_date: '2026-10-18', scheduled_time: '18:30', scheduled_timezone: 'America/New_York' })!;
   expect(new URLSearchParams(route.split('?')[1]).get('prompt')).toContain('America/New_York');
   expect(new URLSearchParams(route.split('?')[1]).has('context')).toBe(false);
 });
