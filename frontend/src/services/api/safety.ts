import api from './client';

export type SafetySeverityValue = 0 | 1 | 2 | 3 | 4;

export interface SafetySeverity {
  value: SafetySeverityValue;
  label: 'info' | 'low' | 'medium' | 'high' | 'critical';
  label_zh: '提示' | '关注' | '注意' | '警告' | '紧急';
}

export interface SafetyAlert {
  rule_id: string;
  category: 'vitals' | 'labs' | 'ddi' | 'dsi' | 'pgx' | 'training_load' | string;
  severity: SafetySeverity;
  title: string;
  message: string;
  action: string | null;
  data_citation: Record<string, any>;
  references: string[];
  requires_medical_attention: boolean;
  generated_at: string;
}

export interface SafetyReport {
  user_id: number;
  generated_at: string;
  alerts: SafetyAlert[];
  summary: {
    total: number;
    critical: number;
    high: number;
    medium: number;
    rules_evaluated: number;
  };
  timing: {
    twin_build_ms: number;
    evaluate_ms: number;
  };
}

/** 获取当前用户的安全告警报告。 */
export const getSafetyReport = async (severityMin?: number): Promise<SafetyReport> => {
  const res = await api.get('/safety/me', {
    params: severityMin !== undefined ? { severity_min: severityMin } : undefined,
  });
  return res.data;
};

/** 忽略/标记已知某条告警。 */
export const dismissSafetyAlert = async (
  ruleId: string,
  reason: string = 'known',
  note?: string
): Promise<void> => {
  await api.post('/safety/dismiss', null, {
    params: { rule_id: ruleId, reason, ...(note ? { note } : {}) },
  });
};

/** 恢复之前忽略的告警。 */
export const restoreSafetyAlert = async (ruleId: string): Promise<void> => {
  await api.delete('/safety/dismiss', { params: { rule_id: ruleId } });
};

/** 列出所有已注册的规则（调试用）。 */
export const listSafetyRules = async (): Promise<{ total: number; rules: string[] }> => {
  const res = await api.get('/safety/rules');
  return res.data;
};

export interface SafetyExplainResponse {
  rule_id: string;
  explanation: string;
  generated_at: string;
  cached: boolean;
}

/** 对某条 Alert 请求 LLM 个性化解读（Phase 1.6）。 */
export const explainSafetyAlert = async (
  ruleId: string,
  context?: { data_citation?: Record<string, any>; message?: string }
): Promise<SafetyExplainResponse> => {
  const res = await api.post('/safety/explain', {
    rule_id: ruleId,
    data_citation: context?.data_citation,
    message: context?.message,
  });
  return res.data;
};
