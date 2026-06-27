import {
  buildBoundarySummary,
  buildTrajectorySummary,
  buildVerifySummary,
} from '../trajectoryDisplay';
import type { SmartAgendaItem } from '../agenda';

const smartItem = (overrides: Partial<SmartAgendaItem> = {}): SmartAgendaItem => ({
  id: 'smart_daily_plan_action_movement.moderate_activity',
  type: 'movement',
  title: '累计 35-45 分钟中等强度活动',
  status: 'pending',
  priority: 65,
  source: { object_type: 'daily_plan_action', object_id: 'movement.moderate_activity' },
  why_now: '腰围和血压提示代谢轨迹需要关注。',
  do_now: '执行: 累计 35-45 分钟中等强度活动',
  verify_by: {
    metrics: ['waist_cm'],
    window_days: 7,
    trajectory: { uncertainty_level: 'medium' },
  },
  replan_policy: { on_skip: 'capture_reason_then_reschedule' },
  surface: { primary: 'watch', alternates: ['mobile', 'rokid'] },
  autonomy_tier: 'suggest',
  can_complete: true,
  can_snooze: true,
  can_skip: true,
  trajectory_context: {
    domain: 'metabolic_health',
    level: 'attention',
    state_variable: 'waist_cm',
    horizon: 'upstream_90d',
    verification_window_days: 7,
    verification_signal: 'waist_cm',
    claim_boundary: '用于上游健康管理排序, 不替代医生诊断。',
  },
  target_state_variable: 'waist_cm',
  verification_signal: 'waist_cm',
  claim_boundary: '用于上游健康管理排序, 不替代医生诊断。',
  ...overrides,
});

describe('trajectoryDisplay', () => {
  it('renders user-readable target and verification copy', () => {
    const item = smartItem();

    expect(buildTrajectorySummary(item)).toBe('目标: 腰围 · 周期: 90天上游轨迹');
    expect(buildVerifySummary(item)).toBe('腰围 · 7天 · 不确定性: 中');
  });

  it('renders safety boundary copy from claim boundary', () => {
    expect(buildBoundarySummary(smartItem())).toBe('边界: 用于上游健康管理排序, 不替代医生诊断。');
  });
});
