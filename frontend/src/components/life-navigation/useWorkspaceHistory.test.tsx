import { act, renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { useWorkspaceHistory } from './useWorkspaceHistory';

describe('unsaved workspace history', () => {
  it('restores edits, discards an abandoned redo branch and isolates snapshots', () => {
    const { result } = renderHook(() => useWorkspaceHistory<{ title: string }>());
    const original = { title: 'original' };
    act(() => result.current.capture(original));
    original.title = 'mutated elsewhere';
    let restored: { title: string } | null = null;
    act(() => { restored = result.current.undo({ title: 'edited' }); });
    expect(restored).toEqual({ title: 'original' });
    expect(result.current.canRedo).toBe(true);
    act(() => { restored = result.current.redo({ title: 'original' }); });
    expect(restored).toEqual({ title: 'edited' });
    act(() => { restored = result.current.undo({ title: 'edited' }); });
    act(() => result.current.capture(restored!));
    expect(result.current.canRedo).toBe(false);
  });

  it('bounds private history and removes it after a confirmed save or reload', () => {
    const { result, unmount } = renderHook(() => useWorkspaceHistory<number>(2));
    act(() => { result.current.capture(1); result.current.capture(2); result.current.capture(3); });
    let value: number | null = 4;
    act(() => { value = result.current.undo(value!); });
    expect(value).toBe(3);
    act(() => { value = result.current.undo(value!); });
    expect(value).toBe(2);
    expect(result.current.canUndo).toBe(false);
    act(() => result.current.clear());
    expect(result.current.canRedo).toBe(false);
    expect(result.current.canUndo).toBe(false);
    unmount();
    const nextAccount = renderHook(() => useWorkspaceHistory<number>());
    expect(nextAccount.result.current.canUndo).toBe(false);
    expect(nextAccount.result.current.canRedo).toBe(false);
  });
});
