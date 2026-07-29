import type { ChatMessage } from '@/services/api/ai';

const ROLE_LABEL: Record<ChatMessage['role'], string> = {
  user: '我',
  assistant: '健康 Agent',
};

export function buildSelectedChatShareText(
  messages: Pick<ChatMessage, 'id' | 'role' | 'content'>[],
  selectedIds: Set<number>,
): string {
  const parts = messages
    .filter(message => selectedIds.has(message.id))
    .map(message => ({
      role: ROLE_LABEL[message.role] || message.role,
      content: (message.content || '').trim(),
    }))
    .filter(message => message.content)
    .map(message => `【${message.role}】\n${message.content}`);

  return parts.length > 0
    ? `${parts.join('\n\n')}\n\n— 健康 Agent 对话节选`
    : '';
}

export function getShareableMessageIds(messages: Pick<ChatMessage, 'id' | 'content'>[]): Set<number> {
  return new Set(messages.filter(message => (message.content || '').trim()).map(message => message.id));
}

export function durableSelectedMessageIds(
  messages: Pick<ChatMessage, 'id' | 'role' | 'content'>[],
  selectedIds: Set<number>,
): number[] {
  const selected = messages.filter(message => selectedIds.has(message.id));
  if (selected.length === 0 || selected.length !== selectedIds.size) {
    throw new Error('selected_agent_message_not_durable');
  }
  const durableIds = selected.map(message => message.id);
  if (
    durableIds.some(messageId => (
      !Number.isInteger(messageId) || messageId <= 0
    ))
    || new Set(durableIds).size !== durableIds.length
  ) {
    throw new Error('selected_agent_message_not_durable');
  }
  return durableIds;
}
