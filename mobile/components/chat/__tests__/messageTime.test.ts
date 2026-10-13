import { buildMessageTimeDividerItems } from '../messageTime';
import type { UIMessage } from '../../../hooks/useChatEngine';

function message(id: string, createdAt: string): UIMessage {
  return {
    id,
    role: id.startsWith('u') ? 'user' : 'assistant',
    content: id,
    streaming: false,
    createdAt,
  };
}

describe('chat message time dividers', () => {
  it('inserts dividers for the first message and gaps over five minutes', () => {
    const items = buildMessageTimeDividerItems([
      message('u1', '2026-07-14T12:30:00'),
      message('a2', '2026-07-14T12:31:00'),
      message('u3', '2026-07-14T12:38:00'),
    ], 'UTC');

    expect(items.map(item => item.type)).toEqual(['divider', 'message', 'message', 'divider', 'message']);
    expect(items.filter(item => item.type === 'divider')).toHaveLength(2);
  });
});

import { formatMessageTimeDividerLabel, shouldShowMessageTimeDivider, formatConversationDate } from '../messageTime';

it.each([
  ['Asia/Shanghai', '今天 23:06'],
  ['America/Los_Angeles', '今天 08:06'],
  ['Asia/Kathmandu', '今天 20:51'],
])('uses the account timezone %s for legacy UTC message times', (timezone, expected) => {
  expect(formatMessageTimeDividerLabel('2026-10-13T15:06:00', new Date('2026-10-13T15:07:00Z'), timezone)).toBe(expected);
});

it.each(['2026-10-13T15:06:00Z', '2026-10-13T23:06:00+08:00', '2026-10-13T08:06:00-07:00'])('preserves the instant of offset timestamps: %s', value => {
  expect(formatMessageTimeDividerLabel(value, new Date('2026-10-13T15:07:00Z'), 'Asia/Shanghai')).toBe('今天 23:06');
});

it('uses user calendar midnight, even for a two-minute message gap', () => {
  expect(shouldShowMessageTimeDivider('2026-10-13T15:59:00Z', '2026-10-13T16:01:00Z', 'Asia/Shanghai')).toBe(true);
  expect(shouldShowMessageTimeDivider('2026-10-13T15:59:00Z', '2026-10-13T16:01:00Z', 'America/Los_Angeles')).toBe(false);
  expect(formatConversationDate('2026-10-13T16:01:00', 'Asia/Shanghai')).toBe('2026-10-14');
});

it('compares calendar yesterday over DST spring and fall rather than subtracting 24 hours', () => {
  expect(formatMessageTimeDividerLabel('2026-03-08T06:30:00Z', new Date('2026-03-09T04:15:00Z'), 'America/New_York')).toBe('昨天 01:30');
  expect(formatMessageTimeDividerLabel('2026-11-01T04:30:00Z', new Date('2026-11-02T04:45:00Z'), 'America/New_York')).toBe('今天 00:30');
  expect(formatMessageTimeDividerLabel('2026-03-08T07:30:00Z', new Date('2026-03-08T08:00:00Z'), 'America/New_York')).toBe('今天 03:30');
});

it.each([undefined, 'Not/A_Zone'])('does not pretend device time is a user setting when timezone is %s', timezone => {
  expect(formatMessageTimeDividerLabel('2026-10-13T15:06:00Z', new Date(), timezone)).toBe('');
});
