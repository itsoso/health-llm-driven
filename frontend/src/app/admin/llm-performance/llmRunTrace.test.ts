import { describe, expect, it } from 'vitest';
import {
  buildRunTraceRows,
  formatRunTraceTitle,
  runTraceTone,
  summarizeRunDetail,
  type RunDetail,
} from './llmRunTrace';

const baseRun: RunDetail = {
  run_id: 'run_abcdef1234567890',
  summary: {
    calls: 2,
    failed_calls: 1,
    prompt_tokens: 1200,
    completion_tokens: 300,
    total_tokens: 1500,
    cost_usd: 0.0012,
    latency_ms: 4200,
  },
  calls: [
    {
      id: 1,
      provider: 'tokenplan',
      model: 'qwen3.7-plus',
      caller: 'agent.gather',
      user_id: 3,
      run_id: 'run_abcdef1234567890',
      prompt_tokens: 800,
      completion_tokens: 120,
      total_tokens: 920,
      cost_usd: 0,
      latency_ms: 1800,
      success: false,
      error_class: 'quota_exhausted',
      error_type: 'insufficient_quota',
      error_code: 'insufficient_quota',
      error_message: 'Your token-plan quota has been exhausted.',
      recovery_action: 'fallback_attempted',
      recovery_model: 'gpt-5.5',
      created_at: '2026-07-02T06:00:00Z',
    },
    {
      id: 2,
      provider: 'langbridge-proxy',
      model: 'commercial/GPT-5.5',
      caller: 'agent.gather',
      user_id: 3,
      run_id: 'run_abcdef1234567890',
      prompt_tokens: 400,
      completion_tokens: 180,
      total_tokens: 580,
      cost_usd: 0.0012,
      latency_ms: 2400,
      success: true,
      created_at: '2026-07-02T06:00:03Z',
    },
  ],
};

describe('llmRunTrace', () => {
  it('formats a compact run title without losing the trace id', () => {
    expect(formatRunTraceTitle(baseRun.run_id)).toBe('run_abcdef1234567890');
    expect(formatRunTraceTitle('')).toBe('未知 run');
  });

  it('summarizes failures, token totals, and recovery action for the drawer header', () => {
    expect(summarizeRunDetail(baseRun)).toEqual({
      calls: '2 次',
      failures: '1 失败',
      tokens: '1.5k tokens',
      latency: '4.2s',
      recovery: 'fallback_attempted -> gpt-5.5',
    });
  });

  it('marks failed or recovered runs as warning tone', () => {
    expect(runTraceTone(baseRun)).toBe('warn');
    expect(runTraceTone({ ...baseRun, summary: { ...baseRun.summary, failed_calls: 0 }, calls: [baseRun.calls[1]] })).toBe('ok');
  });

  it('builds stable row labels for each LLM call in execution order', () => {
    expect(buildRunTraceRows(baseRun)).toEqual([
      {
        id: 1,
        label: '#1 tokenplan / qwen3.7-plus',
        status: '失败',
        tokens: '920',
        latency: '1.8s',
        caller: 'agent.gather',
        error: 'insufficient_quota · Your token-plan quota has been exhausted.',
        recovery: 'fallback_attempted -> gpt-5.5',
      },
      {
        id: 2,
        label: '#2 langbridge-proxy / commercial/GPT-5.5',
        status: '成功',
        tokens: '580',
        latency: '2.4s',
        caller: 'agent.gather',
        error: '—',
        recovery: '—',
      },
    ]);
  });
});
