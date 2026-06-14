/**
 * modelName — 把后端模型 id 映射成消费级友好名.
 *
 * 后端给的是带前缀和补丁版本号的内部 id, 例如:
 *   commercial/Claude-Opus-4.7  → Claude Opus
 *   openclaw:main               → 健康助理
 *   tokenplan/qwen-max          → Qwen Max
 * 消费者只需要一个干净的家族名: 去掉 provider 前缀 / 补丁版本号 / 连字符.
 *
 * 纯字符串处理.
 */

// 已知家族 → 干净展示名 (大版本号去掉, 只留家族). key 为小写子串匹配.
const KNOWN: Array<[RegExp, string]> = [
  [/claude.*opus/i, 'Claude Opus'],
  [/claude.*sonnet/i, 'Claude Sonnet'],
  [/claude.*haiku/i, 'Claude Haiku'],
  [/gpt-?5/i, 'GPT-5'],
  [/gpt-?4/i, 'GPT-4'],
  [/gemini.*pro/i, 'Gemini Pro'],
  [/gemini/i, 'Gemini'],
  [/deepseek/i, 'DeepSeek'],
  [/qwen/i, 'Qwen'],
  [/glm/i, 'GLM'],
  [/minimax/i, 'MiniMax'],
  [/moonshot|kimi/i, 'Kimi'],
];

/**
 * 后端 model id → 友好家族名.
 * 命中已知家族返回干净名; 否则去掉 provider 前缀 + 补丁版本号做个体面兜底.
 */
export function prettyModelName(raw?: string | null): string | null {
  if (!raw || !raw.trim()) return null;
  for (const [re, label] of KNOWN) {
    if (re.test(raw)) return label;
  }
  // 兜底: 去掉 "provider/" 或 "provider:" 前缀
  let s = raw.replace(/^[^/:]+[/:]/, '');
  // 去掉结尾的补丁版本号 "-4.7" / " 4.7" / "_v2"
  s = s.replace(/[-_\s]v?\d+(\.\d+)*$/i, '');
  // 连字符 / 下划线转空格, 收尾空白
  s = s.replace(/[-_]+/g, ' ').trim();
  return s || raw;
}
