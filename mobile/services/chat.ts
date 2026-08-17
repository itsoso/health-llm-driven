import { getToken } from './auth';
import { BASE_URL, WEB_SESSION_AUTH_SENTINEL } from './api';
import { buildClientCapsHeader } from './clientCaps';
import { sanitizeChatErrorMessage } from '../utils/chatErrorMessage';
import type { AgentPerfProfileLike } from '../utils/chatTransparency';
import { normalizeWriteReceipt, type WriteReceipt } from './writeReceipt';
import type { MedicationSafetyAlert } from './medications';
import { assertAppEgressAllowed, enforceAppEgressAllowed } from './egressPolicy';

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export class ChatStreamHttpError extends Error {
  readonly status: number;
  readonly detail?: string;

  constructor(status: number, detail?: string) {
    super(detail || `请求失败 (status: ${status})`);
    this.name = 'ChatStreamHttpError';
    this.status = status;
    this.detail = detail;
  }
}

const SERVER_BUSY_HTTP_DETAIL = '上一条消息仍在处理，请稍后重试';

function chatStreamHttpError(status: number, responseText: string): ChatStreamHttpError {
  let detail: string | undefined;
  try {
    const body = JSON.parse(responseText);
    if (
      status === 409
      && typeof body?.detail === 'string'
      && body.detail.includes('上一条消息仍在处理')
    ) {
      detail = SERVER_BUSY_HTTP_DETAIL;
    }
  } catch {
    // An HTTP error document is not an SSE payload. Keep malformed bodies out
    // of the error so prompts, gateway pages, and provider details cannot leak.
  }
  return new ChatStreamHttpError(status, detail);
}

interface ClientTimeContext {
  client_now_iso: string;
  timezone?: string;
  timezone_offset_minutes: number;
  locale?: string;
}

export interface Conversation {
  id: number;
  title?: string;
  created_at: string;
  updated_at?: string;
  last_message?: string;
}

export interface StreamCardDescriptor {
  type: string;
  data: any;
  actions?: any[];
}

export interface LlmUsageCall {
  run_id?: string | null;
  provider?: string;
  model?: string;
  caller?: string;
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
  cost_usd?: number;
  cost_cny?: number;
  cost_estimated?: boolean;
  cost_source?: string;
  tokenplan_credits_estimate?: number;
  tokenplan_cost_cny?: number;
  tokenplan_payg_value_cny?: number;
  tokenplan_cost_estimated?: boolean;
  tokenplan_cost_source?: string;
  latency_ms?: number | null;
  success?: boolean;
  error_class?: string | null;
  error_type?: string | null;
  error_code?: string | null;
  error_message?: string | null;
  recovery_action?: string | null;
  recovery_model?: string | null;
}

export interface LlmUsageProfile {
  run_id?: string | null;
  calls?: number;
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
  cost_usd?: number;
  cost_cny?: number;
  cost_estimated?: boolean;
  cost_sources?: string[];
  tokenplan_credits_estimate?: number;
  tokenplan_cost_cny?: number;
  tokenplan_payg_value_cny?: number;
  tokenplan_cost_estimated?: boolean;
  tokenplan_cost_source?: string;
  tokenplan_monthly_fee_cny?: number;
  tokenplan_monthly_credits?: number;
  latency_ms?: number | null;
  failed_calls?: number;
  models?: string[];
  providers?: string[];
  items?: LlmUsageCall[];
}

export type AgentPerfProfile = AgentPerfProfileLike;

export interface AgentTurnStatus {
  clientTurnId: string;
  runId?: string;
  status: string;
  requestPersisted: boolean;
  responsePersisted: boolean;
  conversationId?: number;
  retryable: boolean;
  errorCode?: string;
}

export interface MedicationBatchStreamDecision {
  intentId: number;
  decisionStatus: 'executed' | 'dismissed' | 'expired';
  writeReceipts: WriteReceipt[];
  safetyAlerts: MedicationSafetyAlert[];
}

