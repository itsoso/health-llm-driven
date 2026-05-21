import { describe, expect, it } from 'vitest';
import { resolveNotificationHref } from '../NotificationCenter';

describe('resolveNotificationHref', () => {
  it('maps mobile workout-detail deep links to the web workout detail route', () => {
    expect(resolveNotificationHref({
      notification_type: 'workout_analysis',
      deep_link: '/workout-detail?id=123',
    })).toBe('/workout?id=123');
  });

  it('uses workout_id data as a fallback for workout notifications', () => {
    expect(resolveNotificationHref({
      notification_type: 'workout_analysis',
      data: { workout_id: 456 },
    })).toBe('/workout?id=456');
  });
});
