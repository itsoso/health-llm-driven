jest.mock('../api', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn() },
}));

import api from '../api';
import { getSmartAgendaToday } from '../agenda';

const mockApi = api as unknown as {
  get: jest.Mock;
  post: jest.Mock;
};

describe('agenda service', () => {
  beforeEach(() => jest.clearAllMocks());

  it('loads smart agenda with explicit mode and max_items params', async () => {
    mockApi.get.mockResolvedValue({
      data: {
        agenda_date: '2026-06-22',
        mode: 'smart',
        count: 1,
        source_count: 3,
        items: [],
        smart: {
          top_items: [
            {
              id: 'smart_daily_plan_action_movement.moderate_activity',
              type: 'movement',
              title: '累计 35-45 分钟中等强度活动',
              status: 'pending',
              priority: 65,
              source: { object_type: 'daily_plan_action', object_id: 'movement.moderate_activity' },
              why_now: '对齐每周 150 分钟中等强度活动的代谢健康目标。',
              do_now: '执行: 累计 35-45 分钟中等强度活动',
              verify_by: { metrics: ['weight', 'waist_cm'], window_days: 7 },
              replan_policy: { on_skip: 'capture_reason_then_reschedule' },
              surface: { primary: 'watch', alternates: ['mobile', 'rokid'] },
              autonomy_tier: 'suggest',
              can_complete: true,
              can_snooze: true,
              can_skip: true,
            },
          ],
        },
      },
    });

    const agenda = await getSmartAgendaToday(4);

    expect(mockApi.get).toHaveBeenCalledWith('/agenda/today', {
      params: { mode: 'smart', max_items: 4 },
    });
    expect(agenda.mode).toBe('smart');
    expect(agenda.smart.top_items[0].surface.primary).toBe('watch');
  });
});
