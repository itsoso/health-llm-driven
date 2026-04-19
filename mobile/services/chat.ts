import { getToken } from './auth';

const BASE_URL = 'https://health.executor.life/api';

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
}

/**
 * Stream chat using XMLHttpRequest (React Native doesn't support ReadableStream).
 * Yields StreamEvent objects instead of raw strings.
 */
export async function* streamChat(
  message: string,
  conversationId?: number,
  imageBase64?: string,
  imageType?: string,
): AsyncGenerator<StreamEvent, void, unknown> {
  const token = await getToken();
  const body: Record<string, any> = { message };
  if (conversationId) body.conversation_id = conversationId;
  if (imageBase64) { body.image_base64 = imageBase64; body.image_type = imageType || 'jpeg'; }

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
          const round = parsed.data?.round || '';
          yield { type: 'tool', content: `🔧 ${tool} (第${round}轮)\n`, toolName: tool };
        } else if (parsed.event === 'tool_result') {
          const tool = parsed.data?.tool || '';
          const ok = parsed.data?.success;
          yield { type: 'tool', content: `${ok ? '✅' : '❌'} ${tool} ${ok ? '完成' : '失败'}\n\n`, toolName: tool, toolSuccess: ok };
        } else if (parsed.event === 'done') {
          yield { type: 'done', conversationId: parsed.data?.conversation_id, messageId: parsed.data?.message_id };
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

export async function getConversations(): Promise<Conversation[]> {
  const token = await getToken();
  const res = await fetch(`${BASE_URL}/openclaw/conversations?limit=20`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) return [];
  return res.json();
}

export async function getConversationMessages(conversationId: number): Promise<ChatMessage[]> {
  const token = await getToken();
  const res = await fetch(`${BASE_URL}/openclaw/conversations/${conversationId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) return [];
  const data = await res.json();
  return data.messages || [];
}
