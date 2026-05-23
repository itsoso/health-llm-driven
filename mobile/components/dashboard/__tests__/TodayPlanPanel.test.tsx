/* eslint-disable @typescript-eslint/no-require-imports, import/first */
import React from 'react';
import { fireEvent, render, waitFor } from '@testing-library/react-native';

jest.mock('../../../services/api', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn() },
}));

jest.mock('../../../components/knowledge', () => {
  const React = require('react');
  const { Text } = require('react-native');
  return {
    EvidenceRefsRow: ({ refs }: { refs?: unknown[] | null }) => (
      Array.isArray(refs) && refs.length > 0 ? <Text>系统证据 {refs.length}</Text> : null
    ),
  };
});

import api from '../../../services/api';
import TodayPlanPanel from '../TodayPlanPanel';
import type { DailyOperatingPlan } from '../../../services/dailyPlan';

describe('TodayPlanPanel', () => {
  it('shows recovery mode when acute illness pauses training', () => {
    const plan: DailyOperatingPlan = {
      plan_date: '2026-05-18',
      primary_goal: 'metabolic_health',
      status: 'active',
      state_summary: {
        acute: {
          should_rest_from_training: true,
          illness_names: ['感冒'],
          training_guardrail: '感冒/上呼吸道症状期不要求完成运动目标；优先休息、补水和睡眠。',
        },
      },
      actions: [
        {
          domain: 'movement',
          title: '暂停训练，优先恢复',
          why: '感冒/上呼吸道症状期不要求完成运动目标；优先休息、补水和睡眠。',
          when: 'today',
        },
      ],
    };

    const { getAllByText, getByText } = render(<TodayPlanPanel plan={plan} />);

    expect(getByText('恢复模式')).toBeTruthy();
    expect(getByText('感冒')).toBeTruthy();
    expect(getAllByText('感冒/上呼吸道症状期不要求完成运动目标；优先休息、补水和睡眠。').length).toBeGreaterThan(0);
    expect(getByText('暂停训练，优先恢复')).toBeTruthy();
  });

  it('renders action controls, evidence, and verification metric', () => {
    const plan: DailyOperatingPlan = {
      plan_date: '2026-05-18',
      primary_goal: 'metabolic_health',
      status: 'active',
      state_summary: {},
      actions: [
        {
          action_key: 'sleep.dinner_cutoff',
          domain: 'sleep',
          title: '睡前 3 小时停止正餐',
          why: '晚餐过晚会干扰睡眠和第二天恢复。',
          when: 'evening',
          evidence_level: 'high',
          evidence_refs: ['claim:c_sleep_meal_timing'],
          verification: { metric: 'sleep_score', window_days: 7 },
        } as any,
      ],
    };

    const { getByText } = render(<TodayPlanPanel plan={plan} />);

    expect(getByText('接受')).toBeTruthy();
    expect(getByText('调整')).toBeTruthy();
    expect(getByText('完成')).toBeTruthy();
    expect(getByText('跳过')).toBeTruthy();
    expect(getByText('强证据')).toBeTruthy();
    expect(getByText('系统证据 1')).toBeTruthy();
    expect(getByText('验证 sleep_score · 7天')).toBeTruthy();
  });

  it('can exclude the already promoted primary action', () => {
    const plan: DailyOperatingPlan = {
      plan_date: '2026-05-18',
      primary_goal: 'metabolic_health',
      status: 'active',
      state_summary: {},
      actions: [
        {
          action_key: 'measurement.weight_waist_morning',
          domain: 'measurement',
          title: '晨起记录体重和腰围',
          why: '同一时间测量噪声更低。',
        } as any,
        {
          action_key: 'nutrition.protein_target',
          domain: 'nutrition',
          title: '今天蛋白质目标',
          why: '优先补齐蛋白质。',
        } as any,
      ],
    };

    const { getByText, queryByText } = render(
      <TodayPlanPanel plan={plan} excludeActionKey="measurement.weight_waist_morning" />,
    );

    expect(queryByText('晨起记录体重和腰围')).toBeNull();
    expect(getByText('今天蛋白质目标')).toBeTruthy();
  });

  it('renders a compact remaining-plan queue without feedback controls', () => {
    const onPressAction = jest.fn();
    const plan: DailyOperatingPlan = {
      plan_date: '2026-05-18',
      primary_goal: 'metabolic_health',
      status: 'active',
      state_summary: {},
      actions: [
        {
          action_key: 'measurement.weight_waist_morning',
          domain: 'measurement',
          title: '晨起记录体重和腰围',
          why: '同一时间测量噪声更低。',
        } as any,
        {
          action_key: 'nutrition.protein_target',
          domain: 'nutrition',
          title: '今天蛋白质目标',
          why: '减重阶段先保住蛋白和肌肉量。',
          when: 'meals',
          verification: { metric: 'body_fat', window_days: 14 },
        } as any,
        {
          action_key: 'sleep.bedtime',
          domain: 'sleep',
          title: '23:00 上床',
          why: '稳定睡眠窗口。',
        } as any,
      ],
    };

    const { getByText, queryByText } = render(
      <TodayPlanPanel
        plan={plan}
        compact
        title="余下计划"
        excludeActionKey="measurement.weight_waist_morning"
        onPressAction={onPressAction}
      />,
    );

    expect(getByText('余下计划')).toBeTruthy();
    expect(getByText('除当前重点外，还有 2 件事')).toBeTruthy();
    expect(getByText('今天蛋白质目标')).toBeTruthy();
    expect(getByText('影响 体脂')).toBeTruthy();
    expect(getByText('今天')).toBeTruthy();
    expect(queryByText('晨起记录体重和腰围')).toBeNull();
    expect(queryByText('接受')).toBeNull();
    expect(queryByText('完成')).toBeNull();

    fireEvent.press(getByText('今天蛋白质目标'));

    expect(onPressAction).toHaveBeenCalledWith(expect.objectContaining({
      action_key: 'nutrition.protein_target',
    }));
  });

  it('records completed event for a daily plan action', async () => {
    (api.post as jest.Mock).mockResolvedValueOnce({
      data: {
        id: 1,
        plan_date: '2026-05-18',
        action_id: 'measurement.weight_waist_morning',
        action_title: '晨起记录体重和腰围',
        event_type: 'completed',
        action_state: 'completed',
        payload: {},
      },
    });
    const plan: DailyOperatingPlan = {
      plan_date: '2026-05-18',
      primary_goal: 'metabolic_health',
      status: 'active',
      state_summary: {},
      actions: [
        {
          action_key: 'measurement.weight_waist_morning',
          domain: 'measurement',
          title: '晨起记录体重和腰围',
          why: '同一时间测量噪声更低。',
          when: 'morning',
        } as any,
      ],
    };

    const { getByText } = render(<TodayPlanPanel plan={plan} />);

    fireEvent.press(getByText('完成'));

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        '/daily-plan/actions/measurement.weight_waist_morning/events',
        { event_type: 'completed', payload: {} },
      );
    });
  });
});
