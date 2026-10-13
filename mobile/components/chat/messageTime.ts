import type { UIMessage } from '../../hooks/useChatEngine';

const DIVIDER_GAP_MS = 5 * 60 * 1000;
const formatters = new Map<string, Intl.DateTimeFormat>();

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
  // Legacy AgentMessage/Conversation datetimes are stored as naive UTC.
  // Explicit offsets and newly serialized Z timestamps already identify an instant.
  const normalized = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?$/.test(value)
    ? `${value.replace(' ', 'T')}Z`
    : value;
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? null : date;
}

function zonedParts(date: Date, timezone?: string): Record<string, string> | null {
  if (!timezone) return null;
  let formatter = formatters.get(timezone);
  if (!formatter) {
    try {
      formatter = new Intl.DateTimeFormat('en-GB', {
        timeZone: timezone,
        year: 'numeric', month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
      });
    } catch {
      // An unavailable/invalid account setting must not masquerade as device time.
      return null;
    }
    // Bounded, immutable formatter cache; keys contain no account data.
    if (formatters.size >= 8) formatters.delete(formatters.keys().next().value!);
    formatters.set(timezone, formatter);
  }
  return Object.fromEntries(formatter.formatToParts(date).map(part => [part.type, part.value]));
}

function calendarDay(parts: Record<string, string>): number {
  return Date.UTC(Number(parts.year), Number(parts.month) - 1, Number(parts.day));
}

export function formatConversationDate(value?: string | null, timezone?: string): string {
  const date = parseMessageDate(value);
  const parts = date && zonedParts(date, timezone);
  return parts ? `${parts.year}-${parts.month}-${parts.day}` : '';
}

export function shouldShowMessageTimeDivider(
  previousCreatedAt: string | null | undefined,
  currentCreatedAt: string | null | undefined,
  timezone?: string,
): boolean {
  const current = parseMessageDate(currentCreatedAt);
  if (!current) return false;
  const previous = parseMessageDate(previousCreatedAt);
  if (!previous) return true;
  const currentParts = zonedParts(current, timezone);
  const previousParts = zonedParts(previous, timezone);
  return Boolean(currentParts && previousParts && calendarDay(currentParts) !== calendarDay(previousParts))
    || current.getTime() - previous.getTime() >= DIVIDER_GAP_MS;
}

export function formatMessageTimeDividerLabel(value?: string | null, now = new Date(), timezone?: string): string {
  const date = parseMessageDate(value);
  const parts = date && zonedParts(date, timezone);
  const today = zonedParts(now, timezone);
  if (!parts || !today) return '';
  const time = `${parts.hour}:${parts.minute}`;
  const daysAgo = (calendarDay(today) - calendarDay(parts)) / 86_400_000;
  if (daysAgo === 0) return `今天 ${time}`;
  if (daysAgo === 1) return `昨天 ${time}`;
  return `${Number(parts.month)}/${Number(parts.day)} ${time}`;
}

export function buildMessageTimeDividerItems(messages: UIMessage[], timezone?: string): ChatMessageListItem[] {
  const items: ChatMessageListItem[] = [];
  let previous: UIMessage | null = null;
  for (const message of messages) {
    if (shouldShowMessageTimeDivider(previous?.createdAt, message.createdAt, timezone)) {
      const label = formatMessageTimeDividerLabel(message.createdAt, new Date(), timezone);
      if (label) {
        items.push({ type: 'divider', id: `time-${message.id}`, label });
      }
    }
    items.push({ type: 'message', id: message.id, message });
    previous = message;
  }
  return items;
}
