/**
 * Live Run 规则引擎 (P2).
 *
 * 职责:
 * - 3 条硬规则: 配速偏离 R1 / 心率过载 R2 / 总量超限 R3
 * - 输入: 实时指标 (配速 / 心率 / 已跑时长)
 * - 输出: 触发事件列表
 *
 * 设计:
 * - 纯本地 TypeScript, 不依赖后端
 * - 状态机式触发: 触发后进入"已警告"状态, 必须先回到达标带 (滞回) 才能再次触发
 *   → 解决"用户刚降速 90s 又被锤一次"的假阳性
 * - 冷启动豁免: 前 180s 不评估配速 (起步信号噪声大 + 用户在调状态)
 * - 事件带上触发时的指标快照, 方便 LLM 复盘
 *
 * 关键阈值:
 * - R1 触发: 比目标快 >15 s/km 持续 60s (cold-start 之后)
 * - R1 滞回: 偏差落回 ≤8 s/km 持续 30s 才解除 → 重新可触发
 */
export interface LiveRunMetrics {
  currentPace: number | null;
  targetPace: number;
  elapsedS: number;
  currentHr: number | null;
  z4PlusMinutes: number;
}

export interface LiveRunRule {
  ruleId: string;
  priority: number;
}

const COLD_START_S = 180;
const DRIFT_TRIGGER = 15;
const DRIFT_RECOVER = 8;
const RECOVER_HOLD_MS = 30_000;
const HR_ZONE_TRIGGER_BPM = 150;
const HR_ZONE_DURATION_S = 120;
const TOTAL_LOAD_THRESHOLD_MIN = 30;

export const RULE_PACE_DRIFT: LiveRunRule = { ruleId: 'pace_drift', priority: 0 };
export const RULE_HR_ZONE: LiveRunRule = { ruleId: 'hr_zone_overload', priority: 1 };
export const RULE_TOTAL_LOAD: LiveRunRule = { ruleId: 'total_load_exceeded', priority: 2 };

const ALL_RULES: LiveRunRule[] = [RULE_PACE_DRIFT, RULE_HR_ZONE, RULE_TOTAL_LOAD];

interface RuleState {
  armed: boolean;              // 当前是否可以触发 (false = 触发过, 等滞回)
  recoverStartedAt: number | null; // 进入"达标带"的起始 ts
}

const ruleState = new Map<string, RuleState>();

function getState(ruleId: string): RuleState {
  let s = ruleState.get(ruleId);
  if (!s) {
    s = { armed: true, recoverStartedAt: null };
    ruleState.set(ruleId, s);
  }
  return s;
}

export function resetRuleEngine(): void {
  ruleState.clear();
}

export interface RuleTriggeredEvent {
  ts: number;
  ruleId: string;
  message: string;
  metricSnapshot: {
    currentPace: number | null;
    targetPace: number;
    drift: number | null;
    currentHr: number | null;
    z4PlusMinutes: number;
  };
}

export type TriggerResult =
  | { type: 'triggered'; event: RuleTriggeredEvent }
  | { type: 'unchanged' }
  | { type: 'rule_disabled' };

function buildSnapshot(m: LiveRunMetrics): RuleTriggeredEvent['metricSnapshot'] {
  return {
    currentPace: m.currentPace,
    targetPace: m.targetPace,
    drift: m.currentPace != null ? m.targetPace - m.currentPace : null,
    currentHr: m.currentHr,
    z4PlusMinutes: m.z4PlusMinutes,
  };
}

function evalPaceDrift(m: LiveRunMetrics, now: number): TriggerResult {
  if (m.currentPace == null) return { type: 'unchanged' };
  if (m.elapsedS < COLD_START_S) return { type: 'unchanged' };

  const drift = m.targetPace - m.currentPace;
  const state = getState(RULE_PACE_DRIFT.ruleId);

  if (state.armed) {
    if (drift > DRIFT_TRIGGER && m.elapsedS >= 60) {
      state.armed = false;
      state.recoverStartedAt = null;
      const minutes = Math.floor(drift / 60);
      const seconds = Math.floor(drift % 60);
      const text =
        minutes > 0
          ? `配速偏快 ${minutes}分${seconds}秒,建议降速`
          : `配速偏快 ${seconds}秒,建议降速`;
      return {
        type: 'triggered',
        event: {
          ts: now,
          ruleId: RULE_PACE_DRIFT.ruleId,
          message: text,
          metricSnapshot: buildSnapshot(m),
        },
      };
    }
    return { type: 'unchanged' };
  }

  // 滞回: 等回到达标带 (drift ≤ DRIFT_RECOVER) 持续 RECOVER_HOLD_MS 才重新 arm
  if (drift <= DRIFT_RECOVER) {
    if (state.recoverStartedAt == null) {
      state.recoverStartedAt = now;
    } else if (now - state.recoverStartedAt >= RECOVER_HOLD_MS) {
      state.armed = true;
      state.recoverStartedAt = null;
    }
  } else {
    state.recoverStartedAt = null;
  }
  return { type: 'unchanged' };
}

function evalHrZone(m: LiveRunMetrics, now: number): TriggerResult {
  if (m.currentHr == null) return { type: 'rule_disabled' };
  const state = getState(RULE_HR_ZONE.ruleId);
  if (!state.armed) {
    if (m.currentHr <= HR_ZONE_TRIGGER_BPM - 10) state.armed = true;
    return { type: 'unchanged' };
  }
  if (m.currentHr > HR_ZONE_TRIGGER_BPM && m.elapsedS >= HR_ZONE_DURATION_S) {
    state.armed = false;
    return {
      type: 'triggered',
      event: {
        ts: now,
        ruleId: RULE_HR_ZONE.ruleId,
        message: `心率 ${m.currentHr} 进入高区,注意强度`,
        metricSnapshot: buildSnapshot(m),
      },
    };
  }
  return { type: 'unchanged' };
}

function evalTotalLoad(m: LiveRunMetrics, now: number): TriggerResult {
  const state = getState(RULE_TOTAL_LOAD.ruleId);
  if (!state.armed) return { type: 'unchanged' };
  if (m.z4PlusMinutes > TOTAL_LOAD_THRESHOLD_MIN) {
    state.armed = false;
    const over = m.z4PlusMinutes - TOTAL_LOAD_THRESHOLD_MIN;
    return {
      type: 'triggered',
      event: {
        ts: now,
        ruleId: RULE_TOTAL_LOAD.ruleId,
        message: `高区时长已超限 ${over.toFixed(0)} 分钟,建议结束`,
        metricSnapshot: buildSnapshot(m),
      },
    };
  }
  return { type: 'unchanged' };
}

export function evaluateRules(metrics: LiveRunMetrics): TriggerResult[] {
  const now = Date.now();
  return [
    evalPaceDrift(metrics, now),
    evalHrZone(metrics, now),
    evalTotalLoad(metrics, now),
  ];
}

export function getRuleById(ruleId: string): LiveRunRule | undefined {
  return ALL_RULES.find((r) => r.ruleId === ruleId);
}
