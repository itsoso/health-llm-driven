import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';

import DynamicTodayRenderer from '../DynamicTodayRenderer';
import type { DailyArtifact } from '../../../services/dailyArtifact';
import type { TodayDynamicView } from '../../../services/todayDynamicView';

function makeArtifact(): DailyArtifact {
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

function makeView(overrides: Partial<TodayDynamicView> = {}): TodayDynamicView {
  return {
    view_id: 'today:2026-06-29:abc',
    surface: 'mobile.today',
    trigger: 'open',
    generated_by: 'aheng_today_view_v1',
    generated_at: '2026-06-29T08:00:00Z',
    expires_at: '2026-06-29T08:01:00Z',
    context_hash: 'abc',
    safety_boundary: '健康管理行动建议,不替代医生诊断。',
    sections: [
      {
        slot: 'hero',
        priority: 100,
        cards: [{ type: 'daily_artifact', data: makeArtifact() }],
      },
      {
        slot: 'runtime',
        priority: 80,
        cards: [
          {
            type: 'runtime_agenda',
            data: {
              generated_by: 'rolling_health_runtime_v1',
              horizon_days: 7,
              next_action: {
                title: '晚餐后步行 15 分钟',
                time_window: 'evening',
                priority_tier: 'P1',
                current_state_summary: '晚餐后是今天最短的代谢干预窗口。',
                replan_reason: 'today_smart_rank',
                verification_metrics: ['waist_cm'],
                verification_window_days: 7,
              },
              // 「未来节奏」段仅在有未来日时渲染(RuntimeAgendaCard 的 visibleDays>0 门控);
              // horizon_days:7 的 runtime agenda 现实里就带日序,空数组是不真实的旧 fixture。
              days: [
                { date: '2026-06-30', next_action_title: '晚餐后步行 15 分钟', items_count: 2 },
                { date: '2026-07-01', next_action_title: '晨起拉伸', items_count: 1 },
              ],
              safety_boundary: '健康管理行动建议,不替代医生诊断。',
            },
            actions: [
              {
                id: 'open-runtime-agenda',
                label: '查看7天计划',
                action: 'route.open',
                payload: { route: '/agenda' },
                style: 'primary',
              },
            ],
          },
        ],
      },
    ],
    ...overrides,
  };
}

describe('DynamicTodayRenderer', () => {
  it('renders daily artifact and runtime agenda cards from a DynamicView', () => {
    const onAction = jest.fn();
    const { getByTestId, getByText } = render(
      <DynamicTodayRenderer view={makeView()} onCardAction={onAction} />,
    );

    expect(getByTestId('dynamic-today-view')).toBeTruthy();
    expect(getByText('阿衡动态生成的餐后步行')).toBeTruthy();
    expect(getByText('7天验证节奏')).toBeTruthy();
    expect(getByText('未来节奏')).toBeTruthy();

    fireEvent.press(getByText('查看7天计划'));
    expect(onAction).toHaveBeenCalledWith(
      expect.objectContaining({ action: 'route.open' }),
      expect.objectContaining({ type: 'runtime_agenda' }),
    );
  });

  it('ignores unknown cards without breaking the view', () => {
    const { getByText, queryByText } = render(
      <DynamicTodayRenderer
        view={makeView({
          sections: [
            { slot: 'unknown', priority: 120, cards: [{ type: 'unknown_card', data: { title: 'Bad' } }] },
            { slot: 'hero', priority: 100, cards: [{ type: 'daily_artifact', data: makeArtifact() }] },
          ],
        })}
      />,
    );

    expect(getByText('阿衡动态生成的餐后步行')).toBeTruthy();
    expect(queryByText('Bad')).toBeNull();
  });
});
