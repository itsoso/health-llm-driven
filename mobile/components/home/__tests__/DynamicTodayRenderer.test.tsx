import React from 'react';
import { Alert } from 'react-native';
import { act, fireEvent, render, waitFor } from '@testing-library/react-native';

import DynamicTodayRenderer from '../DynamicTodayRenderer';
import type { DailyArtifact } from '../../../services/dailyArtifact';
import type { TodayDynamicView } from '../../../services/todayDynamicView';

function makeArtifact(): DailyArtifact {
  return {
    artifact_date: '2026-06-29',
    empty_state: false,
    state: { label: '今日最重要行动', tone: 'focused', summary: '小巴已生成今日行动。' },
    top_action: {
      id: 'walk',
      title: '小巴动态生成的餐后步行',
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
  it('renders the daily artifact as the single primary home card and suppresses the expanded runtime agenda', () => {
    const onAction = jest.fn();
    const { getByTestId, getByText, queryByText } = render(
      <DynamicTodayRenderer view={makeView()} onCardAction={onAction} />,
    );

    expect(getByTestId('dynamic-today-view')).toBeTruthy();
    expect(getByText('小巴动态生成的餐后步行')).toBeTruthy();
    expect(queryByText('7天验证节奏')).toBeNull();
    expect(queryByText('未来节奏')).toBeNull();
    expect(queryByText('查看7天计划')).toBeNull();
    expect(onAction).not.toHaveBeenCalled();
  });

  it('renders a DailyArtifact atom from render metadata even when the envelope type is generic', () => {
    const { getByTestId, getByText } = render(
      <DynamicTodayRenderer
        view={makeView({
          sections: [
            {
              slot: 'hero',
              priority: 100,
              cards: [
                {
                  id: 'daily-artifact:2026-06-29:walk',
                  type: 'agent_atom',
                  render: { atom: 'daily_artifact', reason: 'primary_today_action' },
                  data: makeArtifact(),
                },
              ],
            },
          ],
        })}
      />,
    );

    expect(getByTestId('dynamic-today-view')).toBeTruthy();
    expect(getByText('小巴动态生成的餐后步行')).toBeTruthy();
  });

  it('renders a registered runtime atom from render metadata when the envelope type is generic', () => {
    const { getByText } = render(
      <DynamicTodayRenderer
        view={makeView({
          sections: [
            {
              slot: 'runtime',
              priority: 80,
              cards: [
                {
                  id: 'runtime-agenda:2026-06-29:walk',
                  type: 'agent_atom',
                  render: { atom: 'runtime_agenda', reason: 'next_runtime_action' },
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
                    days: [
                      { date: '2026-06-30', next_action_title: '晚餐后步行 15 分钟', items_count: 2 },
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
        })}
      />,
    );

    expect(getByText('今天先做')).toBeTruthy();
    expect(getByText('晚餐后步行 15 分钟')).toBeTruthy();
  });

  it('falls back to the registered card type when render metadata names an unknown atom', async () => {
    const onAction = jest.fn();
    const { getByText } = render(
      <DynamicTodayRenderer
        view={makeView({
          sections: [
            {
              slot: 'runtime',
              priority: 80,
              cards: [
                {
                  id: 'runtime-agenda:2026-06-29:walk',
                  type: 'runtime_agenda',
                  render: { atom: 'future_runtime_agenda', reason: 'experimental_renderer' },
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
                    days: [
                      { date: '2026-06-30', next_action_title: '晚餐后步行 15 分钟', items_count: 2 },
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
        })}
        onCardAction={onAction}
      />,
    );

    expect(getByText('今天先做')).toBeTruthy();
    expect(getByText('晚餐后步行 15 分钟')).toBeTruthy();
    await act(async () => {
      fireEvent.press(getByText('查看7天计划'));
    });
    expect(onAction).toHaveBeenCalledWith(
      expect.objectContaining({ action: 'route.open' }),
      expect.objectContaining({ type: 'runtime_agenda' }),
    );
  });

  it('shows running feedback and prevents duplicate dynamic card actions', async () => {
    let resolveAction: (() => void) | null = null;
    const onAction = jest.fn(() => new Promise<void>((resolve) => {
      resolveAction = resolve;
    }));
    const { getByText } = render(
      <DynamicTodayRenderer
        view={makeView({
          sections: [
            {
              slot: 'runtime',
              priority: 80,
              cards: [
                {
                  id: 'runtime-agenda:2026-06-29:walk',
                  type: 'agent_atom',
                  render: { atom: 'runtime_agenda', reason: 'next_runtime_action' },
                  data: {
                    generated_by: 'rolling_health_runtime_v1',
                    horizon_days: 7,
                    next_action: {
                      title: '晚餐后步行 15 分钟',
                      time_window: 'evening',
                      priority_tier: 'P1',
                      current_state_summary: '晚餐后是今天最短的代谢干预窗口。',
                      verification_metrics: ['waist_cm'],
                      verification_window_days: 7,
                    },
                    days: [
                      { date: '2026-06-30', next_action_title: '晚餐后步行 15 分钟', items_count: 2 },
                    ],
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
        })}
        onCardAction={onAction}
      />,
    );

    fireEvent.press(getByText('查看7天计划'));

    await waitFor(() => {
      expect(getByText('执行中')).toBeTruthy();
    });
    fireEvent.press(getByText('执行中'));
    expect(onAction).toHaveBeenCalledTimes(1);

    await act(async () => {
      resolveAction?.();
    });

    await waitFor(() => {
      expect(getByText('已打开')).toBeTruthy();
    });
  });

  it('requires visible confirmation before a Today write action runs', async () => {
    const onAction = jest.fn().mockResolvedValue(undefined);
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation((title, message, buttons) => {
      expect(title).toBe('确认完成？');
      expect(message).toContain('记录为已完成');
      buttons?.find(button => button.text === '确认完成')?.onPress?.();
    });
    const view = makeView({
      sections: [{
        slot: 'runtime',
        priority: 80,
        cards: [{
          id: 'runtime-agenda:today:intervention.card.9',
          type: 'runtime_agenda',
          data: {
            presentation_mode: 'today',
            next_action: { title: '散步 10 分钟', verification_window_days: 1 },
            days: [],
          },
          actions: [{
            id: 'complete-runtime-action',
            label: '完成这一步',
            action: 'daily_plan_action.complete',
            endpoint: '/daily-plan/actions/intervention.card.9/events',
            requires_manual_confirm: true,
            capability_id: 'runtime_agenda.v1',
            required_receipt: true,
            autonomy_tier: 'manual_confirm',
            policy_reason: 'manual_confirm_write',
            payload: { action_id: 'intervention.card.9', event_type: 'completed' },
            confirmation: {
              title: '确认完成？',
              detail: '确认后会将“散步 10 分钟”记录为已完成。',
              confirm_label: '确认完成',
              cancel_label: '取消',
            },
          }],
        }],
      }],
    });
    const { getByText } = render(
      <DynamicTodayRenderer view={view} onCardAction={onAction} />,
    );

    fireEvent.press(getByText('完成这一步'));

    await waitFor(() => expect(onAction).toHaveBeenCalledTimes(1));
    expect(alertSpy).toHaveBeenCalledTimes(1);
    alertSpy.mockRestore();
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

    expect(getByText('小巴动态生成的餐后步行')).toBeTruthy();
    expect(queryByText('Bad')).toBeNull();
  });

  it('ignores unregistered chat cards instead of rendering the full Chat CARD_MAP on Today', () => {
    const { getByText, queryByText } = render(
      <DynamicTodayRenderer
        view={makeView({
          sections: [
            { slot: 'hero', priority: 100, cards: [{ type: 'daily_artifact', data: makeArtifact() }] },
            {
              slot: 'insights',
              priority: 70,
              cards: [
                {
                  type: 'discovery',
                  data: {
                    title: '小巴动态生成的餐后步行',
                    summary: 'Chat 卡片不应该绕过 Today atom registry。',
                  },
                },
                {
                  type: 'discovery',
                  data: {
                    title: '最近睡眠连续性变好',
                    summary: '即使不是重复题,也不能绕过 Today atom registry。',
                  },
                },
              ],
            },
          ],
        })}
      />,
    );

    expect(getByText('小巴动态生成的餐后步行')).toBeTruthy();
    expect(queryByText('Chat 卡片不应该绕过 Today atom registry。')).toBeNull();
    expect(queryByText('最近睡眠连续性变好')).toBeNull();
    expect(queryByText('即使不是重复题,也不能绕过 Today atom registry。')).toBeNull();
  });
});
