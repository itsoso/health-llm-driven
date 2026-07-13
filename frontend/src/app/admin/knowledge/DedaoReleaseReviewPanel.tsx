'use client';

import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Ban,
  CheckCircle2,
  FileCheck2,
  FlaskConical,
  RefreshCw,
  ShieldAlert,
  XCircle,
} from 'lucide-react';

import { api } from '@/services/api/client';

import {
  buildAdjudicationPayload,
  canFinalizeReleaseReview,
  decisionLabel,
  DedaoClaimDecision,
  isStaleWorkspaceError,
} from './dedaoReleaseReview';

interface ReleaseClaim {
  doc_id: string;
  title: string;
  summary: string;
  evidence_level: 'A' | 'B' | 'C' | 'D' | null;
  confidence: number | null;
  sources: string[];
  source_count: number;
  review_status: string;
  decision: DedaoClaimDecision | null;
  release_id: string | null;
  usage_policy: string | null;
  citation_ids: string[];
}

interface ReviewResponse {
  workspace_fingerprint: string;
  total: number;
  unresolved_count: number;
  decision_counts: Record<string, number>;
  offset: number;
  limit: number;
  items: ReleaseClaim[];
}

interface DedaoReleaseReviewPanelProps {
  enabled: boolean;
}

const PAGE_SIZE = 50;

