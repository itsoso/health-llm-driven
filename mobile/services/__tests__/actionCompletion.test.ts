import { completeActionWithUndo } from '../actionCompletion';

function makeDeps(overrides: Partial<Parameters<typeof completeActionWithUndo>[0]> = {}) {
  return {
    cardId: 7,
    cardTitle: '今天补镁 200mg',
    completeCard: jest.fn().mockResolvedValue(undefined),
    reactivateCard: jest.fn().mockResolvedValue(undefined),
    refetchCards: jest.fn(),
    showUndoable: jest.fn(),
    showError: jest.fn(),
    ...overrides,
  };
}

describe('completeActionWithUndo', () => {
  it('completes and offers an undo toast on success', async () => {
    const deps = makeDeps();
    await completeActionWithUndo(deps);
    expect(deps.completeCard).toHaveBeenCalledWith(7);
    expect(deps.refetchCards).toHaveBeenCalledTimes(1);
    expect(deps.showUndoable).toHaveBeenCalledWith(
      expect.stringContaining('已完成'),
      expect.any(Function),
      5000,
    );
    expect(deps.showError).not.toHaveBeenCalled();
  });

  it('surfaces an error and does NOT fake success when completing fails', async () => {
    const deps = makeDeps({ completeCard: jest.fn().mockRejectedValue(new Error('network')) });
    await completeActionWithUndo(deps);
    expect(deps.showError).toHaveBeenCalledWith('标记完成失败，请重试');
    expect(deps.showUndoable).not.toHaveBeenCalled();
    expect(deps.refetchCards).not.toHaveBeenCalled();
  });

  it('surfaces an error when the undo (reactivate) fails instead of silently swallowing', async () => {
    const deps = makeDeps({ reactivateCard: jest.fn().mockRejectedValue(new Error('network')) });
    await completeActionWithUndo(deps);
    // grab the onUndo callback handed to showUndoable and invoke it
    const onUndo = (deps.showUndoable as jest.Mock).mock.calls[0][1];
    await onUndo();
    expect(deps.reactivateCard).toHaveBeenCalledWith(7);
    expect(deps.showError).toHaveBeenCalledWith('撤销失败，请重试');
  });

  it('refetches again after a successful undo', async () => {
    const deps = makeDeps();
    await completeActionWithUndo(deps);
    const onUndo = (deps.showUndoable as jest.Mock).mock.calls[0][1];
    await onUndo();
    expect(deps.reactivateCard).toHaveBeenCalledWith(7);
    // once after complete, once after undo
    expect(deps.refetchCards).toHaveBeenCalledTimes(2);
    expect(deps.showError).not.toHaveBeenCalled();
  });

  it('truncates long card titles in the toast message', async () => {
    const deps = makeDeps({ cardTitle: '一二三四五六七八九十一二三四五六七八九十' });
    await completeActionWithUndo(deps);
    const msg = (deps.showUndoable as jest.Mock).mock.calls[0][0];
    expect(msg).toBe('已完成「一二三四五六七八九十一二三四」');
  });
});
