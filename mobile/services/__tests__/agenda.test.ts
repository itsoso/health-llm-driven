jest.mock('../api', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn() },
}));

import api from '../api';
import { completeAgendaItem, getSmartAgendaToday } from '../agenda';

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

  describe('completeAgendaItem', () => {
    beforeEach(() => mockApi.post.mockResolvedValue({ data: { wrote: true } }));

    it('defaults to status done (existing callers unchanged, no skip_reason)', async () => {
      await completeAgendaItem({ object_type: 'health_protocol', object_id: 42 });

      expect(mockApi.post).toHaveBeenCalledWith('/agenda/complete', {
        object_type: 'health_protocol',
        object_id: 42,
        status: 'done',
        track: 'protocol',
        value: null,
      });
      // done path must NOT carry skip_reason
      expect(mockApi.post.mock.calls[0][1]).not.toHaveProperty('skip_reason');
    });

    it('passes status skipped + skip_reason when skipping', async () => {
      await completeAgendaItem(
        { object_type: 'medication', object_id: 7 },
        'protocol',
        undefined,
        { status: 'skipped', skipReason: 'forgot' },
      );

      expect(mockApi.post).toHaveBeenCalledWith('/agenda/complete', {
        object_type: 'medication',
        object_id: 7,
        status: 'skipped',
        skip_reason: 'forgot',
        track: 'protocol',
        value: null,
      });
    });

    it('skipped without a reason defaults to no_time', async () => {
      await completeAgendaItem(
        { object_type: 'supplement', object_id: 3 },
        'protocol',
        undefined,
        { status: 'skipped' },
      );

      expect(mockApi.post.mock.calls[0][1]).toMatchObject({
        status: 'skipped',
        skip_reason: 'no_time',
      });
    });

    it('rejects non-numeric object_id before posting completion payload', async () => {
      await expect(
        completeAgendaItem({ object_type: 'medication', object_id: 'med_7' }),
      ).rejects.toThrow('agenda object_id must be numeric');

      expect(mockApi.post).not.toHaveBeenCalled();
    });

    it('keeps manual-track value passthrough alongside status', async () => {
      await completeAgendaItem(
        { object_type: 'health_protocol', object_id: 9 },
        'manual',
        { volume_ml: 500 },
      );

      expect(mockApi.post).toHaveBeenCalledWith('/agenda/complete', {
        object_type: 'health_protocol',
        object_id: 9,
        status: 'done',
        track: 'manual',
        value: { volume_ml: 500 },
      });
    });
  });
});
