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

  it('prefers request-entry latency over the legacy post-compile clock', () => {
    const profile = buildAgentTransparency({
      elapsedMs: 5200,
      perf: {
        total_ms: 5200,
        llm_ttft_ms: 900,
        end_to_end_total_ms: 6100,
        end_to_end_ttft_ms: 1800,
      },
    });

    expect(profile.headline).toBe('6.1s');
    expect(profile.bands.find(band => band.label === '首字节')?.ms).toBe(1800);
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
    expect(profile.errorLine).toBe('失败 1 次 · insufficient_quota');
    expect(profile.errorLine).not.toContain('quota has been exhausted');
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


it('retains partial outcome meaning when legacy status is error', () => {
  const profile = buildAgentTransparency({ completionStatus: 'error', terminalStatus: 'partial', toolsUsed: ['health_query'] });
  expect(profile.headline).toContain('部分完成');
  expect(profile.toolLabel).toBe('尝试调用 Skill');
});

it('shows every measured model call separately from the agent round count', () => {
  const profile = buildAgentTransparency({
    model: 'qwen3.8-max', llmRounds: 1, completionStatus: 'complete',
    llmUsage: { calls: 2, items: [
      { caller: 'food_recognition.from_base64', model: 'qwen3.8-flash', latency_ms: 3100, prompt_tokens: 900, completion_tokens: 180, token_source: 'api', success: true },
      { caller: 'agent', model: 'qwen3.8-max', latency_ms: 27900, prompt_tokens: 17900, completion_tokens: 1400, cached_tokens: 12000, token_source: 'api', success: true },
    ] },
    perf: { turn_setup_ms: 0, write_verified_ms: 4000, first_card_ms: 4010, end_to_end_total_ms: 31800 },
  });
  expect(profile.modelCalls).toHaveLength(2);
  expect(profile.modelCalls[0].value).toContain('图片识别');
  expect(profile.modelCalls[0].value).toContain('qwen3.8-flash');
  expect(profile.modelCalls[0].value).toContain('输入 900');
  expect(profile.modelCalls[1].value).toContain('输入 17.9k');
  expect(profile.modelCalls[1].value).toContain('缓存命中 12k');
  expect(profile.milestones).toContainEqual({ label: '记录已核验', value: '4s' });
  expect(profile.milestones).toContainEqual({ label: '回复完成', value: '31.8s' });
});

it('does not invent per-call tokens, purpose, timing or success for legacy metadata', () => {
  const profile = buildAgentTransparency({ llmUsage: { calls: 2, items: [{ model: 'legacy' }, { model: 'new', success: false, prompt_tokens: 0, token_source: 'estimate' }] } });
  expect(profile.modelCalls[0].value).toBe('模型调用 · legacy');
  expect(profile.modelCalls[1].value).toContain('输入 0');
  expect(profile.modelCalls[1].value).toContain('估算');
  expect(profile.modelCalls[1].value).toContain('失败');
  expect(profile.milestones).toEqual([]);
});

it('marks missing image usage instead of presenting reported calls as the complete cost', () => {
  const profile = buildAgentTransparency({
    perf: { pre_llm_stages: { vision_ms: 3100 } },
    llmUsage: { calls: 2, items: [{ caller: 'agent_executor.run_stream', model: 'qwen3.6-flash' }, { caller: 'agent_executor.run_stream', model: 'qwen3.8-max' }] },
  });
  expect(profile.usageCoverageLine).toContain('图像阶段的独立调用尚无法核对');
  expect(profile.usageCoverageLine).toContain('不代表已核验的完整成本');
});

it('aligns verified record timing with request-entry timing and labels incomplete outcomes', () => {
  const profile = buildAgentTransparency({ terminalStatus: 'partial', perf: { turn_setup_ms: 200, write_verified_ms: 4000, end_to_end_total_ms: 9000 } });
  expect(profile.milestones).toContainEqual({ label: '记录已核验', value: '4.2s' });
  expect(profile.milestones).toContainEqual({ label: '本轮结束', value: '9s' });
  expect(profile.milestones.some(row => row.label === '回复完成')).toBe(false);
});


it.each([undefined, 'unknown'])('does not infer successful completion from duration with status %s', terminalStatus => {
  const profile = buildAgentTransparency({ terminalStatus, perf: { end_to_end_total_ms: 9000, write_verified_ms: 4000 } });
  expect(profile.milestones).toContainEqual({ label: '本轮结束', value: '9s' });
  expect(profile.milestones).toContainEqual({ label: '记录已核验', value: '4s（处理开始后）' });
  expect(profile.milestones.some(row => row.label === '回复完成')).toBe(false);
});
