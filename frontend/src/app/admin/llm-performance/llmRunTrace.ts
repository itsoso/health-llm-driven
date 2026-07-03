export interface LlmRunCall {
  id: number;
  provider: string;
  model: string;
  caller?: string | null;
  user_id?: number | null;
  run_id?: string | null;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
  cost_cny?: number;
  cost_estimated?: boolean;
  cost_source?: string | null;
  latency_ms?: number | null;
  success: boolean;
  error_class?: string | null;
  error_type?: string | null;
  error_code?: string | null;
  error_message?: string | null;
  recovery_action?: string | null;
  recovery_model?: string | null;
  created_at: string;
}

export interface RunDetail {
  run_id: string;
  summary: {
    calls: number;
    failed_calls: number;
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    cost_usd: number;
    cost_cny?: number;
    cost_estimated?: boolean;
    latency_ms: number;
  };
  calls: LlmRunCall[];
}

export interface RunTraceSummary {
  calls: string;
  failures: string;
  tokens: string;
  latency: string;
  recovery: string;
}

export interface RunTraceRow {
  id: number;
  label: string;
  status: string;
  tokens: string;
  latency: string;
  caller: string;
  error: string;
  recovery: string;
}

function fmtTokens(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}k`;
  return String(value);
}

function fmtDuration(ms?: number | null): string {
  if (ms == null) return '—';
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`;
  return `${ms}ms`;
}

function compactText(value?: string | null): string {
  return (value || '').trim();
}

export function formatRunTraceTitle(runId?: string | null): string {
  const cleaned = compactText(runId);
  return cleaned || '未知 run';
}

export function recoveryLabel(call?: Pick<LlmRunCall, 'recovery_action' | 'recovery_model'> | null): string {
  const action = compactText(call?.recovery_action);
  const model = compactText(call?.recovery_model);
  if (action && model) return `${action} -> ${model}`;
  return action || model || '—';
}

export function errorLabel(call?: Pick<LlmRunCall, 'error_code' | 'error_type' | 'error_class' | 'error_message'> | null): string {
  const code = compactText(call?.error_code) || compactText(call?.error_type) || compactText(call?.error_class);
  const message = compactText(call?.error_message);
  if (code && message) return `${code} · ${message}`;
  return code || message || '—';
}

export function summarizeRunDetail(run: RunDetail): RunTraceSummary {
  const recovered = run.calls.find(call => recoveryLabel(call) !== '—');
  return {
    calls: `${run.summary.calls} 次`,
    failures: `${run.summary.failed_calls} 失败`,
    tokens: `${fmtTokens(run.summary.total_tokens)} tokens`,
    latency: fmtDuration(run.summary.latency_ms),
    recovery: recoveryLabel(recovered),
  };
}

export function runTraceTone(run: RunDetail): 'ok' | 'warn' {
  const hasFailure = run.summary.failed_calls > 0 || run.calls.some(call => !call.success);
  const hasRecovery = run.calls.some(call => recoveryLabel(call) !== '—');
  return hasFailure || hasRecovery ? 'warn' : 'ok';
}

export function buildRunTraceRows(run: RunDetail): RunTraceRow[] {
  return run.calls.map((call, index) => ({
    id: call.id,
    label: `#${index + 1} ${call.provider} / ${call.model}`,
    status: call.success ? '成功' : '失败',
    tokens: fmtTokens(call.total_tokens),
    latency: fmtDuration(call.latency_ms),
    caller: compactText(call.caller) || '—',
    error: errorLabel(call),
    recovery: recoveryLabel(call),
  }));
}
