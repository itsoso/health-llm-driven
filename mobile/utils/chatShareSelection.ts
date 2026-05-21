type ShareableChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  streaming?: boolean;
  cardType?: string;
};

const ROLE_LABEL: Record<ShareableChatMessage['role'], string> = {
  user: '我',
  assistant: '健康 Agent',
};

export function isShareableChatMessage(message: ShareableChatMessage): boolean {
  return !message.streaming && !message.cardType && Boolean((message.content || '').trim());
}

export function buildSelectedChatShareMessage(
  messages: ShareableChatMessage[],
  selectedIds: Set<string>,
): string {
  const parts = messages
    .filter(message => selectedIds.has(message.id) && isShareableChatMessage(message))
    .map(message => `【${ROLE_LABEL[message.role] || message.role}】\n${message.content.trim()}`);

  return parts.length > 0
    ? `${parts.join('\n\n')}\n\n— 健康 Agent 对话节选`
    : '';
}
