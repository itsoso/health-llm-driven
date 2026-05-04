/**
 * Attribution extractor — parse AI 回答里的"显式归因 marker", 还原成结构化数据
 * 给 ChatBubble 底部 chip 行渲染.
 *
 * P4 (2026-05-04): orchestrator system prompt 强制 LLM 在用了用户差异化数据时
 * 用括号标注来源 — 例如:
 *   "建议补叶酸 800mcg (基于你的 MTHFR C677T 杂合), 不要超过 1000."
 * 我们把这些 marker 提取出来变成底部 chip "📌 用了你的: MTHFR · ..."
 * 让用户**直接看到** AI 在用基因/化验/用药/历史, 而不是套通用模板.
 *
 * 设计:
 * - 纯函数, 单测好覆盖
 * - 5 类 marker (基因/化验/用药/历史/趋势), 每类一个 source 字段, 颜色不同
 * - 同源去重 (同一基因或药 marker 在多处出现只算一次)
 * - 无归因 → 空数组, ChatBubble 不渲染 chip 行
 */

export type AttributionSource = 'genetic' | 'lab' | 'medication' | 'history' | 'trend';

export interface AttributionItem {
  source: AttributionSource;
  /** 短标签, 用于 chip 文字 — "MTHFR" / "6月LDL" / "异丙托溴铵" */
  label: string;
  /** 完整 marker 文本 (含括号) — "(基于你的 MTHFR C677T 杂合)" */
  raw: string;
}

// 各 source 的正则. 严格匹配 system prompt 约定的 5 种格式.
// 内括号支持中英文括号 (Apple 输入法常出全角).
const PATTERNS: Array<{ source: AttributionSource; re: RegExp; labelExtract: (m: string) => string }> = [
  {
    // 基因: "基于你的 MTHFR C677T 杂合"
    source: 'genetic',
    re: /[（(]基于你的\s*([^()）]+?)[）)]/g,
    labelExtract: (m) => {
      // 取首个 token 作 label (基因名), 截断长 description
      const first = m.trim().split(/\s+/)[0] || m.trim();
      return first.slice(0, 16);
    },
  },
  {
    // 化验: "参照你 6 月 LDL 4.1" / "参照你近期 HbA1c 5.8"
    // NOTE: 必须排除 "参照你近 X" (那个走 trend pattern), 但保留 "参照你近期".
    source: 'lab',
    re: /[（(]参照你(?!近\s*\d)\s*([^()）]+?)[）)]/g,
    labelExtract: (m) => m.trim().replace(/\s+/g, '').slice(0, 18),
  },
  {
    // 用药: "因你在服异丙托溴铵" / "因你在服 GLP-1"
    source: 'medication',
    re: /[（(]因你在服\s*([^()）]+?)[）)]/g,
    labelExtract: (m) => m.trim().slice(0, 16),
  },
  {
    // 历史: "基于你之前提到的鼻塞" / "基于你 6 月反馈的失眠"
    source: 'history',
    re: /[（(]基于你之前(?:提到|提及|反馈|说过)的?\s*([^()）]+?)[）)]/g,
    labelExtract: (m) => m.trim().slice(0, 18),
  },
  {
    // 历史 (变体): "基于你 6 月反馈的失眠"
    source: 'history',
    re: /[（(]基于你\s*\d+\s*月反馈的?\s*([^()）]+?)[）)]/g,
    labelExtract: (m) => m.trim().slice(0, 18),
  },
  {
    // 趋势: "参照你近 90 天 HRV 下降趋势"
    source: 'trend',
    re: /[（(]参照你近\s*([^()）]+?)[）)]/g,
    labelExtract: (m) => m.trim().replace(/\s+/g, '').slice(0, 20),
  },
];

/**
 * 从 AI 回答 text 里提取 attribution markers. 同源 + 同 label 去重.
 * 返回顺序按文本里出现顺序.
 */
export function extractAttributions(text: string): AttributionItem[] {
  if (!text) return [];

  const found: AttributionItem[] = [];
  const seen = new Set<string>();

  for (const { source, re, labelExtract } of PATTERNS) {
    // re 是 /g, 重置 lastIndex (有时 reuse 会有问题)
    re.lastIndex = 0;
    let m: RegExpExecArray | null;
    while ((m = re.exec(text)) !== null) {
      const inner = (m[1] || '').trim();
      if (!inner) continue;
      const label = labelExtract(inner);
      const key = `${source}:${label}`;
      if (seen.has(key)) continue;
      seen.add(key);
      found.push({ source, label, raw: m[0] });
    }
  }

  return found;
}
