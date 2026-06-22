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
