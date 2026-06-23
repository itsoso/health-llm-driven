import api from './api';
import { canonicalModelId, isAdvancedChatModelId, sanitizeLlmPreference } from './llmModelCatalog';

export interface ModelOption {
  id: string;
  label: string;
  provider: string;
  model: string;
  speed_tier: 'fast' | 'balanced' | 'reasoning' | string;
  note: string;
}

export interface PreferenceResponse {
  model_id: string | null;
  options: ModelOption[];
}

export async function getLlmPreference(): Promise<PreferenceResponse> {
  const res = await api.get<PreferenceResponse>('/me/llm-preference');
  return sanitizeLlmPreference(res.data);
}

export async function updateLlmPreference(modelId: string | null): Promise<PreferenceResponse> {
  const canonical = canonicalModelId(modelId);
  const nextModelId = canonical && isAdvancedChatModelId(canonical) ? canonical : null;
  const res = await api.put<PreferenceResponse>('/me/llm-preference', { model_id: nextModelId });
  return sanitizeLlmPreference(res.data);
}
