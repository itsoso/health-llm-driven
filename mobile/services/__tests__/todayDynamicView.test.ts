import api from '../api';
import {
  getTodayDynamicView,
  hasRenderableTodayDynamicView,
  normalizeTodayDynamicView,
} from '../todayDynamicView';

jest.mock('../api', () => ({
  post: jest.fn(),
}));

describe('todayDynamicView service', () => {
  beforeEach(() => jest.clearAllMocks());

  it('posts the mobile.today surface and normalizes a dynamic view', async () => {
    (api.post as jest.Mock).mockResolvedValue({
      data: {
        view_id: 'today:2026-06-29:abc',
        surface: 'mobile.today',
        trigger: 'pull_refresh',
        generated_by: 'aheng_today_view_v1',
        context_hash: 'abc',
        sections: [
          {
            slot: 'runtime',
            priority: 80,
            cards: [{ type: 'runtime_agenda', data: { horizon_days: 7 } }],
          },
        ],
      },
    });

    const view = await getTodayDynamicView({
      trigger: 'pull_refresh',
      clientContext: { timezone: 'Asia/Shanghai' },
    });

    expect(api.post).toHaveBeenCalledWith('/dynamic-views/today', {
      trigger: 'pull_refresh',
      surface: 'mobile.today',
      client_context: { timezone: 'Asia/Shanghai' },
    });
    expect(view.surface).toBe('mobile.today');
    expect(view.sections[0].cards[0].type).toBe('runtime_agenda');
    expect(hasRenderableTodayDynamicView(view)).toBe(true);
  });

  it('filters malformed sections and cards without crashing', () => {
    const view = normalizeTodayDynamicView({
      view_id: '',
      surface: 'mobile.today',
      trigger: 'bad' as any,
      generated_by: '',
      context_hash: 12 as any,
      sections: [
        null as any,
        { slot: '', priority: 20, cards: [{ type: 'runtime_agenda', data: {} }] },
        { slot: 'hero', priority: 100, cards: [{ type: '', data: {} }] },
        { slot: 'runtime', priority: 80, cards: [{ type: 'runtime_agenda', data: null }] },
      ],
    });

    expect(view.view_id).toBe('today:empty');
    expect(view.trigger).toBe('open');
    expect(view.context_hash).toBe('');
    expect(view.sections).toHaveLength(1);
    expect(view.sections[0].slot).toBe('runtime');
    expect(view.sections[0].cards[0].data).toEqual({});
    expect(hasRenderableTodayDynamicView(view)).toBe(true);
    expect(hasRenderableTodayDynamicView(normalizeTodayDynamicView(null))).toBe(false);
  });

  it('preserves server card identity and render metadata for atom composition', () => {
    const view = normalizeTodayDynamicView({
      view_id: 'today:2026-06-29:abc',
      surface: 'mobile.today',
      trigger: 'open',
      generated_by: 'aheng_today_view_v1',
      context_hash: 'abc',
      sections: [
        {
          slot: 'hero',
          priority: 100,
          cards: [
            {
              id: 'daily-artifact:2026-06-29:walk',
              type: 'daily_artifact',
              data: { artifact_date: '2026-06-29' },
              render: {
                atom: 'daily_artifact',
                dedupe_key: 'action:walk',
                reason: 'primary_today_action',
              },
            } as any,
          ],
        },
      ],
    });

    expect(view.sections[0].cards[0].id).toBe('daily-artifact:2026-06-29:walk');
    expect(view.sections[0].cards[0].render).toEqual({
      atom: 'daily_artifact',
      dedupe_key: 'action:walk',
      reason: 'primary_today_action',
    });
  });

  it('keeps only safe dynamic card actions for Today view cards', () => {
    const view = normalizeTodayDynamicView({
      view_id: 'today:2026-06-29:abc',
      surface: 'mobile.today',
      trigger: 'open',
      generated_by: 'aheng_today_view_v1',
      context_hash: 'abc',
      sections: [
        {
          slot: 'hero',
          priority: 100,
          cards: [
            {
              type: 'runtime_agenda',
              data: {},
              actions: [
                {
                  label: '打开外部站点',
                  action: 'route.open',
                  payload: { route: '//example.test/path' },
                },
                {
                  label: '缺少确认',
                  action: 'agenda.complete',
                  endpoint: '/agenda/complete',
                  payload: { source: { object_type: 'health_protocol', object_id: 7 } },
                },
                {
                  label: '打开小巴',
                  action: 'route.open',
                  payload: { route: '/(tabs)/chat?prompt=hrv' },
                },
                {
                  label: '确认完成',
                  action: 'agenda.complete',
                  endpoint: '/agenda/complete',
                  requires_manual_confirm: true,
                  capability_id: 'runtime_agenda.v1',
                  required_receipt: true,
                  autonomy_tier: 'manual_confirm',
                  policy_reason: 'manual_confirm_write',
                  payload: { source: { object_type: 'health_protocol', object_id: 7 } },
                },
                {
                  label: '完成今天行动',
                  action: 'daily_plan_action.complete',
                  endpoint: '/daily-plan/actions/intervention.card.9/events',
                  requires_manual_confirm: true,
                  capability_id: 'runtime_agenda.v1',
                  required_receipt: true,
                  autonomy_tier: 'manual_confirm',
                  policy_reason: 'manual_confirm_write',
                  payload: { action_id: 'intervention.card.9', event_type: 'completed' },
                  confirmation: { title: '确认完成？', confirm_label: '确认完成' },
                },
              ],
            } as any,
          ],
        },
      ],
    });

    expect(view.sections[0].cards[0].actions).toEqual([
      expect.objectContaining({ action: 'route.open', payload: { route: '/(tabs)/chat?prompt=hrv' } }),
      expect.objectContaining({ action: 'agenda.complete', requires_manual_confirm: true }),
      expect.objectContaining({ action: 'daily_plan_action.complete', requires_manual_confirm: true }),
    ]);
  });
});
