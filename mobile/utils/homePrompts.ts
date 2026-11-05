/** Retired home shortcut, including text-only replies from older servers. */
export function isHomePhotoEntry(text: string, action?: string): boolean {
  return action === 'photo_meal' || /^拍照(?:记一餐|记餐|记录一餐)$/.test(text.trim());
}

/** Keep server ranking, but apply visibility rules before taking the display limit. */
export function selectHomeSuggestions<T extends { text: string }>(items: T[], limit = 2): T[] {
  const seen = new Set<string>();
  return items.flatMap(item => {
    const text = item.text.trim();
    if (!text || isHomePhotoEntry(text) || seen.has(text)) return [];
    seen.add(text);
    return [item];
  }).slice(0, limit);
}

/** Neutral invitations: time alone must never imply a health fact or a completed action. */
export function freshConversationPrompt(hour: number): { text: string; reply: string } {
  if (hour < 5) return { text: '现在感觉怎么样？想聊什么，直接告诉我就好。', reply: '聊聊现在的状态' };
  if (hour < 11) return { text: '昨晚睡得怎么样？想聊睡眠或记录身体状态，直接告诉我就好。', reply: '聊聊昨晚的睡眠' };
  if (hour < 14) return { text: '今天吃得怎么样？想聊饮食或记录身体状态，直接告诉我就好。', reply: '聊聊今天的饮食' };
  if (hour < 18) return { text: '下午感觉怎么样？想聊活动或记录身体状态，直接告诉我就好。', reply: '聊聊下午的状态' };
  return { text: '今天过得怎么样？想回顾一天或记录身体状态，直接告诉我就好。', reply: '回顾今天的状态' };
}
