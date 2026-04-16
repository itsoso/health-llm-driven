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
