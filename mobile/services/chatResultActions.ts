import api from './api';

export async function saveAssistantReplyAsMemory(text: string): Promise<void> {
  const value = text.trim();
  if (!value) return;

  await api.post('/memory-facts', {
    tier: 'working',
    subject: 'assistant_reply',
    predicate: 'suggests',
    object_value: value,
    confidence: 0.6,
    tags: ['chat', 'assistant_suggestion'],
    is_sensitive: false,
  });
}
