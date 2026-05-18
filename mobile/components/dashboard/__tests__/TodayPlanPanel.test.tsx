import React from 'react';
import { fireEvent, render, waitFor } from '@testing-library/react-native';

jest.mock('../../../services/api', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn() },
}));

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

  it('submits done feedback for a daily plan action', async () => {
    (api.post as jest.Mock).mockResolvedValueOnce({ data: { status: 'done' } });
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

    fireEvent.press(getByText('做到了'));

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        '/daily-plan/me/actions/measurement.weight_waist_morning/feedback',
        { status: 'done' },
      );
    });
  });
});
