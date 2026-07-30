type ShareableChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  streaming?: boolean;
  cardType?: string;
  completionStatus?: 'complete' | 'interrupted' | 'error' | 'unknown';
  imageUris?: string[];
  sourceMessageId?: number;
};

const ROLE_LABEL: Record<ShareableChatMessage['role'], string> = {
  user: '我',
  assistant: '小巴',
};

export function isShareableChatMessage(message: ShareableChatMessage): boolean {
  if (message.streaming || message.cardType) {
    return false;
  }
  if (message.completionStatus === 'interrupted' || message.completionStatus === 'error') {
    return false;
  }
  const content = message.content || '';
  const hasShareableText = content.trim().length > 0;
  const hasShareableImage = (message.imageUris || []).some(uri => !!String(uri || '').trim());
  return (hasShareableText || hasShareableImage)
    && !content.includes('[回复因长度限制中断')
    && !content.includes('[回复中断');
}

function formatImageReferences(imageUris?: string[]): string[] {
  return (imageUris || [])
    .map(uri => String(uri || '').trim())
    .filter(Boolean)
    .map((uri, index) => `![对话图片 ${index + 1}](${uri})`);
}

export function buildSelectedChatShareMessage(
  messages: ShareableChatMessage[],
  selectedIds: Set<string>,
): string {
  const parts = messages
    .filter(message => selectedIds.has(message.id) && isShareableChatMessage(message))
    .map(message => {
      const body = [
        message.content.trim(),
        ...formatImageReferences(message.imageUris),
      ].filter(Boolean).join('\n\n');
      return `【${ROLE_LABEL[message.role] || message.role}】\n${body}`;
    });

  return parts.length > 0
    ? `${parts.join('\n\n')}\n\n— 小巴对话节选`
    : '';
}

export function durableSelectedAgentMessageIds(
  messages: ShareableChatMessage[],
  selectedIds: Set<string>,
): number[] {
  const selected = messages.filter(message => selectedIds.has(message.id));
  if (selected.length === 0 || selected.length !== selectedIds.size) {
    throw new Error('selected_agent_message_not_durable');
  }

  const durableIds = selected.map((message) => {
    const durableId = message.sourceMessageId;
    if (
      !isShareableChatMessage(message)
      || !Number.isInteger(durableId)
      || (durableId as number) <= 0
    ) {
      throw new Error('selected_agent_message_not_durable');
    }
    return durableId as number;
  });
  if (new Set(durableIds).size !== durableIds.length) {
    throw new Error('selected_agent_message_not_durable');
  }
  return durableIds;
}