export function DedaoReleaseReviewPanel({ enabled }: DedaoReleaseReviewPanelProps) {
  const queryClient = useQueryClient();
  const [offset, setOffset] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [note, setNote] = useState('');
  const [evidenceLevel, setEvidenceLevel] = useState<'' | 'A' | 'B' | 'C' | 'D'>('');
  const [confidence, setConfidence] = useState('');
  const [evidenceKind, setEvidenceKind] = useState('');
  const [evidenceSource, setEvidenceSource] = useState('');
  const [evidenceTitle, setEvidenceTitle] = useState('');
  const [evidenceUrl, setEvidenceUrl] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<Record<string, unknown> | null>(null);

  const reviewQuery = useQuery<ReviewResponse>({
    queryKey: ['dedao-kbase-release-review', offset],
    queryFn: async () => {
      const response = await api.get(
        `/admin/knowledge/dedao_kbase/draft_review/items?offset=${offset}&limit=${PAGE_SIZE}`,
      );
      return response.data;
    },
    enabled,
    retry: false,
  });

  const selected = useMemo(() => {
    const items = reviewQuery.data?.items ?? [];
    return items.find((item) => item.doc_id === selectedId) ?? items[0] ?? null;
  }, [reviewQuery.data?.items, selectedId]);

  useEffect(() => {
    if (!selected) {
      setSelectedId(null);
      return;
    }
    setSelectedId(selected.doc_id);
    setEvidenceLevel(selected.evidence_level ?? '');
    setConfidence(selected.confidence == null ? '' : String(selected.confidence));
    setNote('');
    setEvidenceKind('');
    setEvidenceSource('');
    setEvidenceTitle('');
    setEvidenceUrl('');
  }, [selected]);

  const refreshReview = async () => {
    setError(null);
    setPreview(null);
    await reviewQuery.refetch();
  };

  const adjudicationMutation = useMutation({
    mutationFn: async (decision: DedaoClaimDecision) => {
      if (!selected || !reviewQuery.data) throw new Error('未选择 claim');
      const payload = buildAdjudicationPayload({
        workspaceFingerprint: reviewQuery.data.workspace_fingerprint,
        decision,
        note,
        evidenceLevel,
        confidence,
        evidenceKind,
        evidenceSource,
        evidenceTitle,
        evidenceUrl,
      });
      const response = await api.patch(
        `/admin/knowledge/dedao_kbase/draft_review/items/${encodeURIComponent(selected.doc_id)}`,
        payload,
      );
      return response.data;
    },
    onSuccess: async () => {
      setError(null);
      setNote('');
      setEvidenceKind('');
      setEvidenceSource('');
      setEvidenceTitle('');
      setEvidenceUrl('');
      await queryClient.invalidateQueries({ queryKey: ['dedao-kbase-release-review'] });
    },
    onError: (mutationError: unknown) => {
      if (isStaleWorkspaceError(mutationError)) {
        setError('工作区已更新，请重新加载后再裁决。');
        return;
      }
      const detail = (mutationError as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail || '裁决失败，请检查输入后重试。');
    },
  });

  const finalizeMutation = useMutation({
    mutationFn: async () => {
      if (!reviewQuery.data) throw new Error('审核工作区未加载');
      const response = await api.post('/admin/knowledge/dedao_kbase/draft_review/finalize', {
        workspace_fingerprint: reviewQuery.data.workspace_fingerprint,
        note: note.trim() || undefined,
      });
      return response.data;
    },
    onSuccess: async () => {
      setError(null);
      await queryClient.invalidateQueries({ queryKey: ['dedao-kbase-release-review'] });
    },
    onError: (mutationError: unknown) => {
      if (isStaleWorkspaceError(mutationError)) {
        setError('工作区已更新，请重新加载后再最终确认。');
        return;
      }
      const detail = (mutationError as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail || '最终确认失败。');
    },
  });

  const previewMutation = useMutation({
    mutationFn: async () => {
      const response = await api.post('/admin/knowledge/dedao_kbase/reviewed_artifacts/publish/preview', {
        note: 'admin console impact preview',
      });
      return response.data as Record<string, unknown>;
    },
    onSuccess: (result) => {
      setError(null);
      setPreview(result);
    },
    onError: (mutationError: unknown) => {
      const detail = (mutationError as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail || '影响预演失败。');
    },
  });

  if (!enabled) return null;

  const data = reviewQuery.data;
  const canFinalize = data
    ? canFinalizeReleaseReview({ total: data.total, unresolvedCount: data.unresolved_count })
    : false;
  const isMutating = adjudicationMutation.isPending || finalizeMutation.isPending || previewMutation.isPending;

  return (
    <section className="mt-6 overflow-hidden rounded-lg border border-slate-800 bg-[#111820]">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 px-4 py-3">
        <div>
          <div className="flex items-center gap-2 text-xs font-medium uppercase text-teal-300">
            <FileCheck2 className="h-4 w-4" />
            Dedao KBase Review
          </div>
          <h2 className="mt-1 text-lg font-semibold">Release Claims</h2>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="rounded border border-slate-700 px-2 py-1 text-slate-300">
            {data?.total ?? 0} 条
          </span>
          <span className="rounded border border-amber-500/40 bg-amber-500/10 px-2 py-1 text-amber-200">
            仍有 {data?.unresolved_count ?? 0} 条未决
          </span>
          <code className="hidden max-w-44 truncate text-slate-500 xl:block">
            {data?.workspace_fingerprint ?? 'workspace loading'}
          </code>
          <button
            type="button"
            onClick={refreshReview}
            disabled={reviewQuery.isFetching}
            className="inline-flex h-8 w-8 items-center justify-center rounded border border-slate-700 text-slate-300 hover:bg-slate-800 disabled:opacity-50"
            title="重新加载"
            aria-label="重新加载"
          >
            <RefreshCw className={`h-4 w-4 ${reviewQuery.isFetching ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </header>

      {error && (
        <div className="flex items-center justify-between gap-3 border-b border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
          <span className="flex items-center gap-2"><ShieldAlert className="h-4 w-4" />{error}</span>
          {error.includes('重新加载') && (
            <button type="button" onClick={refreshReview} className="rounded border border-rose-400/40 px-3 py-1 hover:bg-rose-500/10">
              重新加载
            </button>
          )}
        </div>
      )}

      <div className="grid min-h-[430px] lg:grid-cols-[minmax(260px,0.38fr)_minmax(0,1fr)]">
        <div className="border-b border-slate-800 lg:border-b-0 lg:border-r">
          {reviewQuery.isLoading && <div className="p-4 text-sm text-slate-500">加载 Release claims...</div>}
          {reviewQuery.isError && <div className="p-4 text-sm text-rose-300">无法读取审核工作区。</div>}
          {!reviewQuery.isLoading && data?.items.length === 0 && (
            <div className="p-4 text-sm text-slate-500">当前页没有 Release claim。</div>
          )}
          <div className="max-h-[520px] overflow-y-auto">
            {data?.items.map((item) => {
              const active = item.doc_id === selected?.doc_id;
              return (
                <button
                  key={item.doc_id}
                  type="button"
                  onClick={() => setSelectedId(item.doc_id)}
                  className={`block w-full border-b border-slate-800 px-4 py-3 text-left transition-colors ${
                    active ? 'bg-teal-500/10' : 'hover:bg-slate-900/50'
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <span className="line-clamp-2 text-sm font-medium text-slate-100">{item.title}</span>
                    <span className={`shrink-0 text-[11px] ${item.review_status === 'draft' ? 'text-amber-300' : 'text-emerald-300'}`}>
                      {item.decision ? decisionLabel(item.decision) : '未决'}
                    </span>
                  </div>
                  <div className="mt-2 flex gap-3 text-[11px] text-slate-500">
                    <span>{item.evidence_level ?? '-'}</span>
                    <span>{Math.round((item.confidence ?? 0) * 100)}%</span>
                    <span>{item.source_count} 源</span>
                  </div>
                </button>
              );
            })}
          </div>
          <div className="flex items-center justify-between gap-2 border-t border-slate-800 p-3 text-xs text-slate-400">
            <button
              type="button"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              className="rounded border border-slate-700 px-2 py-1 disabled:opacity-40"
            >
              上一页
            </button>
            <span>{Math.floor(offset / PAGE_SIZE) + 1} / {Math.max(1, Math.ceil((data?.total ?? 0) / PAGE_SIZE))}</span>
            <button
              type="button"
              disabled={!data || offset + PAGE_SIZE >= data.total}
              onClick={() => setOffset(offset + PAGE_SIZE)}
              className="rounded border border-slate-700 px-2 py-1 disabled:opacity-40"
            >
              下一页
            </button>
          </div>
        </div>

        <div className="p-4" data-testid="dedao-claim-detail">
          {!selected && <div className="text-sm text-slate-500">选择一条 claim 开始审核。</div>}
          {selected && (
            <div className="space-y-4">
              <div>
                <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
                  <span>{selected.release_id}</span>
                  <span>{selected.usage_policy}</span>
                  <span>{selected.source_count} 个来源</span>
                </div>
                <h3 className="mt-2 text-xl font-semibold text-slate-100">{selected.title}</h3>
                <p className="mt-2 max-w-4xl text-sm leading-6 text-slate-300">{selected.summary}</p>
              </div>

              <div className="grid gap-3 sm:grid-cols-3">
                <label className="text-xs text-slate-400">
                  证据等级
                  <select value={evidenceLevel} onChange={(event) => setEvidenceLevel(event.target.value as typeof evidenceLevel)} className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200">
                    <option value="">不修改</option><option value="A">A</option><option value="B">B</option><option value="C">C</option><option value="D">D</option>
                  </select>
                </label>
                <label className="text-xs text-slate-400">
                  置信度
                  <input value={confidence} onChange={(event) => setConfidence(event.target.value)} inputMode="decimal" className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200" />
                </label>
                <label className="text-xs text-slate-400">
                  证据类型
                  <input value={evidenceKind} onChange={(event) => setEvidenceKind(event.target.value)} placeholder="guideline / research" className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200" />
                </label>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <label className="text-xs text-slate-400">外部证据 ID<input value={evidenceSource} onChange={(event) => setEvidenceSource(event.target.value)} placeholder="pubmed:12345" className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200" /></label>
                <label className="text-xs text-slate-400">证据标题<input value={evidenceTitle} onChange={(event) => setEvidenceTitle(event.target.value)} className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200" /></label>
              </div>
              <label className="block text-xs text-slate-400">证据 URL<input value={evidenceUrl} onChange={(event) => setEvidenceUrl(event.target.value)} type="url" className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200" /></label>
              <label className="block text-xs text-slate-400">
                裁决说明
                <textarea value={note} onChange={(event) => setNote(event.target.value)} rows={3} className="mt-1 w-full resize-y rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200" />
              </label>

              <div className="flex flex-wrap gap-2">
                <DecisionButton label="批准" icon={<CheckCircle2 className="h-4 w-4" />} tone="emerald" disabled={isMutating} onClick={() => adjudicationMutation.mutate('approve')} />
                <DecisionButton label="待补证据" icon={<FlaskConical className="h-4 w-4" />} tone="amber" disabled={isMutating} onClick={() => adjudicationMutation.mutate('needs_evidence')} />
                <DecisionButton label="拒绝" icon={<XCircle className="h-4 w-4" />} tone="rose" disabled={isMutating} onClick={() => adjudicationMutation.mutate('reject')} />
                <DecisionButton label="仅作背景" icon={<Ban className="h-4 w-4" />} tone="slate" disabled={isMutating} onClick={() => adjudicationMutation.mutate('background_only')} />
              </div>
            </div>
          )}
        </div>
      </div>

      <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-800 px-4 py-3">
        <span className="text-xs text-slate-500">最终确认只打开审核门，不写入 serving。</span>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => previewMutation.mutate()}
            disabled={!canFinalize || isMutating}
            className="rounded border border-slate-700 px-3 py-2 text-sm text-slate-200 hover:bg-slate-800 disabled:opacity-40"
          >
            影响预演
          </button>
          <button
            type="button"
            onClick={() => finalizeMutation.mutate()}
            disabled={!canFinalize || isMutating}
            className="rounded bg-teal-500 px-4 py-2 text-sm font-medium text-slate-950 hover:bg-teal-400 disabled:opacity-40"
          >
            最终确认 Release
          </button>
        </div>
        {preview && <span className="basis-full text-xs text-teal-300">影响预演已完成，未修改 serving 数据。</span>}
      </footer>
    </section>
  );
}

function DecisionButton({
  label,
  icon,
  tone,
  disabled,
  onClick,
}: {
  label: string;
  icon: ReactNode;
  tone: 'emerald' | 'amber' | 'rose' | 'slate';
  disabled: boolean;
  onClick: () => void;
}) {
  const tones = {
    emerald: 'border-emerald-500/40 text-emerald-200 hover:bg-emerald-500/10',
    amber: 'border-amber-500/40 text-amber-200 hover:bg-amber-500/10',
    rose: 'border-rose-500/40 text-rose-200 hover:bg-rose-500/10',
    slate: 'border-slate-700 text-slate-300 hover:bg-slate-800',
  };
  return <button type="button" onClick={onClick} disabled={disabled} className={`inline-flex items-center gap-2 rounded border px-3 py-2 text-sm disabled:opacity-40 ${tones[tone]}`}>{icon}{label}</button>;
}
