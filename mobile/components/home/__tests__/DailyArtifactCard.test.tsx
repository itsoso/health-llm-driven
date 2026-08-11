import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';

import DailyArtifactCard from '../DailyArtifactCard';
import type { DailyArtifact } from '../../../services/dailyArtifact';

// RN style prop 可能是数组/嵌套;拍平成单对象方便断言颜色。
function flattenStyle(style: unknown): Record<string, unknown> {
  if (Array.isArray(style)) return Object.assign({}, ...style.map(flattenStyle));
  return (style && typeof style === 'object' ? style : {}) as Record<string, unknown>;
}

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

    expect(getByText('今日行动')).toBeTruthy();
    expect(getByText('建议行动')).toBeTruthy();
    expect(getByText('今日重点 · 数据已更新')).toBeTruthy();
    expect(getByText('午饭后步行 10 分钟')).toBeTruthy();
    expect(getByText('穿好鞋,从办公室楼下走一圈。')).toBeTruthy();
    expect(getByText('决策依据')).toBeTruthy();
    expect(getByText('餐后血糖窗口更适合轻活动。')).toBeTruthy();
    expect(getByText('目标')).toBeTruthy();
    expect(getByText('腰围 · 90天上游轨迹')).toBeTruthy();
    expect(getByText('验证')).toBeTruthy();
    expect(getByText('腰围 · 7天 · 不确定性: 中')).toBeTruthy();
    expect(getAllByTestId('daily-artifact-evidence')).toHaveLength(2);
    expect(queryByText('今日焦点')).toBeNull();
    expect(queryByText('现在只做')).toBeNull();
    expect(queryByText('中可信')).toBeNull();
    expect(queryByText('P1 · 1 个来源 · 新鲜')).toBeNull();
    expect(queryByText('不应显示')).toBeNull();
  });

  it('opens a detailed decision basis discussion with Aheng', () => {
    const onExplainBasis = jest.fn();
    const artifact = makeArtifact();
    const { getByLabelText, getByText } = render(
      <DailyArtifactCard artifact={artifact} onExplainBasis={onExplainBasis} />,
    );

    expect(getByText('查看决策依据')).toBeTruthy();
    fireEvent.press(getByLabelText('查看今日行动决策依据'));
    expect(onExplainBasis).toHaveBeenCalledWith(artifact);
  });

  it('cleans generated action titles before rendering them', () => {
    const { getByText, queryByText } = render(
      <DailyArtifactCard
        artifact={makeArtifact({
          top_action: {
            ...makeArtifact().top_action!,
            title: '今日训练:今天恢复/休息,暂停高强度;优先睡眠与轻活动',
          } as any,
        })}
      />,
    );

    expect(getByText('恢复/休息:暂停高强度;优先睡眠与轻活动')).toBeTruthy();
    expect(queryByText('今日训练:今天恢复/休息,暂停高强度;优先睡眠与轻活动')).toBeNull();
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

    const { getAllByTestId, getAllByText, getByText } = render(
      <DailyArtifactCard artifact={artifact} />,
    );

    expect(getAllByText('优先睡眠与轻活动')).toHaveLength(1);
    expect(getAllByText('腰围、血压、BMI、血糖血脂或基因信号提示代谢风险轨迹正在形成。')).toHaveLength(1);
    // 「如何验证」行的泛化 filler 被换成实名句(defect ④):action.verify_by.metrics=['waist_cm'] → 腰围。
    expect(getByText('后续观察 腰围 的变化。')).toBeTruthy();
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

  it('routes a medical follow-up to handling instead of the unsupported complete write', () => {
    const onComplete = jest.fn();
    const onPressAction = jest.fn();
    const source = { object_type: 'health_problem', object_id: 9 };
    const artifact = makeArtifact({
      top_action: {
        ...makeArtifact().top_action!,
        type: 'checkup',
        title: '复查:胃溃疡(Hp 阴性,胃窦后壁)',
        source,
        verify_by: { metrics: ['follow_up_completed'], window_days: 14 },
        verification_signal: null,
        target_state_variable: null,
        actions: {
          complete: { enabled: true, source },
          skip: { requires_reason: true },
        },
      } as any,
      evidence: [
        { kind: 'verification', label: 'Verification', summary: '后续用这些信号验证是否有效。' },
      ],
    });

    const { getByLabelText, getByText, queryByText } = render(
      <DailyArtifactCard artifact={artifact} onComplete={onComplete} onPressAction={onPressAction} />,
    );

    expect(getByText('复查完成情况 · 14天')).toBeTruthy();
    expect(getByText('后续确认复查是否完成。')).toBeTruthy();
    expect(getByText('处理复查')).toBeTruthy();
    expect(queryByText('follow_up_completed · 14天')).toBeNull();
    expect(queryByText('完成')).toBeNull();

    fireEvent.press(getByLabelText('处理今日复查'));
    expect(onComplete).not.toHaveBeenCalled();
    expect(onPressAction).toHaveBeenCalledWith(artifact.top_action);
  });

  it('uses 小巴 as the visible assistant persona for the ask action', () => {
    const { getByLabelText, getByText, queryByLabelText } = render(
      <DailyArtifactCard artifact={makeArtifact()} />,
    );

    expect(getByText('问小巴')).toBeTruthy();
    expect(getByLabelText('询问小巴今日行动')).toBeTruthy();
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

  // ── defect ①:do_now 复读标题时,「查看并确认」子行折成 affordance,不再抄一遍标题 ──
  it('collapses a do_now that echoes the title (with affordance prefix) to just the affordance', () => {
    const { getByText, queryByText } = render(
      <DailyArtifactCard
        artifact={makeArtifact({
          top_action: {
            ...makeArtifact().top_action!,
            title: '今日训练:今天恢复/休息,暂停高强度;优先睡眠与轻活动',
            do_now: '查看并确认: 今日训练:今天恢复/休息,暂停高强度;优先睡眠与轻活动',
          } as any,
        })}
      />,
    );

    // 大标题清洗后显示
    expect(getByText('恢复/休息:暂停高强度;优先睡眠与轻活动')).toBeTruthy();
    // do_now 子行只留 affordance 文案,不复读整句标题
    expect(getByText('查看并确认')).toBeTruthy();
    expect(queryByText('查看并确认: 今日训练:今天恢复/休息,暂停高强度;优先睡眠与轻活动')).toBeNull();
  });

  it('keeps a genuinely distinct do_now instruction intact', () => {
    const { getByText } = render(
      <DailyArtifactCard
        artifact={makeArtifact({
          top_action: {
            ...makeArtifact().top_action!,
            title: '午饭后步行 10 分钟',
            do_now: '穿好鞋,从办公室楼下走一圈。',
          } as any,
        })}
      />,
    );

    expect(getByText('穿好鞋,从办公室楼下走一圈。')).toBeTruthy();
  });

  // ── defect ③:高可信 badge 用正向(success 绿)配色,绝不用 risk 红 ──
  it('tints the 重点行动 confidence badge with success green, never risk red', () => {
    const { getByText } = render(
      <DailyArtifactCard
        artifact={makeArtifact({
          confidence: 'high',
          state: { label: '今日状态', tone: 'urgent', summary: '紧急态' },
        })}
      />,
    );

    const badge = getByText('重点行动');
    const flat = flattenStyle(badge.parent?.props?.style);
    // 文案色 = success 绿(revaSemantic.normal.fg),不是 risk 红(#D5503A)。
    expect(flat.color).toBe('#1F8A5B');
    expect(flat.color).not.toBe('#D5503A');
  });

  it('tints the 待补数据 (low) confidence badge with caution amber', () => {
    const { getByText } = render(
      <DailyArtifactCard artifact={makeArtifact({ confidence: 'low' })} />,
    );

    const flat = flattenStyle(getByText('待补数据').parent?.props?.style);
    expect(flat.color).toBe('#C98A1E'); // revaSemantic.caution.fg
  });

  // ── defect ④:无具体验证指标时,「如何验证」filler 行整条丢掉(不留废话) ──
  it('drops the verification evidence row when no concrete metrics exist', () => {
    const base = makeArtifact();
    const { queryByText } = render(
      <DailyArtifactCard
        artifact={makeArtifact({
          top_action: {
            ...base.top_action!,
            verify_by: undefined,
            target_state_variable: null,
            verification_signal: null,
            trajectory_context: undefined,
          } as any,
          evidence: [
            { kind: 'verification', label: 'Verification', summary: '后续用这些信号验证是否有效。' },
          ],
        })}
      />,
    );

    expect(queryByText('后续用这些信号验证是否有效。')).toBeNull();
    expect(queryByText('如何验证')).toBeNull();
  });
});