export interface StreamEvent {
  type: 'start' | 'persisted' | 'token' | 'tool' | 'status' | 'card' | 'done' | 'error';
  content?: string;
  /** 面向用户的安全思考/进度摘要,不包含模型原始推理链或工具参数。 */
  thought?: string;
  thinkingSteps?: string[];
  // P0-1 渐进渲染: status SSE 事件映射出的"细状态行"标签 (中文人话), 首 token 前显示.
  // 与 thought/thinkingSteps 分离 —— status 行是气泡顶部的单行进度, 不进思考步骤列表.
  statusLabel?: string;
  /** status 事件的原始阶段 (accepted / tool / synthesis), 供消费端语义判定。 */
  statusStage?: string;
  conversationId?: number;
  userMessageId?: number;
  clientTurnId?: string;
  imageUrls?: string[];
  messageId?: number;
  requestPersisted?: boolean;
  anchor?: string;
  card?: StreamCardDescriptor;
  toolName?: string;
  toolSuccess?: boolean;
  writeAttempted?: boolean;
  writeCompleted?: boolean;
  writeOutcome?: 'verified' | 'rejected' | 'failed' | 'uncertain';
  dispatchStarted?: boolean;
  resubmitSafe?: boolean;
  errorCode?: string;
  receipt?: WriteReceipt;
  // I Phase 2: health_record 时附 record_type + record_data 让前端能 sniff 录入摘要
  recordType?: string;
  recordData?: Record<string, any>;
  // 2026-05-13: 每轮对话耗时 + 模型名 (性能可观测)
  elapsedMs?: number;
  llmMs?: number;
  llmRounds?: number;
  llmRoundsMs?: number[];
  model?: string;
  llmUsage?: LlmUsageProfile;
  perf?: AgentPerfProfile;
  // 2026-05-14 #4: 可解释性 — AI 用了什么数据
  sourcesUsed?: string[];
  // 2026-06-12: 本轮调用的 Skill / 工具名 (后端 done.tools_used; 去重保序, 空 [])
  toolsUsed?: string[];
  completionStatus?: 'complete' | 'interrupted' | 'error' | 'unknown';
  terminalRetryable?: boolean;
  terminalErrorCode?: string;
  retryMode?: 'retry_source';
  // SSE done 事件里的动态卡片，由 useChatEngine 交给 card registry 渲染。
  // health_evidence_manifest 以 health_evidence card.data 为 Mobile 唯一展示投影，
  // 不再复制一份可漂移的 UI 状态。
  cards?: StreamCardDescriptor[];
  writeReceipts?: WriteReceipt[];
  medicationBatchDecision?: MedicationBatchStreamDecision;
}

function medicationSafetyAlerts(value: unknown): MedicationSafetyAlert[] {
  if (!Array.isArray(value)) return [];
  return value.filter((raw): raw is MedicationSafetyAlert => (
    raw != null
    && typeof raw === 'object'
    && !Array.isArray(raw)
    && typeof (raw as Record<string, unknown>).rule_id === 'string'
    && typeof (raw as Record<string, unknown>).category === 'string'
    && typeof (raw as Record<string, unknown>).title === 'string'
    && typeof (raw as Record<string, unknown>).message === 'string'
  ));
}

function medicationBatchStreamDecision(
  decisionValue: unknown,
  legacyWriteReceipts: unknown,
  legacySafetyAlerts: unknown,
): MedicationBatchStreamDecision | undefined {
  if (!decisionValue || typeof decisionValue !== 'object' || Array.isArray(decisionValue)) {
    return undefined;
  }
  const decision = decisionValue as Record<string, unknown>;
  const intentId = Number(decision.intent_id);
  const decisionStatus = decision.status;
  if (
    !Number.isInteger(intentId)
    || intentId <= 0
    || (decisionStatus !== 'executed' && decisionStatus !== 'dismissed' && decisionStatus !== 'expired')
  ) {
    return undefined;
  }
  const rawReceipts = Array.isArray(decision.write_receipts)
    ? decision.write_receipts
    : legacyWriteReceipts;
  const rawAlerts = Array.isArray(decision.safety_alerts)
    ? decision.safety_alerts
    : legacySafetyAlerts;
  const writeReceipts = decisionStatus === 'executed' && Array.isArray(rawReceipts)
    ? rawReceipts
      .map(normalizeWriteReceipt)
      .filter((receipt): receipt is WriteReceipt => !!receipt)
    : [];
  return {
    intentId,
    decisionStatus,
    writeReceipts,
    safetyAlerts: decisionStatus === 'executed' ? medicationSafetyAlerts(rawAlerts) : [],
  };
}

