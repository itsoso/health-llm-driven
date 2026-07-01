import type { DailyArtifact } from '../../../services/dailyArtifact';
import type { SafetyAlert } from '../../../services/safety';
import {
  buildDailyArtifactAtomicContract,
  buildSafetyAlertAtomicContract,
  selectTodayAtomicContracts,
} from '../todayAtomicCards';

function artifact(overrides: Partial<DailyArtifact> = {}): DailyArtifact {
  return {
    artifact_date: '2026-06-30',
    empty_state: false,
    state: { label: '今日最重要行动', tone: 'focused', summary: '先做餐后行动。' },
    top_action: {
      id: 'walk-10m',
      title: '今日训练:今天午饭后步行 10 分钟',
      why_now: '餐后窗口优先。',
      do_now: '走一圈。',
      target_state_variable: 'waist_cm',
      verification_signal: 'sleep_score',
      actions: { complete: { enabled: false }, skip: { requires_reason: true } },
    },
    evidence: [
      { kind: 'verification', label: 'Verification', summary: '用睡眠和腰围验证。', metrics: ['steps'] },
    ],
    confidence: 'medium',
    freshness: { status: 'fresh', sources: ['runtime'] },
    safety_boundary: '健康管理行动建议,不替代医生诊断。',
    ...overrides,
  };
}

function alert(overrides: Partial<SafetyAlert> = {}): SafetyAlert {
  return {
    rule_id: 'spo2_low',
    severity: 'high',
    category: 'vitals',
    title: '夜间血氧持续偏低',
    message: '昨晚最低血氧 88%。',
    action: '今天先复测。',
    ...overrides,
  };
}

describe('todayAtomicCards', () => {
  it('declares DailyArtifact as a closed atomic capability for Agent composition', () => {
    const contract = buildDailyArtifactAtomicContract(artifact());

    expect(contract.id).toBe('daily-artifact:2026-06-30:walk-10m');
    expect(contract.kind).toBe('daily_artifact');
    expect(contract.render.show).toBe(true);
    expect(contract.render.reason).toBe('has_top_action');
    expect(contract.primaryAction).toMatchObject({ id: 'execute', label: '去执行' });
    expect(contract.secondaryActions.map(action => action.id)).toEqual(['explain_basis', 'ask_reva', 'skip']);
    expect(contract.verificationSignals).toEqual(['睡眠分', '腰围', '步数']);
    expect(contract.safetyBoundary).toContain('不替代医生诊断');
    expect(contract.dedupeKeys).toEqual(['午饭后步行 10 分钟']);
  });

  it('does not promote an empty DailyArtifact as a primary action atom', () => {
    const contract = buildDailyArtifactAtomicContract(artifact({
      empty_state: true,
      top_action: null,
      evidence: [],
    }));

    expect(contract.render.show).toBe(false);
    expect(contract.render.reason).toBe('missing_top_action');
    expect(contract.primaryAction).toBeNull();
  });

  it('declares only high-priority SafetyAlert as a Today atom and chooses critical first', () => {
    const contract = buildSafetyAlertAtomicContract([
      alert({ rule_id: 'high_spo2', severity: 'high', title: '高风险血氧' }),
      alert({ rule_id: 'critical_bp', severity: 'critical', title: '严重血压风险' }),
    ]);

    expect(contract.render.show).toBe(true);
    expect(contract.id).toBe('safety-alert:critical_bp');
    expect(contract.primaryAction).toEqual({ id: 'open_alerts', label: '查看安全提醒', route: '/(tabs)/alerts' });
    expect(contract.payload?.title).toBe('严重血压风险');
    expect(contract.riskLevel).toBe('critical');
  });

  it('keeps medium and low SafetyAlert out of Today', () => {
    const contract = buildSafetyAlertAtomicContract([
      alert({ severity: 'medium', title: '饮水偏少' }),
      alert({ severity: 'low', title: '日常提示' }),
    ]);

    expect(contract.render.show).toBe(false);
    expect(contract.render.reason).toBe('no_high_priority_alert');
    expect(contract.payload).toBeNull();
  });

  it('returns renderable Today contracts in Agent composition order', () => {
    const contracts = selectTodayAtomicContracts({
      artifact: artifact(),
      safetyAlerts: [alert()],
    });

    expect(contracts.map(contract => contract.kind)).toEqual(['daily_artifact', 'safety_alert']);
    expect(contracts.every(contract => contract.render.show)).toBe(true);
  });
});
