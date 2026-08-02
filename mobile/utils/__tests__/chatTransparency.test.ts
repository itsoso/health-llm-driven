import { buildAgentTransparency, formatDurationMs, formatTokenCount, routingReasonLabel } from '../chatTransparency';

describe('chatTransparency', () => {
  it('builds a Mac-like run profile from perf, tokens, sources, and tools', () => {
    const profile = buildAgentTransparency({
      elapsedMs: 29200,
      llmRounds: 5,
      model: 'qwen3.7-plus',
      llmUsage: {
        calls: 5,
        prompt_tokens: 1840,
        completion_tokens: 620,
        total_tokens: 2460,
        cost_usd: 0.0042,
        cost_cny: 0.0302,
        cost_estimated: true,
        tokenplan_credits_estimate: 3.18,
        tokenplan_cost_cny: 0.0222,
        tokenplan_payg_value_cny: 0.0302,
        tokenplan_cost_estimated: true,
      },
      sourcesUsed: ['Garmin 数据 (14 天 HRV/睡眠/RHR)', '化验报告 (23 次)'],
      toolsUsed: ['health_manage', 'health_record'],
      perf: {
        total_ms: 29200,
        pre_llm_ms: 44,
        llm_ttft_ms: 23600,
        llm_full_ms: 4000,
        pre_llm_stages: {
          history_ms: 1,
          system_prompt_ms: 26,
          inspect_ms: 6,
        },
        rounds: [
          { llm_gen_ms: 4100, tool_exec_ms: 15, tools: ['health_manage'] },
          { llm_gen_ms: 4700, tool_exec_ms: 217, tools: ['health_record'] },
        ],
      },
    });

    expect(profile.visible).toBe(true);
    expect(profile.headline).toBe('约¥0.02 · 29.2s · 5轮 · qwen3.7-plus');
    expect(profile.costLine).toBe('套餐折算 约¥0.02 · 按量价对照 约¥0.03');
    expect(profile.tokenLine).toBe('输入 1.8k · 输出 620 · 总 2.5k · 5次');
    expect(profile.sources).toEqual(['Garmin 数据 (14 天 HRV/睡眠/RHR)', '化验报告 (23 次)']);
    expect(profile.tools).toEqual(['health_manage', 'health_record']);
    expect(profile.bands.map(b => b.label)).toEqual(['组装', '首字节', '生成', '工具']);
    expect(profile.stages).toContainEqual({ label: '系统提示', value: '26ms' });
    expect(profile.rounds[0]).toEqual({
      label: '第 1 轮',
      value: '生成 4.1s · 工具 15ms · health_manage',
    });
  });

  it('falls back to legacy timing when perf is absent', () => {
    const profile = buildAgentTransparency({
      elapsedMs: 3200,
      llmRounds: 1,
      llmUsage: { prompt_tokens: 410, completion_tokens: 90 },
    });

    expect(profile.visible).toBe(true);
    expect(profile.headline).toBe('3.2s · 1轮');
    expect(profile.bands).toEqual([{ kind: 'total', label: '总耗时', ms: 3200, ratio: 1 }]);
  });

  it('labels tools as attempted when the turn ended in error', () => {
    const profile = buildAgentTransparency({
      toolsUsed: ['health_record'],
      completionStatus: 'error',
    });

    expect(profile.toolLabel).toBe('尝试调用 Skill');
  });

  it('labels tools as attempted for an explicit unknown status but preserves legacy rows', () => {
    const unknown = buildAgentTransparency({
      toolsUsed: ['health_record'],
      completionStatus: 'unknown',
    });
    const legacy = buildAgentTransparency({
      toolsUsed: ['health_record'],
    });

    expect(unknown.toolLabel).toBe('尝试调用 Skill');
    expect(legacy.toolLabel).toBe('调用 Skill');
  });

  it('shows sub-cent RMB costs without false zeroes or extra decimals', () => {
    const profile = buildAgentTransparency({
      elapsedMs: 900,
      llmUsage: {
        tokenplan_cost_cny: 0.0029,
        tokenplan_payg_value_cny: 0.0042,
        tokenplan_cost_estimated: true,
        cost_estimated: true,
      },
    });

    expect(profile.headline).toBe('约¥0.01以内 · 900ms');
    expect(profile.costLine).toBe('套餐折算 约¥0.01以内 · 按量价对照 约¥0.01以内');
  });

  it('does not turn an unknown TokenPlan model into a fake zero cost', () => {
    const profile = buildAgentTransparency({
      elapsedMs: 800,
      llmUsage: { providers: ['tokenplan'], prompt_tokens: 120 },
    });

    expect(profile.costLine).toBe('套餐折算 暂无法估算');
    expect(profile.headline).toBe('800ms');
  });

  it('summarizes failed LLM calls for client-side diagnosis', () => {
    const profile = buildAgentTransparency({
      llmUsage: {
        calls: 1,
        prompt_tokens: 120,
        failed_calls: 1,
        items: [
          {
            run_id: 'run_abc1234567890',
            success: false,
            error_class: 'quota_exhausted',
            error_type: 'insufficient_quota',
            error_code: 'insufficient_quota',
            error_message: 'Your token-plan quota has been exhausted.',
            recovery_action: 'fallback_attempted',
            recovery_model: 'gpt-5.5',
          },
        ],
      },
    });

    expect(profile.visible).toBe(true);
    expect(profile.errorLine).toBe('失败 1 次 · insufficient_quota · Your token-plan quota has been exhausted.');
    expect(profile.traceLine).toBe('run run_abc1234567890 · fallback_attempted · 备用 gpt-5.5');
  });

  it('formats compact durations and tokens', () => {
    expect(formatDurationMs(44)).toBe('44ms');
    expect(formatDurationMs(4100)).toBe('4.1s');
    expect(formatTokenCount(2460)).toBe('2.5k');
  });
});

describe('chatTransparency routing (模型路由透明化)', () => {
  it('fast_route_simple_turn 映射成中文并进入 profile.routing', () => {
    const profile = buildAgentTransparency({
      model: 'deepseek-v4-flash',
      elapsedMs: 2000,
      fallbackReasons: ['fast_route_simple_turn'],
    });
    expect(profile.routing).toEqual(['简单查询·自动用快模型']);
    expect(profile.visible).toBe(true);
  });

  it('工具切换类 reason 去重后只出一条标签', () => {
    const profile = buildAgentTransparency({
      elapsedMs: 1000,
      fallbackReasons: ['selected_model_tool_unreliable', 'selected_model_tool_stream_failed'],
    });
    expect(profile.routing).toEqual(['工具调用临时切到可靠模型']);
  });

  it('未知 reason 原样透出(fail-open 到可见, 不吞)', () => {
    expect(routingReasonLabel('some_future_reason')).toBe('some_future_reason');
    const profile = buildAgentTransparency({ elapsedMs: 1, fallbackReasons: ['some_future_reason'] });
    expect(profile.routing).toEqual(['some_future_reason']);
  });

  it('无 fallbackReasons 时 routing 为空数组', () => {
    const profile = buildAgentTransparency({ elapsedMs: 1000, model: 'qwen3.7-max' });
    expect(profile.routing).toEqual([]);
  });
});
