import api, { API_BASE_URL } from './client';
import { parseFullSSE } from '@/utils/sseParser';
import { AiConsentError, fetchWithAiSubject, isAiConsentRejection, requireAiConsent } from '@/services/aiConsent';

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
  const aiHeaders = await requireAiConsent();
  const res = await fetchWithAiSubject(`${API_BASE_URL}/orchestrator/chat/stream`, {
    method: 'POST',
    headers: {
      ...aiHeaders,
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
    credentials: 'include',
    body: JSON.stringify({ ...req, stream: true }),
    signal,
  });

  if (!res.ok) {
    if (res.status === 403 && isAiConsentRejection(await res.clone().json())) throw new AiConsentError();
    const text = await res.text().catch(() => '');
    throw new Error(`Orchestrator stream failed: ${res.status} ${text || ''}`);
  }

  if (!res.body) {
    throw new Error('Orchestrator stream: no body');
  }

  await parseFullSSE(res, ({ event, data }) => {
    switch (event) {
      case 'intent':
        handlers.onIntent?.(data);
        break;
      case 'specialist':
        handlers.onSpecialist?.(data);
        break;
      case 'chunk':
        handlers.onChunk?.(typeof data === 'string' ? data : JSON.stringify(data));
        break;
      case 'done':
        handlers.onDone?.(data);
        break;
      case 'error':
        handlers.onError?.(typeof data === 'string' ? data : data?.detail || 'unknown error');
        break;
    }
  }, signal);
};
