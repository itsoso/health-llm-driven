// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '@/services/api/client';
import DecisionControlPanel from './DecisionControlPanel';

vi.mock('@/services/api/client', () => ({ api: { get: vi.fn(), put: vi.fn() } }));
const initial = { enabled: false, revision: 0, effective_mode: 'off', configured: true, provider: 'laya', updated_at: '2026-09-24T02:00:00Z' };

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><DecisionControlPanel /></QueryClientProvider>);
}

describe('DecisionControlPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.get).mockResolvedValue({ data: initial });
  });

  it('saves the current revision and shows only the confirmed server state', async () => {
    vi.mocked(api.put).mockResolvedValue({ data: { ...initial, enabled: true, revision: 1, effective_mode: 'on' } });
    renderPanel();
    const toggle = await screen.findByRole('switch', { name: '全站意图决策' });
    expect(toggle).toHaveAttribute('aria-checked', 'false');
    fireEvent.click(toggle);
    await waitFor(() => expect(api.put).toHaveBeenCalledWith('/admin/decisions', { enabled: true, revision: 0 }));
    await waitFor(() => expect(toggle).toHaveAttribute('aria-checked', 'true'));
    expect(screen.getByText('设置已保存')).toBeInTheDocument();
  });

  it('does not pretend a failed save enabled the service', async () => {
    vi.mocked(api.put).mockRejectedValue({ response: { data: { detail: '开关已被更新，请刷新后重试' } } });
    renderPanel();
    const toggle = await screen.findByRole('switch', { name: '全站意图决策' });
    fireEvent.click(toggle);
    expect(await screen.findByRole('alert')).toHaveTextContent('开关已被更新，请刷新后重试');
    expect(toggle).toHaveAttribute('aria-checked', 'false');
  });

  it('does not allow enabling an unconfigured service', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { ...initial, configured: false } });
    renderPanel();
    expect(await screen.findByRole('switch', { name: '全站意图决策' })).toBeDisabled();
    expect(api.put).not.toHaveBeenCalled();
  });
});
