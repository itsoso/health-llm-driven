/**
 * 共享 SSE (Server-Sent Events) 解析工具。
 *
 * 支持两种模式：
 * 1. 简单模式 (parseSimpleSSE): `data: {json}\n` — OpenClaw / Agent 使用
 * 2. 完整模式 (parseFullSSE):  `event: xxx\ndata: xxx\n\n` — Orchestrator 使用
 */

/** 简单 SSE 数据事件 */
export interface SSEDataEvent {
  event: string;
  data: any;
}

/**
 * 从 fetch Response 创建 async generator，逐条 yield SSE 数据事件。
 * 适用于简单 `data: {json}\n` 格式（OpenClaw / Agent stream）。
 *
 * 支持 AbortSignal 取消。
 */
export async function* parseSimpleSSE(
  response: Response,
  signal?: AbortSignal,
): AsyncGenerator<any> {
  const reader = response.body?.getReader();
  if (!reader) return;

  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      if (signal?.aborted) break;
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            yield JSON.parse(line.slice(6));
          } catch {
            // skip malformed JSON
          }
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

/** 完整 SSE 事件（含 event 类型） */
export interface FullSSEEvent {
  event: string;
  data: any;
}

/**
 * 从 fetch Response 解析完整 SSE 帧（event: + data:），通过回调分发。
 * 适用于 Orchestrator 的 `event: xxx\ndata: xxx\n\n` 格式。
 *
 * 支持 AbortSignal 取消。
 */
export async function parseFullSSE(
  response: Response,
  onEvent: (event: FullSSEEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const reader = response.body?.getReader();
  if (!reader) return;

  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  try {
    while (true) {
      if (signal?.aborted) break;
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      let idx;
      while ((idx = buffer.indexOf('\n\n')) !== -1) {
        const frame = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);

        // 解析帧
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
        if (!dataStr) continue;

        let parsed: any = dataStr;
        try {
          parsed = JSON.parse(dataStr);
        } catch {
          // plain string payload
        }

        onEvent({ event, data: parsed });
      }
    }
  } finally {
    reader.releaseLock();
  }
}
