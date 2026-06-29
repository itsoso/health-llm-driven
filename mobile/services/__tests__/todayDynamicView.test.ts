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
});
