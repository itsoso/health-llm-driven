import api, { API_BASE_URL } from './client';

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

export interface VocabularyListResponse {
  total: number;
  words: VocabularyWord[];
}

export interface VocabularyWord {
  id: number;
  word: string;
  phonetic_us?: string;
  phonetic_uk?: string;
  meanings?: string;
  example_sentences?: string;
  synonyms?: string;
  antonyms?: string;
  word_roots?: string;
  notes?: string;
  review_count: number;
  correct_count: number;
  mastery_level: number;
  last_reviewed_at?: string;
  next_review_date?: string;
  is_mastered: boolean;
  created_at?: string;
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

    const reader = response.body?.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (reader) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6));
            yield data;
          } catch {
            // skip malformed JSON
          }
        }
      }
    }
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

    const reader = response.body?.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (reader) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6));
            yield data;
          } catch {
            // skip malformed JSON
          }
        }
      }
    }
  },
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
  revokeShare: (shareToken: string) =>
    api.delete(`/shared/${shareToken}`),
};

// ===== 活动状态 API =====
export const vocabularyApi = {
  getWords: (page: number = 1, pageSize: number = 20, mastered?: boolean) => {
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (mastered !== undefined) params.append('mastered', String(mastered));
    return api.get<VocabularyListResponse>(`/vocabulary/words?${params}`);
  },
  getWord: (wordId: number) =>
    api.get<VocabularyWord>(`/vocabulary/words/${wordId}`),
  getReviewWords: (limit: number = 10) =>
    api.get<VocabularyListResponse>(`/vocabulary/review?limit=${limit}`),
  submitReview: (wordId: number, isCorrect: boolean) =>
    api.post<{ ok: boolean; mastery_level: number; next_review_date: string }>(
      '/vocabulary/review', { word_id: wordId, is_correct: isCorrect }
    ),
  deleteWord: (wordId: number) =>
    api.delete(`/vocabulary/words/${wordId}`),
};

// ── 资产防御与布局 (Security Life) ─────────────────────