const TOOL_THOUGHT_LABELS: Record<string, string> = {
  health_query: '健康数据',
  health_record: '记录信息',
  health_manage: '健康记录',
};

function toolThoughtLabel(toolName?: string): string {
  const tool = (toolName || '').trim();
  if (!tool) return '相关数据';
  if (TOOL_THOUGHT_LABELS[tool]) return TOOL_THOUGHT_LABELS[tool];
  if (tool.includes('weather') || tool.includes('environment')) return '环境数据';
  if (tool.includes('calendar')) return '日程上下文';
  if (tool.includes('medical') || tool.includes('exam') || tool.includes('lab')) return '体检数据';
  if (tool.includes('genetic')) return '基因数据';
  if (tool.includes('supplement')) return '补剂数据';
  if (tool.includes('diet')) return '饮食数据';
  if (tool.includes('sleep')) return '睡眠数据';
  return '相关数据';
}

function writeAttemptFromToolCall(toolName: string, rawArgs: unknown): boolean | undefined {
  if (toolName === 'health_record') return true;
  if (!['health_manage', 'intervention_cycle'].includes(toolName)) return undefined;
  try {
    const args = typeof rawArgs === 'string' ? JSON.parse(rawArgs) : rawArgs;
    if (!args || typeof args !== 'object' || Array.isArray(args)) return false;
    if (toolName === 'health_manage') {
      return ['update', 'delete'].includes(String((args as any).operation || ''));
    }
    return ['start', 'update', 'cancel'].includes(String((args as any).action || ''));
  } catch {
    return false;
  }
}

function buildClientTimeContext(): ClientTimeContext {
  const now = new Date();
  let timezone: string | undefined;
  let locale: string | undefined;
  try {
    const resolved = Intl.DateTimeFormat().resolvedOptions();
    timezone = typeof resolved.timeZone === 'string' ? resolved.timeZone : undefined;
    locale = typeof resolved.locale === 'string' ? resolved.locale : undefined;
  } catch {
    timezone = undefined;
    locale = undefined;
  }
  return {
    client_now_iso: now.toISOString(),
    timezone,
    // Date#getTimezoneOffset is minutes west of UTC. Store minutes east of UTC.
    timezone_offset_minutes: -now.getTimezoneOffset(),
    locale,
  };
}

/**
 * P0-1 渐进渲染 · status 行 (刀⑤): 把 status SSE 事件映射成气泡顶部的单行进度标签。
 *
 * 新契约 (backend additive): stage ∈ { accepted, tool, synthesis }。
 *  - accepted   → 流一打开立刻发, 首 token 前显示 "正在理解…"。
 *  - tool       → 每轮工具执行前发, label 是后端确定性映射的"中文人话"动词短语
 *                 (如 "正在记录饮水…" / "查看步数数据…"), 无 label 时兜底 "正在处理…"。
 *  - synthesis  → 最终回答开始生成时发, 显示 "正在整理回答…"。
 *
 * 兼容旧契约 stage ∈ { vision, thinking } 也给一个合理 label (avoid 空态)。
 * 未知 stage → 返回 undefined (调用方忽略, 与既有 fall-through 一致)。
 */
function statusStageLabel(stage?: string, label?: string | null): string | undefined {
  const s = (stage || '').trim();
  const trimmedLabel = typeof label === 'string' ? label.trim() : '';
  switch (s) {
    case 'accepted':
      return '正在理解…';
    case 'tool':
      // label 来自后端确定性映射表 (工具名→动词短语); 缺失时兜底.
      return trimmedLabel || '正在处理…';
    case 'synthesis':
      return '正在整理回答…';
    case 'vision':
      return '识别图片中…';
    case 'thinking':
      return '正在思考…';
    default:
      return undefined;
  }
}

