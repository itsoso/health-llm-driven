import React from 'react';
import { render } from '@testing-library/react-native';

jest.mock('../../../services/api', () => ({
  __esModule: true,
  default: { get: jest.fn() },
}));

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
});
