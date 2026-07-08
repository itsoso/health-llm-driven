const QUOTA_ERROR_MESSAGE = '当前模型额度已用尽。请切换模型或稍后重试；本轮没有生成可靠健康建议。';
const RATE_LIMIT_ERROR_MESSAGE = '当前模型服务请求过于频繁。请稍后重试；本轮没有生成可靠健康建议。';
const GENERIC_MODEL_ERROR_MESSAGE = '模型服务暂时不可用。请稍后重试；本轮没有生成可靠健康建议。';

function looksLikeProviderError(raw: string): boolean {
  const text = raw.toLowerCase();
  return (
    text.includes('agent 执行遇到问题') ||
    text.includes('error code:') ||
    text.includes('insufficient_quota') ||
    text.includes('token-plan quota') ||
    text.includes('quota has been exhausted') ||
    text.includes("{'error'") ||
    text.includes('"error"')
  );
}

export function sanitizeChatErrorMessage(raw: unknown, fallback = '请求出错，请稍后再试'): string {
  const value = typeof raw === 'string' ? raw.trim() : String(raw || '').trim();
  if (!value) return fallback;
  if (!looksLikeProviderError(value)) return value;

  const text = value.toLowerCase();
  if (
    text.includes('insufficient_quota') ||
    text.includes('quota has been exhausted') ||
    text.includes('token-plan quota')
  ) {
    return QUOTA_ERROR_MESSAGE;
  }
  if (
    text.includes('error code: 429') ||
    text.includes('too many requests') ||
    text.includes('rate limit') ||
    text.includes('限流')
  ) {
    return RATE_LIMIT_ERROR_MESSAGE;
  }
  return GENERIC_MODEL_ERROR_MESSAGE;
}

export function sanitizeChatStreamToken(raw: unknown): string {
  const value = typeof raw === 'string' ? raw : String(raw || '');
  if (!value) return '';

  const trimmed = value.trim();
  if (!trimmed || !looksLikeProviderError(trimmed)) return value;

  return sanitizeChatErrorMessage(trimmed, '');
}
