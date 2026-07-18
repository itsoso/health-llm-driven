export type ChatScrollState = {
  forcePending: boolean;
  isNearBottom: boolean;
};

/**
 * A transcript should follow its end while the opening/focus scroll is settling,
 * or while the user was already reading the latest messages.
 */
export function shouldScrollChatToEnd(state: ChatScrollState): boolean {
  return state.forcePending || state.isNearBottom;
}

/** User intent takes precedence over a pending automatic scroll. */
export function cancelChatScrollOnUserDrag(state: ChatScrollState): void {
  state.forcePending = false;
  state.isNearBottom = false;
}
