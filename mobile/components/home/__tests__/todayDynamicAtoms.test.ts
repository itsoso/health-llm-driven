import type { DailyArtifact } from '../../../services/dailyArtifact';
import type { TodayDynamicView } from '../../../services/todayDynamicView';
import {
  collectTodayDynamicPromotedTitleKeys,
  resolveTodayDynamicAtom,
  shouldRenderTodayDynamicCard,
} from '../todayDynamicAtoms';

function artifact(): DailyArtifact {
  return {
    artifact_date: '2026-06-29',
    empty_state: false,
    state: { label: '今日最重要行动', tone: 'focused', summary: '阿衡已生成今日行动。' },
    top_action: {
      id: 'walk',
      title: '阿衡动态生成的餐后步行',
      why_now: '餐后窗口优先。',
      actions: { complete: { enabled: false }, skip: { requires_reason: true } },
    },
    evidence: [],
    confidence: 'medium',
    freshness: { status: 'fresh', sources: ['agenda.runtime_range'] },
    safety_boundary: '健康管理行动建议,不替代医生诊断。',
  };
}

function view(): TodayDynamicView {
  return {
    view_id: 'today:2026-06-29:abc',
    surface: 'mobile.today',
    trigger: 'open',
    generated_by: 'aheng_today_view_v1',
    context_hash: 'abc',
    sections: [
      {
        slot: 'hero',
        priority: 100,
        cards: [{
          id: 'daily-artifact:2026-06-29:walk',
          type: 'agent_atom',
          render: { atom: 'daily_artifact', reason: 'primary_today_action' },
          data: artifact(),
        }],
      },
    ],
  };
}

describe('todayDynamicAtoms', () => {
  it('resolves the closed atom from render metadata before falling back to type', () => {
    expect(resolveTodayDynamicAtom({ type: 'agent_atom', render: { atom: 'daily_artifact' }, data: {} })).toBe('daily_artifact');
    expect(resolveTodayDynamicAtom({ type: 'runtime_agenda', data: {} })).toBe('runtime_agenda');
    expect(resolveTodayDynamicAtom({
      type: 'runtime_agenda',
      render: { atom: 'future_runtime_agenda' },
      data: {},
    })).toBe('runtime_agenda');
  });

  it('collects promoted DailyArtifact titles from generic atom envelopes', () => {
    const keys = collectTodayDynamicPromotedTitleKeys(view());

    expect(keys.has('阿衡动态生成的餐后步行')).toBe(true);
  });

  it('suppresses runtime atoms when the DailyArtifact already owns the primary action', () => {
    const promotedTitles = collectTodayDynamicPromotedTitleKeys(view());
    const shouldRender = shouldRenderTodayDynamicCard({
      id: 'runtime-agenda:2026-06-29:walk',
      type: 'agent_atom',
      render: { atom: 'runtime_agenda' },
      data: {
        next_action: { title: '阿衡动态生成的餐后步行' },
      },
    }, promotedTitles);

    expect(shouldRender).toBe(false);
  });
});
