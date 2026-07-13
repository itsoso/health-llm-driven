// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { api } from '@/services/api/client';
import { DedaoReleaseReviewPanel } from '../DedaoReleaseReviewPanel';

vi.mock('@/services/api/client', () => ({
  api: {
    get: vi.fn(),
    patch: vi.fn(),
    post: vi.fn(),
  },
}));

const reviewData = {
  workspace_fingerprint: 'a'.repeat(64),
  total: 2,
  unresolved_count: 1,
  decision_counts: { approve: 1, unresolved: 1 },
  offset: 0,
  limit: 50,
  gate: { serving_allowed: false, blocking_reasons: ['draft artifacts require review'] },
  items: [
    {
      doc_id: 'claim:release-abc-claim-1',
      title: '咖啡因与睡眠窗口',
      summary: '晚间咖啡因可能延长睡眠潜伏期。',
      evidence_level: 'C',
      confidence: 0.68,
      sources: ['citation-1'],
      source_count: 1,
      review_status: 'draft',
      decision: null,
      release_id: 'release-abc',
      usage_policy: 'evidence_only',
      citation_ids: ['citation-1'],
    },
    {
      doc_id: 'claim:release-abc-claim-2',
      title: '晨间光照',
      summary: '晨间光照有助于稳定昼夜节律。',
      evidence_level: 'B',
      confidence: 0.8,
      sources: ['citation-2', 'guideline-1'],
      source_count: 2,
      review_status: 'reviewed',
      decision: 'approve',
      release_id: 'release-abc',
      usage_policy: 'evidence_only',
      citation_ids: ['citation-2'],
    },
  ],
};

function renderPanel() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <DedaoReleaseReviewPanel enabled />
    </QueryClientProvider>,
  );
}

describe('DedaoReleaseReviewPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.get).mockResolvedValue({ data: reviewData });
    vi.mocked(api.patch).mockResolvedValue({
      data: { decision: 'needs_evidence', workspace_fingerprint: 'b'.repeat(64) },
    });
    vi.mocked(api.post).mockResolvedValue({ data: { dry_run: true } });
  });

  it('selects release claims and shows their evidence context', async () => {
    renderPanel();

    expect(await screen.findByRole('button', { name: /晨间光照/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /晨间光照/ }));

    const details = screen.getByTestId('dedao-claim-detail');
    expect(within(details).getByText('晨间光照')).toBeInTheDocument();
    expect(within(details).getByText('2 个来源')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /发布到 serving/ })).not.toBeInTheDocument();
  });

  it('submits an explicit claim decision with the current fingerprint', async () => {
    renderPanel();
    await screen.findByRole('button', { name: /咖啡因与睡眠窗口/ });

    fireEvent.change(screen.getByLabelText('裁决说明'), { target: { value: '需要独立临床来源' } });
    fireEvent.click(screen.getByRole('button', { name: '待补证据' }));

    await waitFor(() => {
      expect(api.patch).toHaveBeenCalledWith(
        '/admin/knowledge/dedao_kbase/draft_review/items/claim%3Arelease-abc-claim-1',
        {
          workspace_fingerprint: 'a'.repeat(64),
          decision: 'needs_evidence',
          note: '需要独立临床来源',
        },
      );
    });
  });

  it('clears claim-specific evidence inputs when selecting another claim', async () => {
    renderPanel();
    await screen.findByRole('button', { name: /咖啡因与睡眠窗口/ });

    fireEvent.change(screen.getByLabelText('裁决说明'), { target: { value: '仅适用于第一条 claim' } });
    fireEvent.change(screen.getByLabelText('证据类型'), { target: { value: 'research' } });
    fireEvent.change(screen.getByLabelText('外部证据 ID'), { target: { value: 'pubmed:12345' } });
    fireEvent.change(screen.getByLabelText('证据标题'), { target: { value: 'First claim evidence' } });
    fireEvent.change(screen.getByLabelText('证据 URL'), { target: { value: 'https://example.test/evidence' } });

    fireEvent.click(screen.getByRole('button', { name: /晨间光照/ }));

    expect(screen.getByLabelText('裁决说明')).toHaveValue('');
    expect(screen.getByLabelText('证据类型')).toHaveValue('');
    expect(screen.getByLabelText('外部证据 ID')).toHaveValue('');
    expect(screen.getByLabelText('证据标题')).toHaveValue('');
    expect(screen.getByLabelText('证据 URL')).toHaveValue('');
  });

  it('keeps finalization disabled while claims are unresolved', async () => {
    renderPanel();
    await screen.findByRole('button', { name: /咖啡因与睡眠窗口/ });

    expect(screen.getByRole('button', { name: '最终确认 Release' })).toBeDisabled();
    expect(screen.getByText('仍有 1 条未决')).toBeInTheDocument();
  });

  it('keeps impact preview disabled until the review gate is finalized', async () => {
    vi.mocked(api.get).mockResolvedValue({
      data: {
        ...reviewData,
        unresolved_count: 0,
        decision_counts: { approve: 2 },
        items: reviewData.items.map((item) => ({
          ...item,
          review_status: 'reviewed',
          decision: 'approve',
        })),
      },
    });
    renderPanel();
    await screen.findByRole('button', { name: /咖啡因与睡眠窗口/ });

    expect(screen.getByRole('button', { name: '最终确认 Release' })).toBeEnabled();
    expect(screen.getByRole('button', { name: '影响预演' })).toBeDisabled();
  });

  it('surfaces stale fingerprint conflicts and offers a reload', async () => {
    vi.mocked(api.patch).mockRejectedValue({ response: { status: 409, data: { detail: 'reload before approval' } } });
    renderPanel();
    await screen.findByRole('button', { name: /咖啡因与睡眠窗口/ });

    fireEvent.click(screen.getByRole('button', { name: '拒绝' }));

    expect(await screen.findByText('工作区已更新，请重新加载后再裁决。')).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole('button', { name: '重新加载' }).at(-1)!);
    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2));
  });
});
