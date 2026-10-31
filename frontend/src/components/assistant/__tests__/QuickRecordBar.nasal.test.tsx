import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import QuickRecordBar from '../QuickRecordBar';

const { post, remove, showToast } = vi.hoisted(() => ({ post: vi.fn(), remove: vi.fn(), showToast: vi.fn() }));
vi.mock('@/services/api/client', () => ({ api: { post, delete: remove } }));
vi.mock('@/contexts/ToastContext', () => ({ useToast: () => ({ showToast }) }));

beforeEach(() => { vi.clearAllMocks(); });

it('appends an event using no cached total and undoes only that event', async () => {
  const saved = { id: 44, nasal_wash_count: 6, nasal_wash_times: [] as { event_id: string }[] };
  post.mockImplementation(async (_path, request) => { saved.nasal_wash_times = [{ event_id: request.event_id }]; return { data: saved }; });
  remove.mockResolvedValue({ data: { id: 44, nasal_wash_count: 8 } });
  const update = vi.fn();
  render(<QuickRecordBar rhinitisToday={{ nasal_wash_count: 2 }} onRhinitisUpdate={update} onWaterRecord={vi.fn()} />);
  fireEvent.click(screen.getByText('洗鼻+1'));
  await waitFor(() => expect(showToast).toHaveBeenCalled());
  const [path, data] = post.mock.calls[0];
  expect(path).toBe('/checkin/nasal-wash');
  expect(data).toEqual({ event_id: expect.any(String), record_date: expect.any(String), count: 1 });
  expect(update.mock.calls[0][0]({})).toEqual(saved);
  await act(async () => showToast.mock.calls[0][1].onUndo());
  expect(remove).toHaveBeenCalledWith(`/checkin/44/nasal-wash/${data.event_id}`);
  expect(update.mock.calls[1][0]({})).toEqual({ id: 44, nasal_wash_count: 8 });
});

it('reuses uncertain event on retry and creates a new ID only after success', async () => {
  vi.spyOn(console, 'error').mockImplementation(() => {});
  post.mockRejectedValueOnce(new Error('network')).mockImplementation(async (_path, request) => ({ data: { id: 44, nasal_wash_count: 1, nasal_wash_times: [{ event_id: request.event_id }] } }));
  render(<QuickRecordBar rhinitisToday={{}} onRhinitisUpdate={vi.fn()} onWaterRecord={vi.fn()} />);
  fireEvent.click(screen.getByText('洗鼻+1'));
  await waitFor(() => expect(showToast).toHaveBeenCalledTimes(1));
  fireEvent.click(screen.getByText('洗鼻+1'));
  await waitFor(() => expect(showToast).toHaveBeenCalledTimes(2));
  expect(post.mock.calls[1][1]).toEqual(post.mock.calls[0][1]);
  fireEvent.click(screen.getByText('洗鼻+1'));
  await waitFor(() => expect(post).toHaveBeenCalledTimes(3));
  expect(post.mock.calls[2][1].event_id).not.toBe(post.mock.calls[0][1].event_id);
  vi.restoreAllMocks();
});

it('does not confirm a response missing the requested event', async () => {
  vi.spyOn(console, 'error').mockImplementation(() => {});
  post.mockResolvedValue({ data: { id: 44, nasal_wash_count: 5, nasal_wash_times: [] } });
  const update = vi.fn();
  render(<QuickRecordBar rhinitisToday={{}} onRhinitisUpdate={update} onWaterRecord={vi.fn()} />);
  fireEvent.click(screen.getByText('洗鼻+1'));
  await waitFor(() => expect(showToast).toHaveBeenCalled());
  expect(showToast.mock.calls[0][1]).toBe('error');
  expect(update).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText('洗鼻+1'));
  await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
  expect(post.mock.calls[1][1]).toEqual(post.mock.calls[0][1]);
  vi.restoreAllMocks();
});
