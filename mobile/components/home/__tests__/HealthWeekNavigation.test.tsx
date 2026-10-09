import React from 'react';
import { render, waitFor } from '@testing-library/react-native';
import { fetchHealthWeekNavigation, fetchHealthNavigationGrants } from '../../../services/healthNavigation';
jest.mock('expo-router', () => ({
  useRouter: () => ({ push: jest.fn() }), Stack: { Screen: () => null },
  useFocusEffect: (callback: () => void) => { require('react').useEffect(callback, [callback]); },
}));
jest.mock('../../../services/healthNavigation', () => ({
  ...jest.requireActual('../../../services/healthNavigation'), fetchHealthWeekNavigation: jest.fn(), fetchHealthNavigationGrants: jest.fn(),
}));
import HealthWeekNavigation from '../HealthWeekNavigation';
describe('Health week navigation', () => {
  beforeEach(() => {
    (fetchHealthNavigationGrants as jest.Mock).mockResolvedValue([]);
  });
  it('shows the fixed rolling window and record coverage without a misleading percentage', async () => {
    (fetchHealthWeekNavigation as jest.Mock).mockResolvedValue({
      availability: 'ready', timezone: 'Asia/Shanghai', timezone_source: 'user', source_as_of: '2026-10-09T08:00:00Z',
      review_window: { start_date: '2026-10-03', end_date: '2026-10-09' }, actions: [],
      review: { recorded_days: 2, window_days: 7, completed_occurrences: 2, skipped_occurrences: 1, deferred_occurrences: 0, unknown_occurrences: 3, claim_boundary: '观察记录不证明健康改善。' },
    });
    const view = render(<HealthWeekNavigation />);
    await waitFor(() => expect(view.getByText('2026-10-03 → 2026-10-09 · 含今天的滚动 7 天')).toBeTruthy());
    expect(view.getByText('已记录 2/7 天')).toBeTruthy();
    expect(view.queryByText(/完成率|%/)).toBeNull();
    expect(view.getByText('观察记录不证明健康改善。')).toBeTruthy();
  });
  it('clears an expired projection from page memory and asks for a fresh read', async () => {
    (fetchHealthWeekNavigation as jest.Mock).mockResolvedValue({
      availability: 'ready', expires_at: '2000-01-01T00:00:00Z', actions: [],
      review_window: { start_date: '1999-12-26', end_date: '2000-01-01' },
      review: { recorded_days: 2, window_days: 7, completed_occurrences: 2, skipped_occurrences: 1, deferred_occurrences: 0, unknown_occurrences: 3 },
    });
    const view = render(<HealthWeekNavigation />);
    await waitFor(() => view.getByText('健康摘要已过期，请更新或重新读取。'));
    expect(view.queryByText('已记录 2/7 天')).toBeNull();
  });
  it('keeps not generated distinct from a zero completion record', async () => {
    (fetchHealthWeekNavigation as jest.Mock).mockResolvedValue({ availability: 'not_generated', actions: [], review: {}, review_window: {} });
    const view = render(<HealthWeekNavigation />);
    await waitFor(() => view.getByText('尚未生成可用的健康行动快照。'));
    expect(view.queryByText(/已完成 0/)).toBeNull();
  });
});
