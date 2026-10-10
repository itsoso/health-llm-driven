import React from 'react';
import { fireEvent, render, screen, waitFor, cleanup } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { getLifeWorkspace, saveLifeWorkspace } from '@/services/lifeNavigation';
import { blankData } from './model';
import LifeNavigationWorkspace from './LifeNavigationWorkspace';
let user = { id: 7 };
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => ({ user, isAuthenticated: true }) }));
vi.mock('@/services/lifeNavigation', () => ({ getLifeWorkspace: vi.fn(), saveLifeWorkspace: vi.fn(), getLifeHistory: vi.fn().mockResolvedValue([]), getLifeBackup: vi.fn(), importLifeBackup: vi.fn(), restoreLifeWorkspace: vi.fn() }));
const workspace = { schema_version: 'life_navigation.v1' as const, revision: 3, data: blankData(), updated_at: '2026-10-10T00:00:00Z' };
async function openDirection() {
  fireEvent.click(await screen.findByRole('button', { name: '方向与季度', exact: true }));
}
function changeVision(value: string) { fireEvent.change(screen.getByLabelText('愿景'), { target: { value } }); }
afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks(); user = { id: 7 };
  vi.mocked(getLifeWorkspace).mockResolvedValue(workspace);
  vi.mocked(saveLifeWorkspace).mockImplementation(async (_owner, revision, data) => ({ ...workspace, revision: revision + 1, data }));
});
describe('workspace undo boundary', () => {
  it('undoes and redoes a draft, then clears history only after a successful save', async () => {
    render(<LifeNavigationWorkspace />); await openDirection();
    expect(screen.getByRole('button', { name: '撤销', exact: true })).toBeDisabled();
    changeVision('First authored direction');
    changeVision('Updated direction');
    fireEvent.click(screen.getByRole('button', { name: '撤销', exact: true }));
    expect(screen.getByLabelText('愿景')).toHaveValue('First authored direction');
    fireEvent.click(screen.getByRole('button', { name: '重做', exact: true }));
    expect(screen.getByLabelText('愿景')).toHaveValue('Updated direction');
    expect(saveLifeWorkspace).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '保存工作区', exact: true }));
    await waitFor(() => expect(saveLifeWorkspace).toHaveBeenCalledWith(7, 3, expect.objectContaining({ strategy: expect.objectContaining({ vision: 'Updated direction' }) })));
    await waitFor(() => expect(screen.getByRole('button', { name: '撤销', exact: true })).toBeDisabled());
    expect(screen.getByRole('button', { name: '重做', exact: true })).toBeDisabled();
  });
  it('retains conflict drafts and history without claiming a successful save', async () => {
    vi.mocked(saveLifeWorkspace).mockRejectedValue({ response: { status: 409 } });
    render(<LifeNavigationWorkspace />); await openDirection();
    changeVision('Conflict draft');
    fireEvent.click(screen.getByRole('button', { name: '保存工作区', exact: true }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('版本冲突'));
    expect(screen.getByLabelText('愿景')).toHaveValue('Conflict draft');
    expect(screen.getByRole('button', { name: '撤销', exact: true })).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: '撤销', exact: true }));
    expect(screen.getByLabelText('愿景')).toHaveValue('');
    expect(saveLifeWorkspace).toHaveBeenCalledTimes(1);
  });
  it('cannot restore private history after switching accounts', async () => {
    const view = render(<LifeNavigationWorkspace />); await openDirection();
    changeVision('Account A private text');
    user = { id: 8 }; view.rerender(<LifeNavigationWorkspace />);
    await waitFor(() => expect(getLifeWorkspace).toHaveBeenCalledWith(8, expect.any(AbortSignal)));
    await openDirection();
    expect(screen.getByRole('button', { name: '撤销', exact: true })).toBeDisabled();
    expect(screen.getByRole('button', { name: '重做', exact: true })).toBeDisabled();
    expect(screen.getByLabelText('愿景')).toHaveValue('');
  });
});

it('can undo a failed timer start without inventing a saved timer', async () => {
  vi.mocked(saveLifeWorkspace).mockRejectedValue({ response: { status: 409 } });
  render(<LifeNavigationWorkspace />);
  fireEvent.click(await screen.findByRole('button', { name: '时段导航', exact: true }));
  fireEvent.click(screen.getByRole('button', { name: '开始并保存' }));
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('版本冲突'));
  fireEvent.click(screen.getByRole('button', { name: '撤销', exact: true }));
  expect(screen.getByRole('button', { name: '开始并保存' })).toBeVisible();
  expect(saveLifeWorkspace).toHaveBeenCalledTimes(1);
});

it('clears successful reload history and keeps failed reload edits recoverable', async () => {
  vi.spyOn(window, 'confirm').mockReturnValue(true);
  render(<LifeNavigationWorkspace />); await openDirection();
  changeVision('Local unsaved direction');
  vi.mocked(getLifeWorkspace).mockRejectedValueOnce(new Error('Synthetic network failure'));
  fireEvent.click(screen.getByRole('button', { name: '重新读取' }));
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('操作未确认成功'));
  expect(screen.getByLabelText('愿景')).toHaveValue('Local unsaved direction');
  expect(screen.getByRole('button', { name: '撤销', exact: true })).toBeEnabled();
  const data = blankData(); data.strategy.vision = 'Server direction';
  vi.mocked(getLifeWorkspace).mockResolvedValueOnce({ ...workspace, data, revision: 4 });
  fireEvent.click(screen.getByRole('button', { name: '重新读取' }));
  await waitFor(() => expect(screen.getByLabelText('愿景')).toHaveValue('Server direction'));
  expect(screen.getByRole('button', { name: '撤销', exact: true })).toBeDisabled();
  expect(screen.getByRole('button', { name: '重做', exact: true })).toBeDisabled();
  vi.restoreAllMocks();
});

it('disables undo while a write is pending and starts a fresh history after saving', async () => {
  let finish!: (value: typeof workspace) => void;
  vi.mocked(saveLifeWorkspace).mockReturnValueOnce(new Promise(resolve => { finish = resolve; }));
  render(<LifeNavigationWorkspace />); await openDirection();
  changeVision('Saved baseline');
  fireEvent.click(screen.getByRole('button', { name: '保存工作区' }));
  expect(screen.getByRole('button', { name: '撤销', exact: true })).toBeDisabled();
  const data = blankData(); data.strategy.vision = 'Saved baseline';
  finish({ ...workspace, data, revision: 4 });
  await waitFor(() => expect(screen.getByRole('button', { name: '保存工作区' })).toBeEnabled());
  changeVision('Another draft');
  fireEvent.click(screen.getByRole('button', { name: '撤销', exact: true }));
  expect(screen.getByLabelText('愿景')).toHaveValue('Saved baseline');
  expect(screen.getByRole('button', { name: '撤销', exact: true })).toBeDisabled();
});
