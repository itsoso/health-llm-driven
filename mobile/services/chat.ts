import { getToken } from './auth';

const BASE_URL = 'https://health.executor.life/api';

const SKILL_PATTERN =
  /记录|打卡|吃了|喝了|喝水|早餐|午餐|晚餐|加餐|补剂|用药|服药|洗鼻|血压|体重|量了/;

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface Conversation {
  id: number;
  title?: string;
  created_at: string;
}

function chooseEndpoint(message: string): string {
  if (SKILL_PATTERN.test(message)) {
    return '/openclaw/stream';
  }
  return '/agent/stream';
}

export async function* streamChat(
  message: string,
  conversationId?: number,
): AsyncGenerator<string, void, unknown> {
  const token = await getToken();
  const endpoint = chooseEndpoint(message);
  const body: Record<string, any> = { message };
  if (conversationId) {
    body.conversation_id = conversationId;
  }

  const response = await fetch(`${BASE_URL}${endpoint}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    throw new Error(`Chat request failed: ${response.status}`);
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error('No response body');

  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed || !trimmed.startsWith('data:')) continue;
      const payload = trimmed.slice(5).trim();
      if (payload === '[DONE]') return;

      try {
        const parsed = JSON.parse(payload);
        const text =
          parsed.choices?.[0]?.delta?.content ||
          parsed.content ||
          parsed.text ||
          parsed.delta ||
          '';
        if (text) yield text;
      } catch {
        // non-JSON SSE line, yield as-is if non-empty
        if (payload && payload !== '[DONE]') yield payload;
      }
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
