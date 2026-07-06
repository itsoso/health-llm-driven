/**
 * 逐条消息显式模型选择 → extra_context 注入(2026-07-06)。
 *
 * 后端契约:POST /agent/stream 的 extra_context 是 JSON 字符串,带
 * `model_id` 时该回合按用户显式选择路由 —— 快路由/工具门控绝不覆盖
 * (backend/app/services/agent_executor.py `_extract_model_id_from_extra_context`)。
 *
 * 收口原则:mobile 有多个 extraContext 生产点(Siri 深链 context、opener
 * 回复 context、ChatInputBar 手动 JSON),model_id 只在 useChatEngine.sendMessage
 * 这一个点合并进去,绝不在各生产点各自拼 JSON。
 */
export function mergeModelIntoExtraContext(
  extraContext: string | undefined,
  modelId: string | null | undefined,
): string | undefined {
  const id = (modelId || '').trim();
  if (!id) return extraContext;
  const raw = (extraContext || '').trim();
  if (!raw) return JSON.stringify({ model_id: id });
  try {
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      // 非对象 JSON(数组/标量):不是我们认识的 extra_context 形态,
      // 保持原样透传 —— 宁可少注入,不破坏既有消费方。
      return extraContext;
    }
    if (typeof parsed.model_id === 'string' && parsed.model_id.trim()) {
      // 调用方已显式带 model_id(更贴近本次意图),不覆盖。
      return extraContext;
    }
    return JSON.stringify({ ...parsed, model_id: id });
  } catch {
    // 非 JSON 字符串:包一层会破坏后端对该串的既有解析,保持原样。
    return extraContext;
  }
}
