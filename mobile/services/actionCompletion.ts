/**
 * completeActionWithUndo —— action-card 完成 + 5s 撤销窗口的纯逻辑 (从 alerts.tsx 抽出, 可单测).
 *
 * rule#1: 完成失败、撤销失败都必须让用户感知 (error toast), 不能假装成功.
 * 之前 alerts.tsx 内联版本: 完成路径无 try/catch (失败照弹"已完成"), 撤销 catch 静默.
 */

export interface CompleteWithUndoDeps {
  cardId: number;
  cardTitle: string;
  completeCard: (id: number) => Promise<unknown>;
  reactivateCard: (id: number) => Promise<unknown>;
  refetchCards: () => void;
  showUndoable: (msg: string, onUndo: () => void | Promise<void>, durationMs?: number) => void;
  showError: (msg: string) => void;
  undoWindowMs?: number;
}

export async function completeActionWithUndo({
  cardId,
  cardTitle,
  completeCard,
  reactivateCard,
  refetchCards,
  showUndoable,
  showError,
  undoWindowMs = 5000,
}: CompleteWithUndoDeps): Promise<void> {
  try {
    await completeCard(cardId);
  } catch {
    showError('标记完成失败，请重试');
    return;
  }
  refetchCards();
  showUndoable(
    `已完成「${cardTitle.slice(0, 14)}」`,
    async () => {
      try {
        await reactivateCard(cardId);
        refetchCards();
      } catch {
        showError('撤销失败，请重试');
      }
    },
    undoWindowMs,
  );
}
