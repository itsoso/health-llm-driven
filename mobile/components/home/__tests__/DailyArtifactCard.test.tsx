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
  it('renders one focused top action with compact proof chips and capped evidence', () => {
    const { getByText, getAllByTestId, queryByText } = render(
      <DailyArtifactCard artifact={makeArtifact()} />,
    );

    expect(getByText('今日焦点')).toBeTruthy();
    expect(getByText('午饭后步行 10 分钟')).toBeTruthy();
    expect(getByText('现在只做')).toBeTruthy();
    expect(getByText('目标')).toBeTruthy();
    expect(getByText('腰围 · 90天上游轨迹')).toBeTruthy();
    expect(getByText('验证')).toBeTruthy();
    expect(getByText('腰围 · 7天 · 不确定性: 中')).toBeTruthy();
    expect(getAllByTestId('daily-artifact-evidence')).toHaveLength(2);
    expect(queryByText('不应显示')).toBeNull();
  });

  it('deduplicates repeated evidence against the action copy', () => {
    const artifact = makeArtifact({
      top_action: {
        ...makeArtifact().top_action!,
        title: '今天训练:优先睡眠与轻活动',
        do_now: '今天训练:优先睡眠与轻活动',
        why_now: '腰围、血压、BMI、血糖血脂或基因信号提示代谢风险轨迹正在形成。',
      } as any,
      evidence: [
        {
          kind: 'why_now',
          label: 'Why now',
          summary: '腰围、血压、BMI、血糖血脂或基因信号提示代谢风险轨迹正在形成。',
        },
        {
          kind: 'trajectory',
          label: 'Trajectory',
          summary: '腰围、血压、BMI、血糖血脂或基因信号提示代谢风险轨迹正在形成。',
        },
        { kind: 'verification', label: 'Verification', summary: '后续用睡眠分和腰围验证。' },
      ],
    });

    const { getAllByTestId, getAllByText, getByText, queryByText } = render(
      <DailyArtifactCard artifact={artifact} />,
    );

    expect(getAllByText('今天训练:优先睡眠与轻活动')).toHaveLength(1);
    expect(queryByText('腰围、血压、BMI、血糖血脂或基因信号提示代谢风险轨迹正在形成。')).toBeNull();
    expect(getByText('后续用睡眠分和腰围验证。')).toBeTruthy();
    expect(getAllByTestId('daily-artifact-evidence')).toHaveLength(1);
  });

  it('uses a go-execute primary action when the card cannot write completion', () => {
    const onComplete = jest.fn();
    const onPressAction = jest.fn();
    const artifact = makeArtifact({
      top_action: {
        ...makeArtifact().top_action!,
        actions: { complete: { enabled: true }, skip: { requires_reason: true } },
        source: null,
      } as any,
    });

    const { getByLabelText, getByText, queryByText } = render(
      <DailyArtifactCard artifact={artifact} onComplete={onComplete} onPressAction={onPressAction} />,
    );

    expect(getByText('去执行')).toBeTruthy();
    expect(queryByText('完成')).toBeNull();

    fireEvent.press(getByLabelText('执行今日最重要行动'));
    expect(onComplete).not.toHaveBeenCalled();
    expect(onPressAction).toHaveBeenCalledWith(artifact.top_action);
  });

  it('uses 阿衡 as the visible assistant persona for the ask action', () => {
    const { getByLabelText, getByText, queryByLabelText } = render(
      <DailyArtifactCard artifact={makeArtifact()} />,
    );

    expect(getByText('问阿衡')).toBeTruthy();
    expect(getByLabelText('询问阿衡今日行动')).toBeTruthy();
    expect(queryByLabelText('询问 Reva 今日行动')).toBeNull();
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
