export interface LlmUsageCallLike {
  run_id?: string | null;
  provider?: string | null;
  model?: string | null;
  success?: boolean | null;
  error_class?: string | null;
  error_type?: string | null;
  error_code?: string | null;
  error_message?: string | null;
  recovery_action?: string | null;
  recovery_model?: string | null;
}

export interface LlmUsageProfileLike {
  run_id?: string | null;
  calls?: number | null;
  prompt_tokens?: number | null;
  completion_tokens?: number | null;
  total_tokens?: number | null;
  cost_usd?: number | null;
  cost_cny?: number | null;
  cost_estimated?: boolean | null;
  tokenplan_credits_estimate?: number | null;
  tokenplan_cost_cny?: number | null;
  tokenplan_payg_value_cny?: number | null;
  tokenplan_cost_estimated?: boolean | null;
  providers?: string[] | null;
  failed_calls?: number | null;
  items?: LlmUsageCallLike[] | null;
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
  completionStatus?: string | null;
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
  costLine?: string;
  tokenLine?: string;
  errorLine?: string;
  traceLine?: string;
  bands: AgentTransparencyBand[];
  stages: AgentTransparencyRow[];
  rounds: AgentTransparencyRow[];
  sources: string[];
  tools: string[];
  toolLabel: '调用 Skill' | '尝试调用 Skill';
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
  if (value < 0.01) return '<$0.01';
  return `$${value.toFixed(2)}`;
}

function formatCostCny(value?: number | null): string | null {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) return null;
  if (value < 0.01) return '¥0.01以内';
  return `¥${value.toFixed(2)}`;
}

function hasTokenPlanUsage(usage: LlmUsageProfileLike): boolean {
  return (usage.providers || []).some(provider => String(provider || '').toLowerCase() === 'tokenplan')
    || (usage.items || []).some(item => String(item?.provider || '').toLowerCase() === 'tokenplan');
}

function buildTokenLine(usage?: LlmUsageProfileLike | null): string | undefined {
  if (!usage) return undefined;
  const input = positive(usage.prompt_tokens);
  const output = positive(usage.completion_tokens);
  const total = positive(usage.total_tokens) || input + output;
  if (!input && !output && !total) return undefined;
  const parts = [
    `输入 ${formatTokenCount(input)}`,
    `输出 ${formatTokenCount(output)}`,
    `总 ${formatTokenCount(total)}`,
  ];
  const calls = positive(usage.calls);
  if (calls > 1) parts.push(`${Math.round(calls)}次`);
  return parts.join(' · ');
}

function buildCostLine(usage?: LlmUsageProfileLike | null): string | undefined {
  if (!usage) return undefined;
  const plan = formatCostCny(usage.tokenplan_cost_cny);
  const payg = formatCostCny(usage.tokenplan_payg_value_cny)
    || formatCostCny(usage.cost_cny)
    || formatCostUsd(usage.cost_usd);
  const parts: string[] = [];
  if (plan) parts.push(`套餐折算 ${usage.tokenplan_cost_estimated === false ? '' : '约'}${plan}`);
  else if (hasTokenPlanUsage(usage)) parts.push('套餐折算 暂无法估算');
  if (payg) parts.push(`按量价对照 ${usage.cost_estimated === false ? '' : '约'}${payg}`);
  return parts.length ? parts.join(' · ') : undefined;
}

function cleanText(value: unknown): string {
  return String(value || '').replace(/\s+/g, ' ').trim();
}

function truncate(value: string, max = 96): string {
  return value.length > max ? `${value.slice(0, max - 1)}…` : value;
}

function buildErrorLine(usage?: LlmUsageProfileLike | null): string | undefined {
  if (!usage) return undefined;
  const items = Array.isArray(usage.items) ? usage.items : [];
  const failedItems = items.filter(item => item?.success === false || item?.error_code || item?.error_type);
  const failedCount = positive(usage.failed_calls) || failedItems.length;
  if (!failedCount) return undefined;

  const first = failedItems[0];
  const code = cleanText(first?.error_code || first?.error_type);
  const message = truncate(cleanText(first?.error_message));
  const parts = [`失败 ${Math.round(failedCount)} 次`];
  if (code) parts.push(code);
  if (message) parts.push(message);
  return parts.join(' · ');
}

function buildTraceLine(usage?: LlmUsageProfileLike | null): string | undefined {
  if (!usage) return undefined;
  const runId = cleanText(usage.run_id || usage.items?.find(item => item?.run_id)?.run_id);
  const recovery = usage.items?.find(item => item?.recovery_action || item?.recovery_model);
  const parts: string[] = [];
  if (runId) parts.push(`run ${runId.slice(0, 18)}`);
  if (recovery?.recovery_action) parts.push(cleanText(recovery.recovery_action));
  if (recovery?.recovery_model) parts.push(`备用 ${cleanText(recovery.recovery_model)}`);
  return parts.length ? parts.join(' · ') : undefined;
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
  const model = String(input.model || '').trim();
  const planCost = formatCostCny(input.llmUsage?.tokenplan_cost_cny);
  if (planCost) headlineParts.push(`约${planCost}`);
  if (total) headlineParts.push(formatDurationMs(total));
  if (roundsCount) headlineParts.push(`${Math.round(roundsCount)}轮`);
  if (model) headlineParts.push(model);

  const sources = uniqueClean(input.sourcesUsed);
  const tools = uniqueClean(input.toolsUsed);
  const toolLabel = input.completionStatus != null
    && input.completionStatus !== 'complete'
    ? '尝试调用 Skill'
    : '调用 Skill';
  const tokenLine = buildTokenLine(input.llmUsage);
  const costLine = buildCostLine(input.llmUsage);
  const errorLine = buildErrorLine(input.llmUsage);
  const traceLine = buildTraceLine(input.llmUsage);
  const bands = buildBands(input.perf, total);
  const stages = buildStages(input.perf);
  const rounds = buildRounds(input);
  const visible = headlineParts.length > 0 || !!costLine || !!tokenLine || !!errorLine || !!traceLine || sources.length > 0 || tools.length > 0;

  return {
    visible,
    headline: headlineParts.join(' · '),
    costLine,
    tokenLine,
    errorLine,
    traceLine,
    bands,
    stages,
    rounds,
    sources,
    tools,
    toolLabel,
  };
}
