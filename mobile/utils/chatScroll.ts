export type ChatScrollState = {
  forcePending: boolean;
  isNearBottom: boolean;
};

export type ChatScrollMetrics = {
  layoutHeight: number;
  offsetY: number;
  contentHeight: number;
};

export const CHAT_NEAR_BOTTOM_THRESHOLD = 120;

/**
 * A transcript should follow its end while the opening/focus scroll is settling,
 * or while the user was already reading the latest messages.
 */
export function shouldScrollChatToEnd(state: ChatScrollState): boolean {
  return state.forcePending || state.isNearBottom;
}

export function isChatNearBottom(
  metrics: ChatScrollMetrics,
  threshold: number = CHAT_NEAR_BOTTOM_THRESHOLD,
): boolean {
  return metrics.contentHeight - metrics.offsetY - metrics.layoutHeight < threshold;
}

export function shouldShowScrollToBottom(state: ChatScrollState): boolean {
  return !state.forcePending && !state.isNearBottom;
}

/** Initial history hydration should win over the list's default offset. */
export function shouldForceScrollAfterHydration(
  previousMessageCount: number,
  nextMessageCount: number,
): boolean {
  return previousMessageCount === 0 && nextMessageCount > 0;
}

/** User intent takes precedence over a pending automatic scroll. */
export function cancelChatScrollOnUserDrag(state: ChatScrollState): void {
  state.forcePending = false;
  state.isNearBottom = false;
}
