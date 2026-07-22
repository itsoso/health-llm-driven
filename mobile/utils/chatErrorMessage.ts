const QUOTA_ERROR_MESSAGE = '当前模型额度已用尽。请切换模型或稍后重试；本轮没有生成可靠健康建议。';
const MONTHLY_USER_LIMIT_MESSAGE = '本月 AI 使用额度已达上限，将于下月 1 日恢复。你已发送的内容已保留；如需立即继续，请联系管理员调整额度。';
const DAILY_USER_LIMIT_MESSAGE = '今日 AI 使用额度已达上限，将于明日恢复。你已发送的内容已保留；如需立即继续，请联系管理员调整额度。';
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
    text.includes('user_monthly_token_limit') ||
    text.includes('user_monthly_credit_limit') ||
    text.includes('user_daily_call_limit') ||
    text.includes('monthly user token quota exceeded') ||
    text.includes('monthly user tokenplan credit quota exceeded') ||
    text.includes('daily user call quota exceeded') ||
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
    text.includes('user_monthly_token_limit') ||
    text.includes('user_monthly_credit_limit') ||
    text.includes('monthly user token quota exceeded') ||
    text.includes('monthly user tokenplan credit quota exceeded')
  ) {
    return MONTHLY_USER_LIMIT_MESSAGE;
  }
  if (
    text.includes('user_daily_call_limit') ||
    text.includes('daily user call quota exceeded')
  ) {
    return DAILY_USER_LIMIT_MESSAGE;
  }
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
