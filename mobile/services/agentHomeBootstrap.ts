import {
  fetchConversationStarters,
  type ConversationOpener,
  type SuggestionMeta,
} from './conversationOpener';
import { getLlmPreference, type PreferenceResponse } from './llmPreference';
import { fetchMemoryOpener, type MemoryOpenerItem } from './memoryOpener';

export interface AgentHomeBootstrapSnapshot {
  opener: ConversationOpener | null;
  suggestions: SuggestionMeta[] | null;
  onboarding: boolean;
  memory: MemoryOpenerItem[];
  llmPreference: PreferenceResponse;
  errors: Array<'history' | 'starters' | 'memory' | 'llm_preference'>;
}

interface AgentHomeBootstrapDependencies {
  loadLatestConversation: () => Promise<unknown>;
  fetchStarters?: typeof fetchConversationStarters;
  fetchMemory?: () => Promise<MemoryOpenerItem[]>;
  fetchLlmPreference?: typeof getLlmPreference;
}

const EMPTY_LLM_PREFERENCE: PreferenceResponse = { model_id: null, options: [] };

export async function loadAgentHomeBootstrap({
  loadLatestConversation,
  fetchStarters = fetchConversationStarters,
  fetchMemory = () => fetchMemoryOpener(2),
  fetchLlmPreference = getLlmPreference,
}: AgentHomeBootstrapDependencies): Promise<AgentHomeBootstrapSnapshot> {
  const [historyResult, startersResult, memoryResult, llmResult] = await Promise.allSettled([
    loadLatestConversation(),
    fetchStarters(),
    fetchMemory(),
    fetchLlmPreference(),
  ] as const);
  const errors: AgentHomeBootstrapSnapshot['errors'] = [];
  if (historyResult.status === 'rejected') errors.push('history');
  if (startersResult.status === 'rejected') errors.push('starters');
  if (memoryResult.status === 'rejected') errors.push('memory');
  if (llmResult.status === 'rejected') errors.push('llm_preference');

  const starters = startersResult.status === 'fulfilled'
    ? startersResult.value
    : { opener: null, suggestions: null, onboarding: false };
  return {
    opener: starters.opener ?? null,
    suggestions: starters.suggestions ?? null,
    onboarding: starters.onboarding === true,
    memory: memoryResult.status === 'fulfilled' ? memoryResult.value : [],
    llmPreference: llmResult.status === 'fulfilled' ? llmResult.value : EMPTY_LLM_PREFERENCE,
    errors,
  };
}
