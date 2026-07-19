import {
  cancelChatScrollOnUserDrag,
  shouldForceScrollAfterHydration,
  shouldScrollChatToEnd,
  type ChatScrollState,
} from '../chatScroll';

describe('chat scroll policy', () => {
  it('keeps the transcript pinned while an opening scroll is pending', () => {
    const state: ChatScrollState = { forcePending: true, isNearBottom: false };

    expect(shouldScrollChatToEnd(state)).toBe(true);
  });

  it('still follows streamed layout changes when the user is already near the end', () => {
    expect(shouldScrollChatToEnd({ forcePending: false, isNearBottom: true })).toBe(true);
  });

  it('forces the first scroll after an async history load', () => {
    expect(shouldForceScrollAfterHydration(0, 4)).toBe(true);
    expect(shouldForceScrollAfterHydration(0, 0)).toBe(false);
    expect(shouldForceScrollAfterHydration(4, 5)).toBe(false);
  });

  it('stops the forced scroll as soon as the user starts reading history', () => {
    const state: ChatScrollState = { forcePending: true, isNearBottom: true };

    cancelChatScrollOnUserDrag(state);

    expect(state.forcePending).toBe(false);
    expect(state.isNearBottom).toBe(false);
    expect(shouldScrollChatToEnd(state)).toBe(false);
  });
});
