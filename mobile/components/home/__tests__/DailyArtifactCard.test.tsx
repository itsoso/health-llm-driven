import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';

import DailyArtifactCard from '../DailyArtifactCard';
import type { DailyArtifact } from '../../../services/dailyArtifact';

function makeArtifact(overrides: Partial<DailyArtifact> = {}): DailyArtifact {
  return {
    artifact_date: '2026-06-27',
    empty_state: false,
    state: {
      label: '今日状态',
      tone: 'focused',
      summary: '餐后窗口优先完成轻活动。',
    },
    top_action: {
      id: 'walk-10m',
      title: '午饭后步行 10 分钟',
      why_now: '餐后血糖窗口更适合轻活动。',
      do_now: '穿好鞋,从办公室楼下走一圈。',
      confidence: 'medium',
      priority_tier: 'P1',
      verify_by: {
        metrics: ['waist_cm'],
        window_days: 7,
        trajectory: { uncertainty_level: 'medium' },
      },
      trajectory_context: {
        state_variable: 'waist_cm',
        horizon: 'upstream_90d',
        verification_window_days: 7,
        claim_boundary: '用于上游健康管理排序, 不替代医生诊断。',
      },
      target_state_variable: 'waist_cm',
      verification_signal: 'waist_cm',
      claim_boundary: '用于上游健康管理排序, 不替代医生诊断。',
      actions: {
        complete: { enabled: true },
        skip: { requires_reason: true, event_type: 'skipped' },
        ask_reva: { target: '/voice-chat?intent=daily_artifact' },
      },
    } as any,
    evidence: [
      { kind: 'why_now', label: 'Why now', summary: '餐后窗口' },
      { kind: 'trajectory', label: 'Trajectory', summary: '近期活动不足' },
      { kind: 'verification', label: 'Verification', summary: '用步数验证' },
      { kind: 'extra', label: 'Extra', summary: '不应显示' },
    ],
    confidence: 'medium',
    freshness: { status: 'fresh', sources: ['health_protocol'] },
    safety_boundary: '这是健康管理行动建议,不替代医生诊断。',
    ...overrides,
  };
}

describe('DailyArtifactCard', () => {
  it('renders exactly one top action and at most three evidence rows', () => {
    const { getByText, getAllByTestId, queryByText } = render(
      <DailyArtifactCard artifact={makeArtifact()} />,
    );

    expect(getByText('午饭后步行 10 分钟')).toBeTruthy();
    expect(getByText('目标: 腰围 · 周期: 90天上游轨迹')).toBeTruthy();
    expect(getByText('验证: 腰围 · 7天 · 不确定性: 中')).toBeTruthy();
    expect(getAllByTestId('daily-artifact-evidence')).toHaveLength(3);
    expect(queryByText('不应显示')).toBeNull();
  });

  it('requires a skip reason before calling onSkip', () => {
    const onSkip = jest.fn();
    const { getByLabelText, getByText } = render(
      <DailyArtifactCard artifact={makeArtifact()} onSkip={onSkip} />,
    );

    fireEvent.press(getByLabelText('跳过今日最重要行动'));
    expect(onSkip).not.toHaveBeenCalled();
    expect(getByText('为什么跳过?')).toBeTruthy();

    fireEvent.press(getByText('太累'));
    expect(onSkip).toHaveBeenCalledWith('too_tired', makeArtifact().top_action);
  });

  it('renders a compact empty state when no top action exists', () => {
    const { getByText, queryByLabelText } = render(
      <DailyArtifactCard
        artifact={makeArtifact({
          empty_state: true,
          top_action: null,
          evidence: [],
          state: {
            label: '暂无今日重点',
            tone: 'neutral',
            summary: '今天暂无需要突出的健康行动。',
          },
        })}
      />,
    );

    expect(getByText('暂无今日重点')).toBeTruthy();
    expect(getByText('今天暂无需要突出的健康行动。')).toBeTruthy();
    expect(queryByLabelText('完成今日最重要行动')).toBeNull();
  });
});
