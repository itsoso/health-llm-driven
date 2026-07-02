export interface LlmUsageProfileLike {
  calls?: number | null;
  prompt_tokens?: number | null;
  completion_tokens?: number | null;
  total_tokens?: number | null;
  cost_usd?: number | null;
}

export interface AgentPerfRoundLike {
  llm_gen_ms?: number | null;
  tool_exec_ms?: number | null;
  tools?: string[] | null;
}

export interface AgentPerfProfileLike {
  total_ms?: number | null;
  pre_llm_ms?: number | null;
  pre_llm_stages?: Record<string, number | null | undefined> | null;
  llm_ttft_ms?: number | null;
  llm_full_ms?: number | null;
  rounds?: AgentPerfRoundLike[] | null;
  orchestrator_tool_ms?: number | null;
}

export interface AgentTransparencyInput {
  elapsedMs?: number | null;
  llmRounds?: number | null;
  llmRoundsMs?: number[] | null;
  model?: string | null;
  llmUsage?: LlmUsageProfileLike | null;
  sourcesUsed?: string[] | null;
  toolsUsed?: string[] | null;
  perf?: AgentPerfProfileLike | null;
}

export interface AgentTransparencyBand {
  kind: 'prellm' | 'ttft' | 'gen' | 'tool' | 'orch' | 'total';
  label: string;
  ms: number;
  ratio: number;
}

export interface AgentTransparencyRow {
  label: string;
  value: string;
}

export interface AgentTransparencyProfile {
  visible: boolean;
  headline: string;
  tokenLine?: string;
  bands: AgentTransparencyBand[];
  stages: AgentTransparencyRow[];
  rounds: AgentTransparencyRow[];
  sources: string[];
  tools: string[];
}

const STAGE_LABELS: Array<[string, string]> = [
  ['conv_ms', '对话记忆'],
  ['opener_ms', '开场判定'],
  ['system_prompt_ms', '系统提示'],
  ['kb_ms', '知识检索'],
  ['inspect_ms', '数据审视'],
  ['history_ms', '历史回填'],
  ['vision_ms', '图像理解'],
];

function positive(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : 0;
}

function uniqueClean(values?: string[] | null): string[] {
  const out: string[] = [];
  for (const raw of values || []) {
    const value = String(raw || '').trim();
    if (value && !out.includes(value)) out.push(value);
  }
  return out;
}

export function formatDurationMs(value?: number | null): string {
  const ms = positive(value);
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1).replace(/\.0$/, '')}s`;
}

export function formatTokenCount(value?: number | null): string {
  const n = positive(value);
  if (n >= 1000) return `${(n / 1000).toFixed(1).replace(/\.0$/, '')}k`;
  return String(Math.round(n));
}

function formatCostUsd(value?: number | null): string | null {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) return null;
  return `$${value.toFixed(6).replace(/0+$/, '').replace(/\.$/, '')}`;
}

function buildTokenLine(usage?: LlmUsageProfileLike | null): string | undefined {
  if (!usage) return undefined;
  const input = positive(usage.prompt_tokens);
  const output = positive(usage.completion_tokens);
  const total = positive(usage.total_tokens) || input + output;
  if (!input && !output && !total) return undefined;
  const parts = [
    `Token 输入 ${formatTokenCount(input)}`,
    `输出 ${formatTokenCount(output)}`,
    `总 ${formatTokenCount(total)}`,
  ];
  const calls = positive(usage.calls);
  if (calls > 1) parts.push(`${Math.round(calls)}次`);
  const cost = formatCostUsd(usage.cost_usd);
  if (cost) parts.push(cost);
  return parts.join(' · ');
}

function buildBands(perf: AgentPerfProfileLike | null | undefined, elapsedMs: number): AgentTransparencyBand[] {
  const total = positive(perf?.total_ms) || elapsedMs;
  if (!total) return [];
  if (!perf) return [{ kind: 'total', label: '总耗时', ms: total, ratio: 1 }];

  const pre = positive(perf.pre_llm_ms);
  const firstTokenAt = Math.max(pre, positive(perf.llm_ttft_ms) || pre);
  const ttft = Math.max(0, firstTokenAt - pre);
  const rounds = Array.isArray(perf.rounds) ? perf.rounds : [];
  const tool = rounds.reduce((sum, round) => sum + positive(round?.tool_exec_ms), 0);
  const orch = positive(perf.orchestrator_tool_ms);
  const gen = Math.max(0, total - firstTokenAt - tool - orch);

  return [
    { kind: 'prellm' as const, label: '组装', ms: pre },
    { kind: 'ttft' as const, label: '首字节', ms: ttft },
    { kind: 'gen' as const, label: '生成', ms: gen },
    { kind: 'tool' as const, label: '工具', ms: tool },
    { kind: 'orch' as const, label: '编排', ms: orch },
  ]
    .filter(band => band.ms > 0)
    .map(band => ({ ...band, ratio: Math.max(0.02, band.ms / total) }));
}

function buildStages(perf?: AgentPerfProfileLike | null): AgentTransparencyRow[] {
  const stages = perf?.pre_llm_stages;
  if (!stages || typeof stages !== 'object') return [];
  return STAGE_LABELS
    .map(([key, label]) => ({ label, valueMs: positive(stages[key]) }))
    .filter(row => row.valueMs > 0)
    .map(row => ({ label: row.label, value: formatDurationMs(row.valueMs) }));
}

function buildRounds(input: AgentTransparencyInput): AgentTransparencyRow[] {
  const perfRounds = Array.isArray(input.perf?.rounds) ? input.perf?.rounds || [] : [];
  if (perfRounds.length > 0) {
    return perfRounds.map((round, index) => {
      const pieces: string[] = [];
      const gen = positive(round.llm_gen_ms);
      const tool = positive(round.tool_exec_ms);
      if (gen) pieces.push(`生成 ${formatDurationMs(gen)}`);
      if (tool) pieces.push(`工具 ${formatDurationMs(tool)}`);
      const tools = uniqueClean(round.tools || undefined);
      if (tools.length > 0) pieces.push(tools.join(', '));
      return {
        label: `第 ${index + 1} 轮`,
        value: pieces.join(' · ') || '已完成',
      };
    });
  }

  const legacy = Array.isArray(input.llmRoundsMs) ? input.llmRoundsMs : [];
  return legacy
    .filter(ms => positive(ms) > 0)
    .map((ms, index) => ({ label: `第 ${index + 1} 轮`, value: `生成 ${formatDurationMs(ms)}` }));
}

export function buildAgentTransparency(input: AgentTransparencyInput): AgentTransparencyProfile {
  const total = positive(input.perf?.total_ms) || positive(input.elapsedMs);
  const roundsCount = positive(input.llmRounds) || positive(input.perf?.rounds?.length);
  const headlineParts: string[] = [];
  if (total) headlineParts.push(formatDurationMs(total));
  if (roundsCount) headlineParts.push(`${Math.round(roundsCount)}轮`);
  const model = String(input.model || '').trim();
  if (model) headlineParts.push(model);

  const sources = uniqueClean(input.sourcesUsed);
  const tools = uniqueClean(input.toolsUsed);
  const tokenLine = buildTokenLine(input.llmUsage);
  const bands = buildBands(input.perf, total);
  const stages = buildStages(input.perf);
  const rounds = buildRounds(input);
  const visible = headlineParts.length > 0 || !!tokenLine || sources.length > 0 || tools.length > 0;

  return {
    visible,
    headline: headlineParts.join(' · '),
    tokenLine,
    bands,
    stages,
    rounds,
    sources,
    tools,
  };
}