/**
 * Stream chat using XMLHttpRequest (React Native doesn't support ReadableStream).
 * Yields StreamEvent objects instead of raw strings.
 * Pass an AbortSignal to cancel the stream externally (e.g. when app backgrounds).
 */
export async function* streamChat(
  message: string,
  conversationId?: number,
  images?: { base64?: string; type?: string }[],
  signal?: AbortSignal,
  extraContext?: string,
  channel: 'typed' | 'voice' | 'siri' = 'typed',
  clientTurnId?: string,
  egressIntent: { explicitCloudAI?: boolean } = {},
): AsyncGenerator<StreamEvent, void, unknown> {
  try {
    assertAppEgressAllowed(egressIntent);
  } catch {
    // Blocked paths wait for the local audit write before rejecting; allowed
    // cloud paths stay synchronous here so streaming startup is unchanged.
    await enforceAppEgressAllowed(egressIntent);
  }
  const token = await getToken();
  // channel = 传输层输入通道声明(非 LLM 参数):打字免症状二次确认;
  // 语音(转写有失真风险)fail-closed 保留确认 —— 语音入口必须显式传 'voice'。
  const body: Record<string, any> = { message, channel, client_time_context: buildClientTimeContext() };
  if (clientTurnId) body.client_turn_id = clientTurnId;
  if (conversationId) body.conversation_id = conversationId;
  if (extraContext && extraContext.trim()) body.extra_context = extraContext.trim();
  if (images && images.length > 0) {
    // Backward compatible: single image uses legacy fields, multi uses images array
    if (images.length === 1) {
      body.image_base64 = images[0].base64;
      body.image_type = images[0].type || 'jpeg';
    } else {
      body.images = images.map(img => ({ base64: img.base64, type: img.type || 'jpeg' }));
    }
  }

  // Use a promise-based wrapper around XHR with chunked callback
  const chunks: string[] = [];
  let resolve: (() => void) | null = null;
  let done = false;
  let error: Error | null = null;
  let processed = 0;

  const xhr = new XMLHttpRequest();
  xhr.open('POST', `${BASE_URL}/agent/stream`);
  xhr.setRequestHeader('Content-Type', 'application/json');
  if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`);
  // 客户端 GenUI 能力声明:走 buildClientCapsHeader 单一真源(含点亮的 metric_table /
  // diet_summary / sleep_summary caps)。此前这里硬编码基础 caps、buildClientCapsHeader 是死代码,
  // 导致所有结构化卡的 cap 从未到达后端 —— 卡在生产从不出现。别再硬编码。
  xhr.setRequestHeader('X-Reva-Client-Caps', buildClientCapsHeader());
  xhr.responseType = 'text';

  // Wire up abort signal
  if (signal) {
    if (signal.aborted) { throw new Error('aborted'); }
    signal.addEventListener('abort', () => {
      error = new Error('aborted');
      done = true;
      try { xhr.abort(); } catch {}
      resolve?.();
    });
  }

  xhr.onprogress = () => {
    if (xhr.status < 200 || xhr.status >= 300) {
      return;
    }
    const newText = xhr.responseText.slice(processed);
    processed = xhr.responseText.length;
    if (newText) {
      chunks.push(newText);
      resolve?.();
    }
  };

  xhr.onload = () => {
    if (xhr.status < 200 || xhr.status >= 300) {
      error = chatStreamHttpError(xhr.status, xhr.responseText);
      done = true;
      resolve?.();
      return;
    }
    // Process any remaining text
    const remaining = xhr.responseText.slice(processed);
    if (remaining) chunks.push(remaining);
    done = true;
    resolve?.();
  };

  xhr.onerror = () => {
    error = new Error(`网络请求失败 (status: ${xhr.status})`);
    done = true;
    resolve?.();
  };

  xhr.ontimeout = () => {
    error = new Error('请求超时');
    done = true;
    resolve?.();
  };

  xhr.timeout = 300000; // Commercial gateway responses can take several minutes.
  xhr.send(JSON.stringify(body));

  // Parse SSE lines from accumulated chunks
  let buffer = '';
  const doneSentinel = Symbol('done');

  const streamEventFromPayload = (payload: string): StreamEvent | typeof doneSentinel | undefined => {
    if (payload === '[DONE]') return doneSentinel;

    try {
      const parsed = JSON.parse(payload);

      if (parsed.type === 'status' && !parsed.event) {
        // 后端扁平进度家族 {"type":"status","stage",...,"label"?} (web/mac 同源契约),
        // 与下面既有的 {"event":"status","data":{...}} 嵌套家族并存, 语义相同。
        const stage = typeof parsed.stage === 'string' ? parsed.stage : undefined;
        const statusLabel = statusStageLabel(stage, parsed.label);
        if (statusLabel) return { type: 'status', statusLabel, statusStage: stage };
        return undefined;
      }

      if (parsed.event === 'request_persisted') {
        const imageUrls = Array.isArray(parsed.data?.image_urls)
          ? parsed.data.image_urls.filter((value: unknown): value is string => typeof value === 'string' && value.trim().length > 0)
          : undefined;
        return {
          type: 'persisted',
          conversationId: parsed.data?.conversation_id,
          userMessageId: parsed.data?.user_message_id,
          clientTurnId: parsed.data?.client_turn_id,
          imageUrls,
        };
      } else if (parsed.event === 'agent_start') {
        return {
          type: 'start',
          conversationId: parsed.data?.conversation_id,
          thought: '正在理解你的问题',
        };
      } else if (parsed.event === 'token') {
        const text = parsed.data?.content || '';
        if (text) return { type: 'token', content: text };
      } else if (parsed.event === 'tool_call') {
        const tool = parsed.data?.tool || '';
        const writeAttempted = writeAttemptFromToolCall(tool, parsed.data?.args);
        // 不把 "🔧 health_record (第1轮)" 这种技术文本注入消息气泡
        // toolName 仍传给前端, cards dispatcher / analytics 可用
        return {
          type: 'tool',
          content: '',
          toolName: tool,
          ...(typeof writeAttempted === 'boolean' ? { writeAttempted } : {}),
          thought: `读取${toolThoughtLabel(tool)}`,
        };
      } else if (parsed.event === 'tool_result') {
        const tool = parsed.data?.tool || '';
        const ok = parsed.data?.success;
        const label = toolThoughtLabel(tool);
        const writeCompleted = typeof parsed.data?.write_completed === 'boolean'
          ? parsed.data.write_completed
          : undefined;
        const writeAttempted = typeof parsed.data?.write_attempted === 'boolean'
          ? parsed.data.write_attempted
          : undefined;
        const receipt = normalizeWriteReceipt(parsed.data?.receipt);
        const writeOutcome = ['verified', 'rejected', 'failed', 'uncertain'].includes(
          parsed.data?.write_outcome,
        )
          ? parsed.data.write_outcome as StreamEvent['writeOutcome']
          : undefined;
        const writeThought = writeOutcome === 'verified'
          ? `已取得${label}`
          : writeOutcome === 'rejected'
            ? '记录信息需要补充'
            : writeOutcome === 'uncertain'
              ? '记录状态需要核对'
              : writeOutcome === 'failed'
                ? '记录未完成'
                : undefined;
        // 工具结果是回合内的中间状态，失败后 Agent 仍可能纠正参数并重试成功。
        // 不把临时失败写进永久正文；整轮失败由后端终态文本或 error 事件呈现。
        return {
          type: 'tool',
          content: '',
          toolName: tool,
          toolSuccess: ok,
          ...(typeof writeAttempted === 'boolean' ? { writeAttempted } : {}),
          ...(typeof writeCompleted === 'boolean' ? { writeCompleted } : {}),
          ...(writeOutcome ? { writeOutcome } : {}),
          ...(typeof parsed.data?.dispatch_started === 'boolean'
            ? { dispatchStarted: parsed.data.dispatch_started }
            : {}),
          ...(typeof parsed.data?.resubmit_safe === 'boolean'
            ? { resubmitSafe: parsed.data.resubmit_safe }
            : {}),
          ...(typeof parsed.data?.error_code === 'string'
            ? { errorCode: parsed.data.error_code }
            : {}),
          ...(receipt ? { receipt } : {}),
          thought: writeThought ?? (ok ? `已取得${label}` : `${label}暂时不可用`),
          // I Phase 2: health_record 时后端附 record_type + record_data, 前端 sniff 录入摘要
          recordType: parsed.data?.record_type,
          recordData: parsed.data?.record_data,
        };
      } else if (parsed.event === 'status') {
        // P0-1 渐进渲染: TTFT 期间后端推送阶段状态 (token 前): accepted/tool/synthesis
        // (兼容旧 vision/thinking). 映射为气泡顶部的"细状态行" (statusLabel), 而非思考步骤 ——
        // status 行是 首 token 前的单行进度, 完成后收进思考完成态 pill (刀⑤).
        // label 优先取后端确定性映射 (parsed.data.label), 缺失时按 stage 兜底.
        // 未知 stage → 返回 undefined, 保持既有 fall-through 忽略行为 (调用方也会静默忽略未知事件).
        const stage = typeof parsed.data?.stage === 'string' ? parsed.data.stage : undefined;
        const statusLabel = statusStageLabel(
          stage,
          parsed.data?.label ?? parsed.data?.detail,
        );
        if (statusLabel) return { type: 'status', statusLabel, statusStage: stage };
      } else if (parsed.event === 'card' || parsed.event === 'proposed_card') {
        const descriptor = parsed.data?.descriptor || parsed.data?.card || parsed.data;
        if (descriptor && typeof descriptor.type === 'string') {
          return {
            type: 'card',
            anchor: typeof parsed.data?.anchor === 'string' ? parsed.data.anchor : undefined,
            card: {
              type: descriptor.type,
              data: descriptor.data ?? {},
              actions: Array.isArray(descriptor.actions) ? descriptor.actions : undefined,
            },
          };
        }
      } else if (parsed.event === 'done') {
        const llmUsage = parsed.data?.llm_usage && typeof parsed.data.llm_usage === 'object'
          ? parsed.data.llm_usage
          : undefined;
        const perf = parsed.data?.perf && typeof parsed.data.perf === 'object'
          ? parsed.data.perf
          : undefined;
        const writeReceipts = Array.isArray(parsed.data?.write_receipts)
          ? parsed.data.write_receipts
            .map(normalizeWriteReceipt)
            .filter((receipt: WriteReceipt | undefined): receipt is WriteReceipt => !!receipt)
          : undefined;
        const medicationDecision = medicationBatchStreamDecision(
          parsed.data?.medication_batch_decision,
          parsed.data?.write_receipts,
          parsed.data?.safety_alerts,
        );
        const turnOutcome = parsed.data?.turn_outcome;
        const recoveryAction = parsed.data?.recovery_action;
        const retrySourceActive = Boolean(
          turnOutcome?.retryable === true
          && recoveryAction?.type === 'retry_source_turn'
          && recoveryAction?.status === 'active'
        );
        return {
          type: 'done',
          conversationId: parsed.data?.conversation_id,
          messageId: parsed.data?.message_id,
          requestPersisted: typeof parsed.data?.request_persisted === 'boolean'
            ? parsed.data.request_persisted
            : undefined,
          elapsedMs: parsed.data?.elapsed_ms,
          llmMs: parsed.data?.llm_ms,
          llmRounds: parsed.data?.llm_rounds,
          llmRoundsMs: Array.isArray(parsed.data?.llm_rounds_ms) ? parsed.data.llm_rounds_ms : undefined,
          model: parsed.data?.model,
          ...(llmUsage ? { llmUsage } : {}),
          ...(perf ? { perf } : {}),
          sourcesUsed: Array.isArray(parsed.data?.sources_used) ? parsed.data.sources_used : undefined,
          toolsUsed: Array.isArray(parsed.data?.tools_used) ? parsed.data.tools_used : undefined,
          completionStatus: parsed.data?.completion_status,
          ...(typeof turnOutcome?.reason_code === 'string'
            ? { terminalErrorCode: turnOutcome.reason_code }
            : {}),
          ...(turnOutcome && typeof turnOutcome === 'object'
            ? { terminalRetryable: retrySourceActive }
            : {}),
          ...(retrySourceActive ? { retryMode: 'retry_source' as const } : {}),
          thinkingSteps: normalizeThinkingSteps(parsed.data?.thinking_steps),
          cards: Array.isArray(parsed.data?.cards) ? parsed.data.cards : undefined,
          writeReceipts: writeReceipts?.length ? writeReceipts : undefined,
          ...(medicationDecision ? { medicationBatchDecision: medicationDecision } : {}),
        };
      } else if (parsed.event === 'error') {
        return {
          type: 'error',
          content: sanitizeChatErrorMessage(parsed.data?.message || parsed.data?.detail, '请求失败'),
        };
      }
    } catch {
      // non-JSON line, skip
    }
    return undefined;
  };

  while (true) {
    // Wait for new data or completion
    if (chunks.length === 0 && !done) {
      await new Promise<void>((r) => { resolve = r; });
      resolve = null;
    }

    if (error) throw error;

    // Process all available chunks
    while (chunks.length > 0) {
      buffer += chunks.shift()!;
    }

    // Parse complete lines
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed || !trimmed.startsWith('data:')) continue;
      const payload = trimmed.slice(5).trim();
      const evt = streamEventFromPayload(payload);
      if (evt === doneSentinel) return;
      if (evt) yield evt;
    }

    if (done && chunks.length === 0) break;
  }

  // Process any remaining buffer
  if (buffer.trim()) {
    const trimmed = buffer.trim();
    if (trimmed.startsWith('data:')) {
      const payload = trimmed.slice(5).trim();
      const evt = streamEventFromPayload(payload);
      if (evt !== doneSentinel && evt) yield evt;
    }
  }
}

function normalizeThinkingSteps(value: unknown): string[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const out: string[] = [];
  for (const step of value) {
    const normalized = String(step || '').trim();
    if (normalized && !out.includes(normalized)) out.push(normalized);
  }
  return out.length > 0 ? out.slice(-8) : undefined;
}

export interface ConversationsPage {
  items: Conversation[];
  total: number;
}

export interface ConversationListOptions {
  /** Only conversations with at least one user turn, for default resume. */
  resumeOnly?: boolean;
}

/**
 * 分页拉取对话列表。透传 offset/limit/search(标题∪内容)/title_like/resume_only 给 /agent/conversations
 * (后端返回 { items, total, limit, offset })，返回 items + total 供无限下拉判断
 * 是否还有更多 (items.length < total)。
 *
 * 后端约束: limit ∈ [1, 100] (agent.py list_conversations Query 校验)。
 * 请求失败会抛错 (fail-loud) — 调用方负责保留已加载列表并展示重试。
 */
export async function getConversationsPage({
  offset = 0,
  limit = 20,
  titleLike,
  search,
  resumeOnly = false,
}: { offset?: number; limit?: number; titleLike?: string; search?: string; resumeOnly?: boolean } = {}): Promise<ConversationsPage> {
  const token = await getToken();
  await enforceAppEgressAllowed({
    cloudCredentialPresent: Boolean(token && token !== WEB_SESSION_AUTH_SENTINEL),
  });
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (resumeOnly) params.set('resume_only', 'true');
  // search 匹配标题 ∪ 消息正文(后端 _apply_search);title_like 仅标题(旧参数,search 优先)。
  if (search) params.set('search', search);
  else if (titleLike) params.set('title_like', titleLike);
  const res = await fetch(`${BASE_URL}/agent/conversations?${params}`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: 'no-store',
  });
  if (!res.ok) {
    throw new Error(`getConversationsPage failed: ${res.status}`);
  }
  const data = await res.json();
  const items: Conversation[] = data.items ?? [];
  const total: number = typeof data.total === 'number' ? data.total : items.length;
  return { items, total };
}

/**
 * 兼容旧调用方 (voice-chat / useChatEngine 的最近会话探测) — 取第一页 items。
 * 失败时返回空数组 (保持历史行为: 这些调用方不处理异常)。
 */
export async function getConversations(
  titleLike?: string,
  options: ConversationListOptions = {},
): Promise<Conversation[]> {
  try {
    const { items } = await getConversationsPage({ limit: 20, titleLike, ...options });
    return items;
  } catch {
    return [];
  }
}

export async function getConversationMessages(
  conversationId: number,
  opts?: { days?: number; limit?: number; beforeMessageId?: number },
): Promise<{
  messages: ChatMessage[];
  total_messages: number;
  has_more?: boolean;
  oldest_message_id?: number;
}> {
  const token = await getToken();
  await enforceAppEgressAllowed({
    cloudCredentialPresent: Boolean(token && token !== WEB_SESSION_AUTH_SENTINEL),
  });
  const params = new URLSearchParams();
  if (opts?.days) params.set('days', String(opts.days));
  if (opts?.limit) params.set('limit', String(opts.limit));
  if (opts?.beforeMessageId) params.set('before_message_id', String(opts.beforeMessageId));
  const query = params.toString();
  const qs = query ? `?${query}` : '';
  const res = await fetch(`${BASE_URL}/agent/conversations/${conversationId}${qs}`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: 'no-store',
  });
  if (!res.ok) {
    throw new Error(`getConversationMessages failed: ${res.status}`);
  }
  const data = await res.json();
  return {
    messages: data.messages || [],
    total_messages: data.total_messages ?? (data.messages?.length ?? 0),
    has_more: typeof data.has_more === 'boolean' ? data.has_more : undefined,
    oldest_message_id: typeof data.oldest_message_id === 'number'
      ? data.oldest_message_id
      : undefined,
  };
}

export async function getAgentTurnStatus(
  clientTurnId: string,
): Promise<AgentTurnStatus | null> {
  await enforceAppEgressAllowed();
  const token = await getToken();
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 1000);
  let res: Response;
  try {
    res = await fetch(
      `${BASE_URL}/agent/turns/${encodeURIComponent(clientTurnId)}/status`,
      {
        headers: { Authorization: `Bearer ${token}` },
        signal: controller.signal,
        cache: 'no-store',
      },
    );
  } finally {
    clearTimeout(timeout);
  }
  if (res.status === 404) return null;
  if (!res.ok) {
    throw new Error(`getAgentTurnStatus failed: ${res.status}`);
  }
  const data = await res.json();
  return {
    clientTurnId: String(data.client_turn_id || clientTurnId),
    ...(typeof data.run_id === 'string' ? { runId: data.run_id } : {}),
    status: String(data.status || 'unknown'),
    requestPersisted: data.request_persisted === true,
    responsePersisted: data.response_persisted === true,
    ...(typeof data.conversation_id === 'number'
      ? { conversationId: data.conversation_id }
      : {}),
    retryable: data.retryable === true,
    ...(typeof data.error_code === 'string'
      ? { errorCode: data.error_code }
      : {}),
  };
}

export async function deleteConversation(conversationId: number): Promise<boolean> {
  await enforceAppEgressAllowed();
  const token = await getToken();
  const res = await fetch(`${BASE_URL}/agent/conversations/${conversationId}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  });
  return res.ok;
}

export async function updateConversationTitle(
  conversationId: number,
  title: string,
): Promise<Conversation | null> {
  await enforceAppEgressAllowed();
  const token = await getToken();
  const res = await fetch(`${BASE_URL}/agent/conversations/${conversationId}`, {
    method: 'PATCH',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ title }),
  });
  if (!res.ok) return null;
  return res.json();
}
