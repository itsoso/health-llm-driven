import api, { API_BASE_URL } from './client';

export interface OrchestratorRequest {
  query: string;
  specialists?: string[];
  stream?: boolean;
}

export interface OrchestratorIntent {
  raw_query: string;
  categories: string[];
  keywords: string[];
}

export interface OrchestratorFinding {
  specialist_name: string;
  category: string;
  summary: string;
  findings: Array<Record<string, any>>;
  raw: Record<string, any>;
  ms_elapsed: number;
}

export interface OrchestratorResponse {
  query: string;
  intent: OrchestratorIntent;
  findings: OrchestratorFinding[];
  synthesis: string;
  used_specialists: string[];
  twin_build_ms: number;
  total_ms: number;
  generated_at: string;
}

/** 非流式综合分析。 */
export const runOrchestrator = async (
  req: OrchestratorRequest
): Promise<OrchestratorResponse> => {
  const res = await api.post('/orchestrator/chat', req);
  return res.data;
};

export interface OrchestratorStreamHandlers {
  onIntent?: (data: {
    categories: string[];
    keywords: string[];
    used_specialists: string[];
    twin_build_ms: number;
  }) => void;
  onSpecialist?: (finding: OrchestratorFinding) => void;
  onChunk?: (text: string) => void;
  onDone?: (data: { total_ms: number }) => void;
  onError?: (err: string) => void;
}

/**
 * 流式调用 Orchestrator。解析 SSE 事件并回调对应处理器。
 *
 * 注意：因为 fetch 本身不支持 EventSource 的 POST，
 * 我们用 fetch + ReadableStream 手动 parse SSE。
 */
export const streamOrchestrator = async (
  req: OrchestratorRequest,
  handlers: OrchestratorStreamHandlers,
  signal?: AbortSignal
): Promise<void> => {
  const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;

  const res = await fetch(`${API_BASE_URL}/orchestrator/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ ...req, stream: true }),
    signal,
  });

  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`Orchestrator stream failed: ${res.status} ${text || ''}`);
  }

  if (!res.body) {
    throw new Error('Orchestrator stream: no body');
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE frames separated by double newline
    let idx;
    while ((idx = buffer.indexOf('\n\n')) !== -1) {
      const frame = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      parseAndDispatch(frame, handlers);
    }
  }
};

function parseAndDispatch(frame: string, handlers: OrchestratorStreamHandlers) {
  const lines = frame.split('\n');
  let event = 'message';
  const dataLines: string[] = [];
  for (const line of lines) {
    if (line.startsWith('event:')) {
      event = line.slice(6).trim();
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trim());
    }
  }
  const dataStr = dataLines.join('\n');
  if (!dataStr) return;

  let parsed: any = dataStr;
  try {
    parsed = JSON.parse(dataStr);
  } catch {
    // plain string payload (e.g. chunk of prose)
  }

  switch (event) {
    case 'intent':
      handlers.onIntent?.(parsed);
      break;
    case 'specialist':
      handlers.onSpecialist?.(parsed);
      break;
    case 'chunk':
      handlers.onChunk?.(typeof parsed === 'string' ? parsed : JSON.stringify(parsed));
      break;
    case 'done':
      handlers.onDone?.(parsed);
      break;
    case 'error':
      handlers.onError?.(typeof parsed === 'string' ? parsed : parsed?.detail || 'unknown error');
      break;
  }
}
