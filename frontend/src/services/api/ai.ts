import api, { API_BASE_URL } from './client';
import { parseSimpleSSE } from '@/utils/sseParser';
import { AiConsentError, fetchWithAiSubject, isAiConsentRejection, requireAiConsent } from '@/services/aiConsent';

// GenUI 能力声明 (X-Reva-Client-Caps): 让后端知道本端能渲染哪些 reva-ui 组件。
// metric_table 渲染器 (MetricTableCard) 已随前端上线, 但 cap token 先暗着 —— eval
// 过闸后把下面这行翻成 true, 后端才会开始产出 metric_table 块。改这一个常量即可。
const REVA_UI_TABLE_CAP_ENABLED = true;
const BASE_CLIENT_CAPS = 'genui-v1, genui-components-v1';
const CLIENT_CAPS = REVA_UI_TABLE_CAP_ENABLED ? `${BASE_CLIENT_CAPS}, genui-table-v1` : BASE_CLIENT_CAPS;

interface ClientTimeContext {
  client_now_iso: string;
  timezone?: string;
  timezone_offset_minutes: number;
  locale?: string;
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

export interface ActivitySavedData {
  type: string;
  status: string;
  message: string;
}

export interface ChatMessage {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
  image_preview?: string;
  file_name?: string;
  /** 动态卡片类型 (vitals/sleep/weight/... ); 如存在则此消息渲染为卡片而非气泡 */
  card_type?: string;
  /** 卡片数据 payload (跟 card_type 匹配) */
  card_data?: any;
  /** 服务端签发的动态卡片动作；只允许经本地 capability 校验后执行。 */
  card_actions?: Array<Record<string, any>>;
  /** 2026-05-13 性能可观测性: assistant 消息完成后填. 显示在气泡 footer */
  elapsed_ms?: number;
  llm_ms?: number;
  llm_rounds?: number;
  llm_rounds_ms?: number[];
  model?: string;
  llm_usage?: LlmUsageProfile;
  perf?: AgentPerfProfile;
  /** 2026-05-14 #4 可解释性: AI 本次回答用了什么数据源, 中文标签数组 */
  sources_used?: string[];
  /** 本轮调用的 Skill / 工具名, 与 sources_used 独立. */
  tools_used?: string[];
  /** 服务端终态；错误/中断回合里的 tools_used 仅表示尝试调用。 */
  completion_status?: 'complete' | 'interrupted' | 'error' | 'unknown';
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

export interface AgentPerfRound {
  llm_gen_ms?: number | null;
  tool_exec_ms?: number | null;
  tools?: string[] | null;
}

export interface AgentPerfProfile {
  total_ms?: number | null;
  pre_llm_ms?: number | null;
  pre_llm_stages?: Record<string, number | null | undefined> | null;
  llm_ttft_ms?: number | null;
  llm_full_ms?: number | null;
  rounds?: AgentPerfRound[] | null;
  orchestrator_tool_ms?: number | null;
}

export interface ChatSendResponse {
  conversation_id: number;
  message_id: number;
  reply: string;
  diet_saved?: boolean;
  diet_data?: DietSavedData;
  activities_saved?: boolean;
  activities?: ActivitySavedData[];
  reminder?: ReminderData;
  workout_analysis?: {
    message_id: number;
    content: string;
    workout_data?: Record<string, unknown>;
  };
}

// ====== 女性健康 ======
export interface Conversation {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
  last_message?: string;
  mode?: string;
}

export interface ConversationPage {
  items: Conversation[];
  total: number;
  limit: number;
  offset: number;
}

export interface ConversationListOptions {
  /** Only conversations with at least one user turn, for default resume. */
  resumeOnly?: boolean;
}

export interface ConversationDetail {
  id: number;
  title: string;
  messages: ChatMessage[];
  mode?: string;
}

export interface DietSavedData {
  record_id: number;
  food_items: string;
  total_calories?: number;
  total_protein?: number;
  total_carbs?: number;
  total_fat?: number;
  meal_type: string;
  record_date: string;
}

export interface ReminderData {
  reminder_minutes: number;
  reminder_message: string;
  activity_name: string;
}

export const chatApi = {
  // 语音转文字（via speech.py，保留 /chat 前缀兼容前端）
  transcribe: (audioBase64: string, audioFormat: string = 'webm') =>
    api.post<{ text: string }>('/chat/transcribe', { audio_base64: audioBase64, audio_format: audioFormat }),
  // 语音指令快速执行
  voiceCommand: (text: string) =>
    api.post<{ matched: boolean; command_type?: string; message?: string; data?: any }>('/chat/voice-command', { text }),
};

// ===== 统一健康 Agent API =====
export const agentApi = {
  // 分页返回 {items,total,limit,offset};历史记录用 offset 做上一页/下一页翻页。
  // search 同时匹配标题与消息内容(后端 EXISTS 子查询)。
  getConversations: (
    limit: number = 30,
    offset: number = 0,
    search?: string,
    options: ConversationListOptions = {},
  ) => {
    const q = search?.trim() ? `&search=${encodeURIComponent(search.trim())}` : '';
    const resume = options.resumeOnly ? '&resume_only=true' : '';
    return api.get<ConversationPage>(`/agent/conversations?limit=${limit}&offset=${offset}${q}${resume}`);
  },

  getConversation: (conversationId: number) =>
    api.get<ConversationDetail & { total_messages?: number }>(`/agent/conversations/${conversationId}`),

  deleteConversation: (conversationId: number) =>
    api.delete<{ ok: boolean }>(`/agent/conversations/${conversationId}`),

  updateConversationTitle: (conversationId: number, title: string) =>
    api.patch<Conversation>(`/agent/conversations/${conversationId}`, { title }),

  streamMessage: async function* (
    message: string,
    conversationId?: number,
    imageBase64?: string,
    imageType?: string,
    fileBase64?: string,
    fileName?: string,
    extraContext?: string,
    expectedSubject?: string,
  ) {
    const aiHeaders = await requireAiConsent(expectedSubject);
    const body: Record<string, any> = {
      message,
      conversation_id: conversationId,
      client_time_context: buildClientTimeContext(),
      // Web 聊天恒为打字输入(键盘逐字敲)→ 声明 typed 通道,后端才走 symptom/rhinitis 免确认;
      // 漏传 → channel=None 走 fail-closed → web 每条症状/鼻炎消息都被二次追问(手机/Mac 正常)。
      channel: 'typed',
    };
    if (imageBase64) { body.image_base64 = imageBase64; body.image_type = imageType || 'jpeg'; }
    if (fileBase64) { body.file_base64 = fileBase64; body.file_name = fileName; }
    // opener quick-reply 上下文: 让后端 apply_opener_quick_reply_context 能把
    // "做到了/没做/调整" 绑定到具体 ActionCard, 而非当孤立文本。
    if (extraContext) { body.extra_context = extraContext; }

    const response = await fetchWithAiSubject(`${API_BASE_URL}/agent/stream`, {
      method: 'POST',
      headers: {
        ...aiHeaders,
        'Content-Type': 'application/json',
        'X-Reva-Client-Caps': CLIENT_CAPS,
      },
      credentials: 'include',
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      if (response.status === 403 && isAiConsentRejection(await response.clone().json())) throw new AiConsentError();
      throw new Error(`Agent stream request failed: ${response.status}`);
    }

    yield* parseSimpleSSE(response);
  },

  listTools: () => api.get('/agent/tools'),
};

// ===== 对话分享 API =====
export const sharedApi = {
  createShare: (
    conversationId: number,
    sourceType: string = 'health',
    messageIds?: number[],
  ) =>
    api.post<{ share_token: string; share_url: string }>('/shared/create', {
      conversation_id: conversationId,
      source_type: sourceType,
      ...(messageIds ? { message_ids: messageIds } : {}),
    }),
  createTextShare: (title: string, message: string) =>
    api.post<{ share_token: string; share_url: string }>('/shared/create-text', {
      title,
      message,
    }),
  revokeShare: (shareToken: string) =>
    api.delete(`/shared/${shareToken}`),
};
