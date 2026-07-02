import { getToken } from './auth';
import { BASE_URL } from './api';
import { sanitizeChatErrorMessage } from '../utils/chatErrorMessage';

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
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

export interface StreamEvent {
  type: 'start' | 'token' | 'tool' | 'card' | 'done' | 'error';
  content?: string;
  /** 面向用户的安全思考/进度摘要,不包含模型原始推理链或工具参数。 */
  thought?: string;
  conversationId?: number;
  messageId?: number;
  anchor?: string;
  card?: StreamCardDescriptor;
  toolName?: string;
  toolSuccess?: boolean;
  // I Phase 2: health_record 时附 record_type + record_data 让前端能 sniff 录入摘要
  recordType?: string;
  recordData?: Record<string, any>;
  // 2026-05-13: 每轮对话耗时 + 模型名 (性能可观测)
  elapsedMs?: number;
  llmMs?: number;
  llmRounds?: number;
  model?: string;
  // 2026-05-14 #4: 可解释性 — AI 用了什么数据
  sourcesUsed?: string[];
  // 2026-06-12: 本轮调用的 Skill / 工具名 (后端 done.tools_used; 去重保序, 空 [])
  toolsUsed?: string[];
  completionStatus?: 'complete' | 'interrupted' | 'error' | 'unknown';
  // SSE done 事件里的动态卡片，由 useChatEngine 交给 card registry 渲染
  cards?: StreamCardDescriptor[];
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
): AsyncGenerator<StreamEvent, void, unknown> {
  const token = await getToken();
  // channel = 传输层输入通道声明(非 LLM 参数):打字免症状二次确认;
  // 语音(转写有失真风险)fail-closed 保留确认 —— 语音入口必须显式传 'voice'。
  const body: Record<string, any> = { message, channel };
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
  xhr.setRequestHeader('X-Reva-Client-Caps', 'genui-v1, genui-components-v1');
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
    const newText = xhr.responseText.slice(processed);
    processed = xhr.responseText.length;
    if (newText) {
      chunks.push(newText);
      resolve?.();
    }
  };

  xhr.onload = () => {
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

      if (parsed.event === 'agent_start') {
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
        // 不把 "🔧 health_record (第1轮)" 这种技术文本注入消息气泡
        // toolName 仍传给前端, cards dispatcher / analytics 可用
        return {
          type: 'tool',
          content: '',
          toolName: tool,
          thought: `读取${toolThoughtLabel(tool)}`,
        };
      } else if (parsed.event === 'tool_result') {
        const tool = parsed.data?.tool || '';
        const ok = parsed.data?.success;
        const label = toolThoughtLabel(tool);
        // 成功静默 (AI token 流会接着讲), 失败才给用户可见的简短提示
        return {
          type: 'tool',
          content: ok ? '' : '⚠️ 操作未成功，请稍后重试\n\n',
          toolName: tool,
          toolSuccess: ok,
          thought: ok ? `已取得${label}` : `${label}暂时不可用`,
          // I Phase 2: health_record 时后端附 record_type + record_data, 前端 sniff 录入摘要
          recordType: parsed.data?.record_type,
          recordData: parsed.data?.record_data,
        };
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
        return {
          type: 'done',
          conversationId: parsed.data?.conversation_id,
          messageId: parsed.data?.message_id,
          elapsedMs: parsed.data?.elapsed_ms,
          llmMs: parsed.data?.llm_ms,
          llmRounds: parsed.data?.llm_rounds,
          model: parsed.data?.model,
          sourcesUsed: Array.isArray(parsed.data?.sources_used) ? parsed.data.sources_used : undefined,
          toolsUsed: Array.isArray(parsed.data?.tools_used) ? parsed.data.tools_used : undefined,
          completionStatus: parsed.data?.completion_status,
          cards: Array.isArray(parsed.data?.cards) ? parsed.data.cards : undefined,
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

export async function getConversations(titleLike?: string): Promise<Conversation[]> {
  const token = await getToken();
  const params = new URLSearchParams({ limit: '20' });
  if (titleLike) params.set('title_like', titleLike);
  // /agent/conversations 返回分页包装 { items, total, limit, offset } (web 同款),
  // 不是裸数组 — 必须取 .items, 否则历史列表渲染为空/错位。
  const res = await fetch(`${BASE_URL}/agent/conversations?${params}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) return [];
  const data = await res.json();
  return data.items ?? [];
}

export async function getConversationMessages(
  conversationId: number,
  opts?: { days?: number },
): Promise<{ messages: ChatMessage[]; total_messages: number }> {
  const token = await getToken();
  const qs = opts?.days ? `?days=${opts.days}` : '';
  const res = await fetch(`${BASE_URL}/agent/conversations/${conversationId}${qs}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) return { messages: [], total_messages: 0 };
  const data = await res.json();
  return {
    messages: data.messages || [],
    total_messages: data.total_messages ?? (data.messages?.length ?? 0),
  };
}

export async function deleteConversation(conversationId: number): Promise<boolean> {
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
