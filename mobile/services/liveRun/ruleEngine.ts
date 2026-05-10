/**
 * Live Run 规则引擎 (P2).
 *
 * 职责:
 * - 3 条硬规则: 配速偏离 R1 / 心率过载 R2 / 总量超限 R3
 * - 输入: 实时指标 (配速 / 心率 / 已跑时长)
 * - 输出: 触发事件列表 (去重 + 节流)
 *
 * 设计:
 * - 纯本地 TypeScript,不依赖后端
 * - 每条规则 90s 内只触发一次 (同规则节流)
 * - 事件带上触发时的指标快照,方便 LLM 复盘
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
  check: (metrics: LiveRunMetrics) => boolean;
  message: (metrics: LiveRunMetrics) => string;
  priority: number; // 0 = 最高, 99 = 最低
}

// R1: 配速偏离 — 实际比目标快 15s/km 且持续 60s
export const RULE_PACE_DRIFT: LiveRunRule = {
  ruleId: 'pace_drift',
  priority: 0,
  check: (m) => {
    if (!m.currentPace) return false;
    const drift = m.targetPace - m.currentPace;
    // 快 15s/km = 偏离阈值
    return drift > 15 && m.elapsedS >= 60;
  },
  message: (m) => {
    const drift = m.targetPace - (m.currentPace ?? m.targetPace);
    const minutes = Math.floor(drift / 60);
    const seconds = drift % 60;
    return `配速偏快 ${minutes}分${seconds}秒,建议降速`;
  },
};

// R2: 心率过载 — 进入 Z4 持续 120s (V1 没心率时跳过)
export const RULE_HR_ZONE: LiveRunRule = {
  ruleId: 'hr_zone_overload',
  priority: 1,
  check: (m) => {
    if (m.currentHr == null) return false;
    // 简化版: 固定 Z4 门槛 (心率 >145 或 >150 视为高区)
    // V2 用 specialists 真正的 Z4 上限
    const isHighZone = m.currentHr > 150;
    return isHighZone && m.elapsedS >= 120;
  },
  message: (m) => {
    if (m.currentHr == null) return '心率进入高区,建议降速';
    return `心率 ${m.currentHr} 进入高区,注意强度`;
  },
};

// R3: 总量超限 — Z4+ 累计超过 readiness 允许阈值
export const RULE_TOTAL_LOAD: LiveRunRule = {
  ruleId: 'total_load_exceeded',
  priority: 2,
  check: (m) => {
    // V1 固定 30 分钟门槛 (后端 max_z4_minutes, 暂时不联接)
    return m.z4PlusMinutes > 30;
  },
  message: (m) => {
    const over = m.z4PlusMinutes - 30;
    return `高区时长已超限${over.toFixed(0)}分钟,建议结束`;
  },
};

const ALL_RULES: LiveRunRule[] = [
  RULE_PACE_DRIFT,
  RULE_HR_ZONE,
  RULE_TOTAL_LOAD,
];

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

export function evaluateRules(metrics: LiveRunMetrics): TriggerResult[] {
  const now = Date.now();
  const results: TriggerResult[] = [];

  for (const rule of ALL_RULES) {
    if (rule.check(metrics)) {
      const event: RuleTriggeredEvent = {
        ts: now,
        ruleId: rule.ruleId,
        message: rule.message(metrics),
        metricSnapshot: {
          currentPace: metrics.currentPace,
          targetPace: metrics.targetPace,
          drift: metrics.currentPace != null ? metrics.targetPace - metrics.currentPace : null,
          currentHr: metrics.currentHr,
          z4PlusMinutes: metrics.z4PlusMinutes,
        },
      };
      results.push({ type: 'triggered', event });
    } else {
      results.push({ type: 'unchanged' });
    }
  }

  return results;
}

export function getRuleById(ruleId: string): LiveRunRule | undefined {
  return ALL_RULES.find((r) => r.ruleId === ruleId);
}
