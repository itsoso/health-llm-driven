import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import RhinitisPage from './page';
const { post } = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock('@/services/api/client', () => ({ api: { post } }));
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => ({ token: 'synthetic' }) }));
vi.mock('@/components/ProtectedRoute', () => ({ default: ({ children }: { children: React.ReactNode }) => children }));
const row = { id: 7, checkin_date: '2026-10-31', nasal_wash_count: 3,
  nasal_wash_times: [{ event_id: 'old-event', time: '12:00', count: 3, type: 'wash' }],
  sneeze_count: 0, sneeze_times: [], notes: '' };
beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal('fetch', vi.fn(async (url: string) => ({ ok: true,
    json: async () => url.includes('/stats') ? { total_records: 0 } : row,
  })));
});
afterEach(() => vi.unstubAllGlobals());
function page() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}><RhinitisPage /></QueryClientProvider>);
}
it('preserves soak and manual time while appending rather than sending a daily snapshot', async () => {
  post.mockImplementation(async (_path, request) => ({ data: { ...row, nasal_wash_count: 4, nasal_wash_times: [...row.nasal_wash_times, request] } }));
  const { container } = page();
  await screen.findByText('12:00 - 💧洗鼻 3次');
  fireEvent.click(screen.getByLabelText('🫧 泡鼻'));
  fireEvent.change(container.querySelectorAll('input[type="time"]')[1], { target: { value: '14:30' } });
  fireEvent.click(screen.getAllByText('➕ 添加记录')[1]);
  await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
  expect(post.mock.calls[0]).toEqual(['/checkin/nasal-wash', {
    event_id: expect.any(String), record_date: expect.any(String), count: 1, type: 'soak', time: '14:30',
  }]);
});
it('locks the uncertain facts and retries with the original identity', async () => {
  post.mockRejectedValueOnce(new Error('network')).mockImplementation(async (_path, request) => ({ data: { ...row, nasal_wash_count: 4, nasal_wash_times: [...row.nasal_wash_times, request] } }));
  page();
  await screen.findByText('12:00 - 💧洗鼻 3次');
  fireEvent.click(screen.getAllByText('➕ 添加记录')[1]);
  await screen.findByText('重试记录');
  expect(screen.getByLabelText('🫧 泡鼻')).toBeDisabled();
  fireEvent.click(screen.getByText('重试记录'));
  await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
  expect(post.mock.calls[1][1]).toEqual(post.mock.calls[0][1]);
});

it('explains validation rejection and allows correcting the request', async () => {
  post.mockRejectedValue({ response: { status: 422, data: { detail: [{ msg: 'invalid' }] } } });
  page();
  await screen.findByText('12:00 - 💧洗鼻 3次');
  fireEvent.click(screen.getAllByText('➕ 添加记录')[1]);
  await screen.findByText('记录内容未通过校验，请检查日期和时间后重新提交。');
  expect(screen.getByLabelText('🫧 泡鼻')).not.toBeDisabled();
  expect(screen.queryByText('重试记录')).not.toBeInTheDocument();
});
