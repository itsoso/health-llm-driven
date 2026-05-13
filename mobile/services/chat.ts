import { getToken } from './auth';
import { BASE_URL } from './api';

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface Conversation {
  id: number;
  title?: string;
  created_at: string;
}

export interface StreamEvent {
  type: 'token' | 'tool' | 'done' | 'error';
  content?: string;
  conversationId?: number;
  messageId?: number;
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
): AsyncGenerator<StreamEvent, void, unknown> {
  const token = await getToken();
  const body: Record<string, any> = { message };
  if (conversationId) body.conversation_id = conversationId;
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

  xhr.timeout = 120000; // 2 min for agent responses
  xhr.send(JSON.stringify(body));

  // Parse SSE lines from accumulated chunks
  let buffer = '';

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
      if (payload === '[DONE]') return;

      try {
        const parsed = JSON.parse(payload);

        if (parsed.event === 'token') {
          const text = parsed.data?.content || '';
          if (text) yield { type: 'token', content: text };
        } else if (parsed.event === 'tool_call') {
          const tool = parsed.data?.tool || '';
          // 不把 "🔧 health_record (第1轮)" 这种技术文本注入消息气泡
          // toolName 仍传给前端, cards dispatcher / analytics 可用
          yield { type: 'tool', content: '', toolName: tool };
        } else if (parsed.event === 'tool_result') {
          const tool = parsed.data?.tool || '';
          const ok = parsed.data?.success;
          // 成功静默 (AI token 流会接着讲), 失败才给用户可见的简短提示
          yield {
            type: 'tool',
            content: ok ? '' : '⚠️ 操作未成功，请稍后重试\n\n',
            toolName: tool,
            toolSuccess: ok,
            // I Phase 2: health_record 时后端附 record_type + record_data, 前端 sniff 录入摘要
            recordType: parsed.data?.record_type,
            recordData: parsed.data?.record_data,
          };
        } else if (parsed.event === 'done') {
          yield {
            type: 'done',
            conversationId: parsed.data?.conversation_id,
            messageId: parsed.data?.message_id,
            elapsedMs: parsed.data?.elapsed_ms,
            llmMs: parsed.data?.llm_ms,
            llmRounds: parsed.data?.llm_rounds,
            model: parsed.data?.model,
          };
        } else if (parsed.event === 'error') {
          yield { type: 'error', content: parsed.data?.message || '请求失败' };
        }
      } catch {
        // non-JSON line, skip
      }
    }

    if (done && chunks.length === 0) break;
  }

  // Process any remaining buffer
  if (buffer.trim()) {
    const trimmed = buffer.trim();
    if (trimmed.startsWith('data:')) {
      const payload = trimmed.slice(5).trim();
      try {
        const parsed = JSON.parse(payload);
        if (parsed.event === 'token' && parsed.data?.content) {
          yield { type: 'token', content: parsed.data.content };
        }
      } catch { /* skip */ }
    }
  }
}

export async function getConversations(titleLike?: string): Promise<Conversation[]> {
  const token = await getToken();
  const params = new URLSearchParams({ limit: '20' });
  if (titleLike) params.set('title_like', titleLike);
  const res = await fetch(`${BASE_URL}/openclaw/conversations?${params}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) return [];
  return res.json();
}

export async function getConversationMessages(
  conversationId: number,
  opts?: { days?: number },
): Promise<{ messages: ChatMessage[]; total_messages: number }> {
  const token = await getToken();
  const qs = opts?.days ? `?days=${opts.days}` : '';
  const res = await fetch(`${BASE_URL}/openclaw/conversations/${conversationId}${qs}`, {
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
  const res = await fetch(`${BASE_URL}/openclaw/conversations/${conversationId}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  });
  return res.ok;
}
