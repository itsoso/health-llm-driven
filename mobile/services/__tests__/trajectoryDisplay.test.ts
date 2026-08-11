import {
  buildBoundarySummary,
  buildTrajectorySummary,
  buildVerifySummary,
  stateVariableLabel,
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

  // ── defect ②:指标 key → 中文名的单一真相源,补齐历史漏映射的 key ──
  describe('stateVariableLabel (single source of metric labels)', () => {
    it('maps previously-leaking English metric keys to Chinese names', () => {
      // 这些 key 之前在 trajectoryDisplay 的表里缺失,导致首页「验证」chip 泄漏英文残缺词。
      expect(stateVariableLabel('weight')).toBe('体重');
      expect(stateVariableLabel('systolic_bp')).toBe('收缩压');
      expect(stateVariableLabel('diastolic_bp')).toBe('舒张压');
      expect(stateVariableLabel('body_fat_pct')).toBe('体脂率');
      expect(stateVariableLabel('waist_cm')).toBe('腰围');
      expect(stateVariableLabel('follow_up_completed')).toBe('复查完成情况');
    });

    it('falls back to the raw key for unknown metrics (never crashes, never English fragment)', () => {
      // 未知 key 原样返回一个完整词,不产生词中间截断(截断由容器 numberOfLines 负责,不切词内)。
      expect(stateVariableLabel('some_unknown_metric')).toBe('some_unknown_metric');
      expect(stateVariableLabel(null)).toBeNull();
      expect(stateVariableLabel(undefined)).toBeNull();
    });

    it('produces an all-Chinese verify summary for the metrics that used to leak', () => {
      const summary = buildVerifySummary({
        verify_by: { metrics: ['weight', 'waist_cm', 'systolic_bp'] },
      });
      expect(summary).toBe('体重 / 腰围 / 收缩压');
      // 断言没有英文残留(排除 defect ② 的 "weight / 腰围 / systoli…" 泄漏)。
      expect(summary).not.toMatch(/[a-z_]/i);
    });

    it('renders follow-up verification without exposing the internal metric key', () => {
      const summary = buildVerifySummary({
        verify_by: { metrics: ['follow_up_completed'], window_days: 14 },
      });

      expect(summary).toBe('复查完成情况 · 14天');
      expect(summary).not.toContain('follow_up_completed');
    });
  });
});
