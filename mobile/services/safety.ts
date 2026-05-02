import api from './api';

export interface SafetyAlert {
  rule_id: string;
  severity: 'critical' | 'high' | 'medium' | 'low' | 'info';
  category: string;
  title: string;
  message: string;
  action?: string;
  context?: Record<string, any>;
}

export interface SafetyReport {
  alerts: SafetyAlert[];
  checked_at: string;
  rules_evaluated: number;
  // Task 3: 回传本次 safety_guardian 评估的 audit_id,
  // Mobile ExplainSheet 用它反查 /reasoning-trace/safety/{audit_id}.
  // 旁路 audit 写失败时为 null, UI 应容忍 (隐藏"为什么?"按钮).
  audit_id: number | null;
}

export interface AlertExplanation {
  explanation: string;
}

export async function getSafetyReport(): Promise<SafetyReport> {
  const { data } = await api.get<SafetyReport>('/safety/me');
  return data;
}

export async function explainAlert(
  ruleId: string,
  message: string,
): Promise<AlertExplanation> {
  const { data } = await api.post<AlertExplanation>('/safety/explain', {
    rule_id: ruleId,
    message,
  });
  return data;
}
