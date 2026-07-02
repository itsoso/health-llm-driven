import api, { API_BASE_URL } from './client';
import { parseSimpleSSE } from '@/utils/sseParser';

export interface ActivitySavedData {
  type: string;
  status: string;
  message: string;
}

export interface AssistantOpenClawBindingStatus {
  configured: boolean;
  enabled: boolean;
  display_name: string;
  gateway_url: string | null;
  gateway_token_last4: string | null;
  status: 'unconfigured' | 'active' | 'invalid' | 'disabled';
  last_tested_at: string | null;
  last_error: string | null;
}

export interface AssistantOpenClawBindingTestResult {
  reachable: boolean;
  authenticated: boolean;
  status: 'active' | 'invalid';
  latency_ms: number | null;
  message: string;
}

export interface AssistantOpenClawBindingUpdateRequest {
  display_name: string;
  gateway_url: string;
  gateway_token?: string;
  enabled: boolean;
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
}

export interface LlmUsageCall {
  provider?: string;
  model?: string;
  caller?: string;
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
  cost_usd?: number;
  latency_ms?: number | null;
  success?: boolean;
  error_type?: string | null;
  error_code?: string | null;
  error_message?: string | null;
}

export interface LlmUsageProfile {
  calls?: number;
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
  cost_usd?: number;
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

// OpenClaw Channel API
export const openclawApi = {
  getConversations: (limit: number = 20) =>
    api.get<Conversation[]>(`/openclaw/conversations?limit=${limit}`),

  getConversation: (conversationId: number) =>
    api.get<ConversationDetail>(`/openclaw/conversations/${conversationId}`),

  deleteConversation: (conversationId: number) =>
    api.delete(`/openclaw/conversations/${conversationId}`),

  updateConversationTitle: (conversationId: number, title: string) =>
    api.patch<Conversation>(`/openclaw/conversations/${conversationId}`, { title }),

  streamMessage: async function* (message: string, conversationId?: number, imageBase64?: string, imageType?: string, fileBase64?: string, fileName?: string) {
    const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;
    const payload: Record<string, any> = {
      message,
      conversation_id: conversationId,
    };
    if (imageBase64) {
      payload.image_base64 = imageBase64;
      payload.image_type = imageType || 'jpeg';
    }
    if (fileBase64 && fileName) {
      payload.file_base64 = fileBase64;
      payload.file_name = fileName;
    }
    const response = await fetch(`${API_BASE_URL}/openclaw/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      throw new Error(`OpenClaw stream request failed: ${response.status}`);
    }

    yield* parseSimpleSSE(response);
  },
};

export const assistantOpenclawBindingApi = {
  getMe: () =>
    api.get<AssistantOpenClawBindingStatus>('/assistant-openclaw/binding/me'),

  update: (data: AssistantOpenClawBindingUpdateRequest) =>
    api.put<{
      ok: boolean;
      configured: boolean;
      enabled: boolean;
      status: string;
      gateway_token_last4: string;
      message: string;
    }>('/assistant-openclaw/binding/me', data),

  test: (data?: { gateway_url?: string; gateway_token?: string }) =>
    api.post<AssistantOpenClawBindingTestResult>('/assistant-openclaw/binding/me/test', data || {}),

  remove: () =>
    api.delete<{ ok: boolean }>('/assistant-openclaw/binding/me'),
};

export const assistantOpenclawApi = {
  getConversations: (limit: number = 20) =>
    api.get<Conversation[]>(`/assistant-openclaw/conversations?limit=${limit}`),

  getConversation: (conversationId: number) =>
    api.get<ConversationDetail>(`/assistant-openclaw/conversations/${conversationId}`),

  deleteConversation: (conversationId: number) =>
    api.delete(`/assistant-openclaw/conversations/${conversationId}`),

  streamMessage: async function* (message: string, conversationId?: number) {
    const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;
    const response = await fetch(`${API_BASE_URL}/assistant-openclaw/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        message,
        conversation_id: conversationId,
      }),
    });

    if (!response.ok) {
      throw new Error(`Assistant OpenClaw stream request failed: ${response.status}`);
    }

    yield* parseSimpleSSE(response);
  },
};

// ===== 统一健康 Agent API =====
export const agentApi = {
  // 分页返回 {items,total,limit,offset};历史记录用 offset 做上一页/下一页翻页。
  getConversations: (limit: number = 30, offset: number = 0) =>
    api.get<ConversationPage>(`/agent/conversations?limit=${limit}&offset=${offset}`),

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
  ) {
    const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;
    const body: Record<string, any> = { message, conversation_id: conversationId };
    if (imageBase64) { body.image_base64 = imageBase64; body.image_type = imageType || 'jpeg'; }
    if (fileBase64) { body.file_base64 = fileBase64; body.file_name = fileName; }

    const response = await fetch(`${API_BASE_URL}/agent/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
        'X-Reva-Client-Caps': 'genui-v1, genui-components-v1',
      },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      throw new Error(`Agent stream request failed: ${response.status}`);
    }

    yield* parseSimpleSSE(response);
  },

  listTools: () => api.get('/agent/tools'),
};

// ===== 对话分享 API =====
export const openclawSkillsApi = {
  listInstalled: () =>
    api.get<Array<{
      name: string;
      description: string;
      version: string;
      enabled: boolean;
      has_env: boolean;
      env_keys: string[];
    }>>('/v1/openclaw/skills'),
  install: (name: string, skill_md_content: string, enabled: boolean = true, env?: Record<string, string>, api_key?: string) =>
    api.post<{ name: string; status: string; enabled: boolean }>('/v1/openclaw/skills', {
      name, skill_md_content, enabled, env, api_key,
    }),
  remove: (name: string) =>
    api.delete<{ ok: boolean; message: string }>(`/v1/openclaw/skills/${name}`),
  toggle: (name: string, enabled: boolean) =>
    api.put<{ ok: boolean; name: string; enabled: boolean }>(`/v1/openclaw/skills/${name}/toggle`, { enabled }),
  gatewayStatus: () =>
    api.get<{ status: string; uptime: string }>('/v1/openclaw/skills/gateway/status'),
  restartGateway: () =>
    api.post<{ ok: boolean; message: string }>('/v1/openclaw/skills/gateway/restart'),
};

// ===== 交互反馈 API（OpenClaw Native 自优化） =====
export const sharedApi = {
  createShare: (conversationId: number, sourceType: string = 'health') =>
    api.post<{ share_token: string; share_url: string }>('/shared/create', {
      conversation_id: conversationId,
      source_type: sourceType,
    }),
  createTextShare: (title: string, message: string) =>
    api.post<{ share_token: string; share_url: string }>('/shared/create-text', {
      title,
      message,
    }),
  revokeShare: (shareToken: string) =>
    api.delete(`/shared/${shareToken}`),
};
