import { buildAgentTransparency, formatDurationMs, formatTokenCount } from '../chatTransparency';

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
    expect(profile.headline).toBe('29.2s · 5轮 · qwen3.7-plus');
    expect(profile.tokenLine).toBe('Token 输入 1.8k · 输出 620 · 总 2.5k · 5次 · $0.0042');
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

  it('formats compact durations and tokens', () => {
    expect(formatDurationMs(44)).toBe('44ms');
    expect(formatDurationMs(4100)).toBe('4.1s');
    expect(formatTokenCount(2460)).toBe('2.5k');
  });
});
