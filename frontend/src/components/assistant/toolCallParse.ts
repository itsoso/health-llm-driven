/**
 * toolCallParse — 把模型当成 markdown 文本吐出来的工具调用从正文里切出来.
 *
 * 模型有时会把工具调用写成裸文本, 例如:
 *   [tool_call: health_query(type=lab_results, days=7)]
 *   [工具调用: health_analysis(...)]
 * 这些不是给人看的, 直接渲染成 markdown 会很丑. 这里把 content 切成
 * 「文本段」和「工具调用段」, 文本段照常走 MarkdownRenderer, 工具调用段
 * 渲染成内联 chip (见 ToolCallChip.tsx).
 *
 * 纯字符串处理, 不碰 React / streaming / 后端逻辑.
 */

export interface ToolCallSegment {
  kind: 'tool_call';
  /** 工具原名, 如 health_query; 解析失败时为空串 */
  name: string;
}

export interface TextSegment {
  kind: 'text';
  text: string;
}

export type ChatSegment = TextSegment | ToolCallSegment;

// 匹配 [tool_call: NAME(...)] / [工具调用: NAME(...)] / [tool: NAME(...)]
// - 标签部分大小写不敏感, 允许 tool_call / toolcall / tool call / 工具调用 / 调用工具
// - NAME 取括号前的标识符 (字母数字下划线连字符)
// - 参数部分 (...) 可有可无, 内容整段忽略 (不展示 args/JSON)
const TOOL_CALL_RE =
  /\[(?:tool[_\s]?call|tool|工具调用|调用工具)\s*[:：]\s*([A-Za-z0-9_-]+)\s*(?:\([\s\S]*?\))?\s*\]/gi;

/**
 * 把一段 assistant content 切成有序的文本 / 工具调用段.
 * - 不会丢失任何非工具调用的文本 (包括空白).
 * - 连续的工具调用之间若只有空白, 也会被识别为相邻段 (由渲染层决定是否合并成一行 chips).
 */
export function parseToolCalls(content: string): ChatSegment[] {
  if (!content) return [];
  const segments: ChatSegment[] = [];
  let lastIndex = 0;
  TOOL_CALL_RE.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = TOOL_CALL_RE.exec(content)) !== null) {
    if (match.index > lastIndex) {
      segments.push({ kind: 'text', text: content.slice(lastIndex, match.index) });
    }
    segments.push({ kind: 'tool_call', name: (match[1] || '').trim() });
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < content.length) {
    segments.push({ kind: 'text', text: content.slice(lastIndex) });
  }
  return segments;
}

/** content 里是否含工具调用文本 — 便宜的预检, 没有就走老路径. */
export function hasToolCall(content: string): boolean {
  if (!content) return false;
  TOOL_CALL_RE.lastIndex = 0;
  return TOOL_CALL_RE.test(content);
}

// 工具原名 → 人话动作词. 覆盖常见 health-* skill; 未知兜底见 toolCallLabel().
const TOOL_LABELS: Record<string, string> = {
  health_query: '查询健康数据',
  health_record: '记录健康数据',
  health_analysis: '分析健康数据',
  health_manage: '管理健康计划',
  health_data_summary: '汇总健康数据',
  health_query_data: '查询健康数据',
  knowledge_search: '检索知识库',
  knowledge_query: '检索知识库',
  web_search: '联网搜索',
  search: '搜索',
};

/** 工具原名 → 展示标签. 未知名兜底为「调用工具」. */
export function toolCallLabel(name: string): string {
  if (!name) return '调用工具';
  const key = name.toLowerCase();
  if (TOOL_LABELS[key]) return TOOL_LABELS[key];
  // 前缀兜底: 任意 health_* / knowledge_* / *_search 给个合理动作词
  if (key.startsWith('health_')) return '调用健康工具';
  if (key.startsWith('knowledge_')) return '检索知识库';
  if (key.endsWith('_search') || key.includes('search')) return '搜索';
  return '调用工具';
}
