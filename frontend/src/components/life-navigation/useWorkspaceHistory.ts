import { useCallback, useReducer, useRef } from 'react';
import { copy } from './model';

/** Account-scoped, bounded, in-memory history of unsaved workspace edits. */
export function useWorkspaceHistory<T>(limit = 30) {
  if (!Number.isInteger(limit) || limit < 1) throw new Error('History limit must be a positive integer');
  const past = useRef<T[]>([]);
  const future = useRef<T[]>([]);
  const [, refresh] = useReducer((value: number) => value + 1, 0);
  const clear = useCallback(() => {
    past.current = [];
    future.current = [];
    refresh();
  }, []);
  const capture = useCallback((value: T) => {
    past.current.push(copy(value));
    if (past.current.length > limit) past.current.splice(0, past.current.length - limit);
    future.current = [];
    refresh();
  }, [limit]);
  const undo = useCallback((current: T): T | null => {
    if (!past.current.length) return null;
    const previous = past.current.pop()!;
    future.current.push(copy(current));
    refresh();
    return copy(previous);
  }, []);
  const redo = useCallback((current: T): T | null => {
    if (!future.current.length) return null;
    const next = future.current.pop()!;
    past.current.push(copy(current));
    refresh();
    return copy(next);
  }, []);
  return { capture, undo, redo, clear, canUndo: past.current.length > 0, canRedo: future.current.length > 0 };
}
