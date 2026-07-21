export const CHAT_SCROLL_SETTLE_DELAYS_MS = [0, 80, 220, 480, 900] as const;

export type ChatScrollTimer = number;
type ChatScrollSetTimer = (callback: () => void, delay: number) => ChatScrollTimer;

export function clearChatScrollTimers(timers: ChatScrollTimer[]) {
  timers.forEach(timer => window.clearTimeout(timer));
}

export function scheduleSettledScrollToBottom(options: {
  getElement: () => HTMLElement | null;
  clearExisting?: () => void;
  behavior?: ScrollBehavior;
  delays?: readonly number[];
  setTimer?: ChatScrollSetTimer;
}): ChatScrollTimer[] {
  const {
    getElement,
    clearExisting,
    behavior = 'smooth',
    delays = CHAT_SCROLL_SETTLE_DELAYS_MS,
    setTimer = (callback, delay) => window.setTimeout(callback, delay),
  } = options;

  clearExisting?.();
  return delays.map((delay, index) => setTimer(() => {
    const element = getElement();
    if (!element) return;
    element.scrollTo({
      top: element.scrollHeight,
      behavior: index === 0 ? behavior : 'auto',
    });
  }, delay));
}
