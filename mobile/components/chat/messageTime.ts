import type { UIMessage } from '../../hooks/useChatEngine';

const DIVIDER_GAP_MS = 5 * 60 * 1000;

export type ChatMessageTimeDividerItem = {
  type: 'divider';
  id: string;
  label: string;
};

export type ChatMessageListItem =
  | ChatMessageTimeDividerItem
  | { type: 'message'; id: string; message: UIMessage };

function parseMessageDate(value?: string | null): Date | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function sameLocalDate(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear()
    && a.getMonth() === b.getMonth()
    && a.getDate() === b.getDate();
}

export function shouldShowMessageTimeDivider(
  previousCreatedAt: string | null | undefined,
  currentCreatedAt: string | null | undefined,
): boolean {
  const current = parseMessageDate(currentCreatedAt);
  if (!current) return false;
  const previous = parseMessageDate(previousCreatedAt);
  if (!previous) return true;
  return !sameLocalDate(previous, current)
    || current.getTime() - previous.getTime() >= DIVIDER_GAP_MS;
}

export function formatMessageTimeDividerLabel(value?: string | null, now = new Date()): string {
  const date = parseMessageDate(value);
  if (!date) return '';
  const time = date.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
  if (sameLocalDate(date, now)) return `今天 ${time}`;

  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (sameLocalDate(date, yesterday)) return `昨天 ${time}`;

  const day = date.toLocaleDateString('zh-CN', {
    month: 'numeric',
    day: 'numeric',
  });
  return `${day} ${time}`;
}

export function buildMessageTimeDividerItems(messages: UIMessage[]): ChatMessageListItem[] {
  const items: ChatMessageListItem[] = [];
  let previous: UIMessage | null = null;
  for (const message of messages) {
    if (shouldShowMessageTimeDivider(previous?.createdAt, message.createdAt)) {
      const label = formatMessageTimeDividerLabel(message.createdAt);
      if (label) {
        items.push({
          type: 'divider',
          id: `time-${message.id}`,
          label,
        });
      }
    }
    items.push({ type: 'message', id: message.id, message });
    previous = message;
  }
  return items;
}
