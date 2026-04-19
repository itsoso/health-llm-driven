import { describe, expect, it } from 'vitest';

import {
  DASHBOARD_CARD_IDS,
  getDefaultDashboardLayout,
  getWelcomeContentBottomPaddingClass,
  normalizeDashboardLayout,
} from '../dashboardLayout';

describe('dashboardLayout', () => {
  it('returns a complete default layout', () => {
    expect(getDefaultDashboardLayout()).toEqual({
      order: [...DASHBOARD_CARD_IDS],
      hidden: [],
    });
  });

  it('normalizes partial layouts and preserves valid ids only', () => {
    expect(normalizeDashboardLayout({
      order: ['trends', 'hero', 'hero', 'unknown'],
      hidden: ['action_cards', 'missing', 'action_cards'],
    })).toEqual({
      order: [
        'trends',
        'hero',
        'safety',
        'consultations',
        'action_cards',
        'specialists',
        'alerts',
        'data_grid',
        'strength',
        'workout_supplement',
        'supplement_guide',
        'activity',
        'exercise',
        'quick_asks',
      ],
      hidden: ['action_cards'],
    });
  });

  it('uses larger bottom padding on mobile when footer controls are shown', () => {
    expect(getWelcomeContentBottomPaddingClass({ isMobile: false, hasFooterControls: false })).toBe('pb-44');
    expect(getWelcomeContentBottomPaddingClass({ isMobile: true, hasFooterControls: false })).toBe('pb-56');
    expect(getWelcomeContentBottomPaddingClass({ isMobile: true, hasFooterControls: true })).toBe('pb-72');
  });
});
