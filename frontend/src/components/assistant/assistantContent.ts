/**
 * assistantContent — assistant 正文渲染前的纯文本预处理.
 *
 * 解决两个问题 (web 侧, 对齐 mac 的 displayText 处理):
 *   1. 剥离 [claim:xxx] / [工具调用:xxx] 等内部标记 —— 这些是 claim_id / tool 调用
 *      标签, 不该裸露给用户; 证据通过 sources_used / cards 单独展示.
 *   2. 从正文里抽出 LLM 直接吐出来的"计划 JSON"(FuelStrategist menu_share schema:
 *      {title, items[], totals?, reason?, shopping_list?}). 命中就渲染成卡片,
 *      不命中的裸 JSON 至少 pretty 成代码块, 不挤成一行.
 *
 * 纯字符串处理, 不碰 React / streaming / 后端逻辑.
 */

export interface MealPlanItem {
  name: string;
  qty?: string;
  kcal?: number;
  protein?: number;
  carbs?: number;
  fat?: number;
}

export interface MealPlanData {
  title: string;
  items: MealPlanItem[];
  totals?: { kcal?: number; protein?: number; carbs?: number; fat?: number; fiber?: number };
  reason?: string;
  shopping_list?: string[];
}

// [claim:c_xxx] / [claim: c_xxx] / claim:c_xxx (无方括号兜底), 连同前导空白一起去掉.
const CLAIM_MARKER_RE = /\s*\[?claim[:：]\s*[^\]\s][^\]]*\]?/gi;
// [工具调用: ...] / [工具调用：...] —— 整段去掉 (web 的内联 tool chip 已由 toolCallParse 处理,
// 这里只兜底裸露的中文标记残留).
const CN_TOOL_MARKER_RE = /\[工具调用[:：][\s\S]*?\]/g;

/**
 * 剥离内部标记. 处理后做一次行级 trim, 去掉因删除标记而残留的空行/行尾空格.
 */
export function stripInternalMarkers(content: string): string {
  if (!content) return content;
  let out = content.replace(CN_TOOL_MARKER_RE, '');
  out = out.replace(CLAIM_MARKER_RE, '');
  // 折叠因删除标记产生的行尾空白; 不动正常段落结构.
  out = out.replace(/[ \t]+$/gm, '');
  return out;
}

/** 给定一段可能含 ```json fence / 裸 JSON 的 content, 找出第一个能解析成对象的 JSON 文本块. */
interface JsonBlock {
  start: number;
  end: number; // exclusive
  json: string;
  parsed: unknown;
  /** true 表示这坨 JSON 来自 ```fence```; false 表示是裸吐在正文里. */
  fenced: boolean;
}

function findFirstJsonObject(content: string): JsonBlock | null {
  // 优先匹配 ```json ... ``` / ``` ... ``` 围栏块.
  const fenceRe = /```(?:json)?\s*\n?([\s\S]*?)```/g;
  let m: RegExpExecArray | null;
  while ((m = fenceRe.exec(content)) !== null) {
    const inner = m[1].trim();
    if (inner.startsWith('{')) {
      try {
        const parsed = JSON.parse(inner);
        if (parsed && typeof parsed === 'object') {
          return { start: m.index, end: m.index + m[0].length, json: inner, parsed, fenced: true };
        }
      } catch { /* 不是合法 JSON, 继续找 */ }
    }
  }
  // 没有围栏, 兜底扫第一个平衡的 {...} 块 (处理 LLM 裸吐 JSON).
  const brace = scanBalancedObject(content);
  if (brace) {
    try {
      const parsed = JSON.parse(brace.json);
      if (parsed && typeof parsed === 'object') {
        return { ...brace, parsed, fenced: false };
      }
    } catch { /* 非法 JSON, 放弃 */ }
  }
  return null;
}

/** 从第一个 '{' 起做花括号配平, 跳过字符串字面量里的括号. */
function scanBalancedObject(content: string): { start: number; end: number; json: string } | null {
  const start = content.indexOf('{');
  if (start < 0) return null;
  let depth = 0;
  let inStr = false;
  let escaped = false;
  for (let i = start; i < content.length; i++) {
    const ch = content[i];
    if (inStr) {
      if (escaped) escaped = false;
      else if (ch === '\\') escaped = true;
      else if (ch === '"') inStr = false;
      continue;
    }
    if (ch === '"') inStr = true;
    else if (ch === '{') depth++;
    else if (ch === '}') {
      depth--;
      if (depth === 0) {
        return { start, end: i + 1, json: content.slice(start, i + 1) };
      }
    }
  }
  return null;
}

/** 判断解析出来的对象是否是 menu_share 计划 schema. */
function isMealPlan(obj: unknown): obj is MealPlanData {
  if (!obj || typeof obj !== 'object') return false;
  const o = obj as Record<string, unknown>;
  const hasTitle = typeof o.title === 'string' && o.title.trim().length > 0;
  const hasItems =
    Array.isArray(o.items) &&
    o.items.length > 0 &&
    o.items.every(it => it && typeof it === 'object' && typeof (it as { name?: unknown }).name === 'string');
  // title + items 是必要条件; totals / shopping_list 增强信号但非必需.
  return hasTitle && hasItems;
}

export interface PreprocessedContent {
  /** 剥离标记 (并抽掉计划 JSON 块后) 的正文, 走 markdown 渲染. 可能为空. */
  text: string;
  /** 命中 menu_share schema 的计划数据, 渲染成 MealPlanCard. */
  mealPlan: MealPlanData | null;
}

/**
 * 预处理 assistant 正文:
 *   1. 剥离内部标记.
 *   2. 若正文里有一坨计划 JSON (menu_share schema) → 抽出来当 mealPlan, 从正文移除.
 *
 * 不命中计划 schema 的裸 JSON: 若是裸吐 (无围栏), 包成 ```json fence``` + pretty
 * (缩进 2 空格), 让 MarkdownRenderer 渲染成代码块, 而不是挤成一行难看的纯文本.
 * 已经在 ```fence``` 里的 JSON 本就走 code block, 不动.
 */
export function preprocessAssistantContent(content: string): PreprocessedContent {
  const stripped = stripInternalMarkers(content || '');
  if (!stripped.includes('{')) {
    return { text: stripped, mealPlan: null };
  }
  const block = findFirstJsonObject(stripped);
  if (!block) {
    return { text: stripped, mealPlan: null };
  }
  if (isMealPlan(block.parsed)) {
    const text = (stripped.slice(0, block.start) + stripped.slice(block.end)).trim();
    return { text, mealPlan: block.parsed };
  }
  // 无法识别的裸 JSON → pretty 后包进 code fence; 围栏 JSON 保持原样.
  if (!block.fenced) {
    const pretty = JSON.stringify(block.parsed, null, 2);
    const text =
      stripped.slice(0, block.start) +
      '\n```json\n' + pretty + '\n```\n' +
      stripped.slice(block.end);
    return { text: text.trim(), mealPlan: null };
  }
  return { text: stripped, mealPlan: null };
}
