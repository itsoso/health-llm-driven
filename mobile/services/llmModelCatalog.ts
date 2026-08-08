export interface ModelOptionBase {
  id: string;
  label: string;
  provider: string;
  model: string;
  speed_tier: string;
  note?: string;
}

export const ADVANCED_CHAT_MODEL_IDS = [
  'claude-opus-4.7',
  'gemini-3.1-pro',
  'gpt-5.5',
  'qwen3.8-max',
  'qwen3.7-plus',
  'qwen3.7-max',
  'deepseek-v4-pro',
  'deepseek-v4-flash',
  'kimi-k2.7-code',
  'glm-5.2',
  'minimax-m2.5',
] as const;

const ADVANCED_CHAT_MODEL_ID_SET = new Set<string>(ADVANCED_CHAT_MODEL_IDS);

const MODEL_ID_ALIASES: Record<string, string> = {
  'commercial/claude-opus-4.7': 'claude-opus-4.7',
  'anthropic/claude-opus-4.7': 'claude-opus-4.7',
  'langbridge/claude-opus-4.7': 'claude-opus-4.7',
  'commercial/gemini-3.1-pro-preview': 'gemini-3.1-pro',
  'commercial/gemini-3.1-pro': 'gemini-3.1-pro',
  'google/gemini-3.1-pro': 'gemini-3.1-pro',
  'langbridge/gemini-3.1-pro': 'gemini-3.1-pro',
  'commercial/gpt-5.5': 'gpt-5.5',
  'openai/gpt-5.5': 'gpt-5.5',
  'langbridge/gpt-5.5': 'gpt-5.5',
  'tokenplan/qwen3.8-max-preview': 'qwen3.8-max-preview',
  'tokenplan/qwen3.8-max': 'qwen3.8-max',
  'qwen-3.8-max': 'qwen3.8-max',
  'qwen3.8': 'qwen3.8-max',
  'qwen-3.8': 'qwen3.8-max',
  'tokenplan/kimi-k2.7': 'kimi-k2.7-code',
  'kimi-k2.7': 'kimi-k2.7-code',
  'minimax-m2.5': 'minimax-m2.5',
  'minimax-m25': 'minimax-m2.5',
};

export function canonicalModelId(modelId: string | null | undefined): string | null {
  const raw = modelId?.trim();
  if (!raw) return null;

  const lower = raw.toLowerCase();
  const withoutProvider = lower.replace(/^(commercial|tokenplan|langbridge|anthropic|google|openai|deepseek|zhipu|minimax)[/:]/, '');
  return MODEL_ID_ALIASES[lower] || MODEL_ID_ALIASES[withoutProvider] || withoutProvider;
}

export function isAdvancedChatModelId(modelId: string | null | undefined): boolean {
  const canonical = canonicalModelId(modelId);
  return !!canonical && ADVANCED_CHAT_MODEL_ID_SET.has(canonical);
}

export function sanitizeModelOptions<T extends ModelOptionBase>(options: T[] | null | undefined): T[] {
  const seen = new Set<string>();
  const cleaned: T[] = [];

  for (const option of options || []) {
    const id = canonicalModelId(option.id);
    if (!id || !ADVANCED_CHAT_MODEL_ID_SET.has(id) || seen.has(id)) continue;
    seen.add(id);
    cleaned.push({ ...option, id });
  }

  return cleaned;
}

export function sanitizeLlmPreference<T extends { model_id: string | null; options: ModelOptionBase[] }>(pref: T): T {
  const options = sanitizeModelOptions(pref.options);
  const activeId = canonicalModelId(pref.model_id);
  const model_id = activeId && options.some(option => option.id === activeId) ? activeId : null;
  return { ...pref, model_id, options } as T;
}
