'use client';

import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { useRouter } from 'next/navigation';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Archive, CheckCircle2, Filter, RefreshCw, ShieldCheck } from 'lucide-react';

import { useAuth } from '@/contexts/AuthContext';
import { api } from '@/services/api/client';

import {
  buildClaimReviewPayload,
  ClaimReviewFormState,
  EvidenceLevel,
  reasonLabel,
  ReviewStatus,
} from './reviewHelpers';
import { CoverageMatrixView, CoverageMatrix } from './CoverageMatrixView';
import { KnowledgeGraphView, GraphData, GraphNode } from './KnowledgeGraphView';
import { BreakerStatus, ReconciliationQueueView, ReconQueueData, ReconScanResult } from './ReconciliationQueueView';
import { ProvenanceLineageView, KBDocPayload } from './ProvenanceLineageView';
import { DedaoReleaseReviewPanel } from './DedaoReleaseReviewPanel';

interface CoverageReportResponse {
  coverage_matrix?: CoverageMatrix;
}

interface ReviewQueueItem {
  doc_id: string;
  title: string | null;
  entity_type: string | null;
  entity_id: string | null;
  evidence_level: EvidenceLevel | null;
  confidence: number | null;
  review_status: string;
  reasons: string[];
  sources: string[];
  external_source_count: number;
  candidate_duplicates: string[];
  feedback_disagree_count: number;
  updated_at: string | null;
  created_at: string | null;
}

interface ReviewQueueResponse {
  summary: {
    total: number;
    returned: number;
    by_reason: Record<string, number>;
    by_review_status: Record<string, number>;
  };
  items: ReviewQueueItem[];
  filters: {
    reason: string | null;
    review_status: string | null;
    limit: number;
  };
  claim_boundary: string;
}

interface OperationsDashboard {
  status: 'ok' | 'attention';
  action_items: string[];
  coverage: {
    documents: {
      total: number;
      by_type: Record<string, number>;
      by_review_status: Record<string, number>;
      by_evidence_level: Record<string, number>;
    };
    external_evidence: {
      claim_total: number;
      claims_with_external_sources: number;
      external_source_rate: number;
      target_external_source_rate: number;
      meets_target: boolean;
      by_kind: Record<string, number>;
    };
    specialist_findings: {
      total: number;
      unsupported: number;
      evidence_ref_rate: number;
      target_evidence_ref_rate: number;
    };
    feedback: {
      disagree: number;
    };
  };
  lint: {
    summary: Record<string, number>;
  };
}

const emptyForm: ClaimReviewFormState = {
  reviewStatus: 'reviewed',
  evidenceLevel: '',
  confidence: '',
  sourceKind: 'research',
  source: '',
  sourceTitle: '',
  sourceUrl: '',
  clearCandidateDuplicates: false,
  resolveFeedback: false,
  note: '',
};

const reasonOptions = [
  { value: '', label: '全部原因' },
  { value: 'needs_review', label: '需要复核' },
  { value: 'draft', label: '草稿待审' },
  { value: 'missing_external_evidence', label: '缺少外部证据' },
  { value: 'candidate_duplicate', label: '候选重复' },
  { value: 'user_feedback', label: '用户反馈' },
];

const statusOptions: Array<{ value: ReviewStatus | ''; label: string }> = [
  { value: '', label: '全部状态' },
  { value: 'draft', label: 'draft' },
  { value: 'needs_review', label: 'needs_review' },
  { value: 'reviewed', label: 'reviewed' },
  { value: 'archived', label: 'archived' },
];

const evidenceOptions: Array<{ value: EvidenceLevel; label: string }> = [
  { value: '', label: '不修改' },
  { value: 'A', label: 'A - 指南/RCT/Meta' },
  { value: 'B', label: 'B - 人群/机制/二源' },
  { value: 'C', label: 'C - 课程/专家解释' },
  { value: 'D', label: 'D - 探索线索' },
];

export default function KnowledgeAdminPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { user, isAuthenticated, isLoading: authLoading } = useAuth();
  const [reason, setReason] = useState('');
  const [reviewStatus, setReviewStatus] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [form, setForm] = useState<ClaimReviewFormState>(emptyForm);
  const [seedInput, setSeedInput] = useState('');
  const [graphSeed, setGraphSeed] = useState('');
  const [graphNode, setGraphNode] = useState<GraphNode | null>(null);
  const [reconStatus, setReconStatus] = useState('open');
  const [reconKind, setReconKind] = useState('');
  const [reconShadow, setReconShadow] = useState(false);
  const [reconActionError, setReconActionError] = useState<string | null>(null);
  const [provInput, setProvInput] = useState('');
  const [provDocId, setProvDocId] = useState('');
  const [reconScanResult, setReconScanResult] = useState<ReconScanResult | undefined>(undefined);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login');
    } else if (!authLoading && isAuthenticated && !user?.is_admin) {
      router.push('/');
    }
  }, [authLoading, isAuthenticated, router, user]);

  const dashboardQuery = useQuery<OperationsDashboard>({
    queryKey: ['admin-knowledge-dashboard'],
    queryFn: async () => {
      const res = await api.get('/admin/knowledge/operations_dashboard');
      return res.data;
    },
    enabled: isAuthenticated && !!user?.is_admin,
  });

  const queueQuery = useQuery<ReviewQueueResponse>({
    queryKey: ['admin-knowledge-review-queue', reason, reviewStatus],
    queryFn: async () => {
      const params = new URLSearchParams({ limit: '200' });
      if (reason) params.set('reason', reason);
      if (reviewStatus) params.set('review_status', reviewStatus);
      const res = await api.get(`/admin/knowledge/review_queue?${params.toString()}`);
      return res.data;
    },
    enabled: isAuthenticated && !!user?.is_admin,
  });

  const coverageQuery = useQuery<CoverageReportResponse>({
    queryKey: ['admin-knowledge-coverage-report'],
    queryFn: async () => {
      const res = await api.get('/admin/knowledge/coverage_report');
      return res.data;
    },
    enabled: isAuthenticated && !!user?.is_admin,
  });

  const graphQuery = useQuery<GraphData>({
    queryKey: ['admin-knowledge-graph', graphSeed],
    queryFn: async () => {
      const res = await api.get(`/admin/knowledge/graph?seed=${encodeURIComponent(graphSeed)}&hops=2`);
      return res.data;
    },
    enabled: isAuthenticated && !!user?.is_admin && !!graphSeed,
  });

  const provQuery = useQuery<KBDocPayload>({
    queryKey: ['admin-knowledge-document', provDocId],
    queryFn: async () => {
      const res = await api.get(`/admin/knowledge/document/${encodeURIComponent(provDocId)}`);
      return res.data;
    },
    enabled: isAuthenticated && !!user?.is_admin && !!provDocId,
    retry: false, // 404 不重试(文档不存在直接显示)
  });

  const reconQuery = useQuery<ReconQueueData>({
    queryKey: ['admin-knowledge-reconciliation', reconStatus, reconKind, reconShadow],
    queryFn: async () => {
      const params = new URLSearchParams({ status: reconStatus, limit: '100' });
      if (reconKind) params.set('kind', reconKind);
      if (reconShadow) params.set('shadow_pending', 'true');
      const res = await api.get(`/admin/knowledge/reconciliation/candidates?${params.toString()}`);
      return res.data;
    },
    enabled: isAuthenticated && !!user?.is_admin,
  });

  const reconScanMutation = useMutation({
    mutationFn: async () => {
      const res = await api.post('/admin/knowledge/reconciliation/scan');
      return res.data as ReconScanResult;
    },
    onSuccess: (result) => {
      setReconScanResult(result);
      queryClient.invalidateQueries({ queryKey: ['admin-knowledge-reconciliation'] });
    },
  });

  const breakerQuery = useQuery<BreakerStatus>({
    queryKey: ['admin-knowledge-breaker'],
    queryFn: async () => {
      const res = await api.get('/admin/knowledge/reconciliation/breaker');
      return res.data;
    },
    enabled: isAuthenticated && !!user?.is_admin,
  });

  // P4/P6 裁决:approve_merge(serving mutation)/ reject / defer / confirm_shadow。
  // 400 = 服务端硬拒(conflict/处方/无锚/LIFO)—— 必须把 detail 亮给 reviewer,不吞。
  const reconActionMutation = useMutation({
    mutationFn: async ({ id, action }: { id: number; action: string }) => {
      const res = await api.patch(`/admin/knowledge/reconciliation/candidates/${id}`, { action });
      return res.data;
    },
    onSuccess: () => {
      setReconActionError(null);
      queryClient.invalidateQueries({ queryKey: ['admin-knowledge-reconciliation'] });
      queryClient.invalidateQueries({ queryKey: ['admin-knowledge-breaker'] });
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setReconActionError(detail || '操作失败');
    },
  });

  const reconUnalignMutation = useMutation({
    mutationFn: async (id: number) => {
      const res = await api.post(`/admin/knowledge/reconciliation/candidates/${id}/unalign`);
      return res.data;
    },
    onSuccess: () => {
      setReconActionError(null);
      queryClient.invalidateQueries({ queryKey: ['admin-knowledge-reconciliation'] });
      queryClient.invalidateQueries({ queryKey: ['admin-knowledge-breaker'] });
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setReconActionError(detail || '撤销失败');
    },
  });

  const breakerResetMutation = useMutation({
    mutationFn: async (note: string) => {
      const res = await api.post('/admin/knowledge/reconciliation/breaker/reset', { note });
      return res.data;
    },
    onSuccess: () => {
      setReconActionError(null);
      queryClient.invalidateQueries({ queryKey: ['admin-knowledge-breaker'] });
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setReconActionError(detail || '复位失败');
    },
  });

  const items = useMemo(() => queueQuery.data?.items ?? [], [queueQuery.data?.items]);
  const selectedItem = useMemo(() => {
    if (!items.length) return null;
    return items.find((item) => item.doc_id === selectedId) ?? items[0];
  }, [items, selectedId]);

  useEffect(() => {
    if (!selectedItem) {
      setSelectedId(null);
      return;
    }
    setSelectedId(selectedItem.doc_id);
    setForm((current) => ({
      ...current,
      reviewStatus: (selectedItem.review_status === 'unreviewed' ? 'reviewed' : selectedItem.review_status) as ReviewStatus,
      evidenceLevel: selectedItem.evidence_level ?? '',
      confidence: selectedItem.confidence == null ? '' : String(selectedItem.confidence),
      clearCandidateDuplicates: selectedItem.candidate_duplicates.length > 0,
      resolveFeedback: selectedItem.feedback_disagree_count > 0,
    }));
  }, [selectedItem]);

  const reviewMutation = useMutation({
    mutationFn: async ({ docId, payload }: { docId: string; payload: ReturnType<typeof buildClaimReviewPayload> }) => {
      const res = await api.patch(`/admin/knowledge/claim/${encodeURIComponent(docId)}/review`, payload);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-knowledge-review-queue'] });
      queryClient.invalidateQueries({ queryKey: ['admin-knowledge-dashboard'] });
    },
  });

  const updateForm = <K extends keyof ClaimReviewFormState>(key: K, value: ClaimReviewFormState[K]) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const submitReview = (statusOverride?: Exclude<ReviewStatus, ''>) => {
    if (!selectedItem || reviewMutation.isPending) return;
    const payload = buildClaimReviewPayload({
      ...form,
      reviewStatus: statusOverride ?? form.reviewStatus,
    });
    reviewMutation.mutate({ docId: selectedItem.doc_id, payload });
  };

  const reload = () => {
    queueQuery.refetch();
    dashboardQuery.refetch();
  };

  if (authLoading || !isAuthenticated || !user?.is_admin) {
    return (
      <main className="min-h-screen bg-[#0b1018] text-slate-100 flex items-center justify-center">
        <div className="text-sm text-slate-400">验证管理员权限中...</div>
      </main>
    );
  }

  const dashboard = dashboardQuery.data;
  const queue = queueQuery.data;
  const externalRate = dashboard?.coverage.external_evidence.external_source_rate ?? 0;
  const evidenceRefRate = dashboard?.coverage.specialist_findings.evidence_ref_rate ?? 0;

  return (
    <main className="min-h-screen bg-[#0b1018] text-slate-100">
      <div className="border-b border-slate-800 bg-[#111820]">
        <div className="mx-auto max-w-[1500px] px-6 py-5">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-4">
              <button
                type="button"
                onClick={() => router.push('/admin')}
                className="inline-flex items-center gap-2 rounded-md border border-slate-700 px-3 py-2 text-sm text-slate-300 hover:bg-slate-800"
              >
                <ArrowLeft className="h-4 w-4" />
                返回后台
              </button>
              <div>
                <div className="flex items-center gap-2 text-sm text-teal-300">
                  <ShieldCheck className="h-4 w-4" />
                  System KB Governance
                </div>
                <h1 className="mt-1 text-2xl font-semibold tracking-tight">知识库 Review Console</h1>
              </div>
            </div>
            <button
              type="button"
              onClick={reload}
              className="inline-flex items-center gap-2 rounded-md bg-teal-500 px-4 py-2 text-sm font-medium text-slate-950 hover:bg-teal-400 disabled:opacity-60"
              disabled={queueQuery.isFetching || dashboardQuery.isFetching}
            >
              <RefreshCw className={`h-4 w-4 ${queueQuery.isFetching || dashboardQuery.isFetching ? 'animate-spin' : ''}`} />
              刷新
            </button>
          </div>
        </div>
      </div>

      <div className="mx-auto max-w-[1500px] px-6 py-6">
        <section className="grid gap-3 md:grid-cols-4">
          <MetricCard label="队列待处理" value={queue?.summary.total ?? '-'} hint={`返回 ${queue?.summary.returned ?? 0} 条`} />
          <MetricCard label="外部证据覆盖" value={`${Math.round(externalRate * 100)}%`} hint={`目标 ${Math.round((dashboard?.coverage.external_evidence.target_external_source_rate ?? 0) * 100)}%`} />
          <MetricCard label="Advisor 证据引用" value={`${Math.round(evidenceRefRate * 100)}%`} hint={`unsupported ${dashboard?.coverage.specialist_findings.unsupported ?? 0}`} />
          <MetricCard label="Lint Issues" value={sumRecord(dashboard?.lint.summary)} hint={dashboard?.status === 'attention' ? '需要处理' : '正常'} />
        </section>

        {(dashboard?.action_items.length ?? 0) > 0 && (
          <section className="mt-4 rounded-lg border border-amber-500/30 bg-amber-500/10 p-4">
            <div className="text-sm font-semibold text-amber-200">运营动作</div>
            <div className="mt-2 flex flex-wrap gap-2">
              {dashboard?.action_items.map((item) => (
                <span key={item} className="rounded-full border border-amber-400/30 px-3 py-1 text-xs text-amber-100">
                  {item}
                </span>
              ))}
            </div>
          </section>
        )}

        <DedaoReleaseReviewPanel enabled={isAuthenticated && !!user?.is_admin} />

        {coverageQuery.data?.coverage_matrix && (
          <CoverageMatrixView data={coverageQuery.data.coverage_matrix} />
        )}

        <section className="mt-6 rounded-xl border border-slate-800 bg-[#111820]">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 p-4">
            <div>
              <h2 className="text-lg font-semibold">邻域图 · 实体关系</h2>
              <p className="mt-1 text-xs text-slate-400">
                种子文档 + hops≤2 邻域(纯 SVG,含 draft 节点供审;不喂 Twin)。粘贴 doc_id 画图。
              </p>
            </div>
            <div className="flex items-center gap-2">
              <input
                value={seedInput}
                onChange={(e) => setSeedInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') setGraphSeed(seedInput.trim());
                }}
                placeholder="种子 doc_id(如 entity:gene:CFTR)"
                className="w-72 rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none focus:border-teal-400"
              />
              <button
                type="button"
                onClick={() => setGraphSeed(seedInput.trim())}
                disabled={!seedInput.trim() || graphQuery.isFetching}
                className="rounded-md bg-teal-500 px-3 py-2 text-sm font-medium text-slate-950 hover:bg-teal-400 disabled:opacity-60"
              >
                画图
              </button>
            </div>
          </div>
          <div className="grid gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_280px]">
            <div>
              {!graphSeed && <div className="p-4 text-sm text-slate-500">粘贴一个 doc_id 开始。</div>}
              {graphSeed && graphQuery.isLoading && <div className="p-4 text-sm text-slate-400">加载中…</div>}
              {graphQuery.data && <KnowledgeGraphView data={graphQuery.data} onSelect={setGraphNode} />}
            </div>
            {graphNode && (
              <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3 text-sm">
                <div className="font-medium text-slate-200">{graphNode.title || graphNode.doc_id}</div>
                <div className="mt-2 space-y-1 text-xs text-slate-400">
                  <div>doc_id: <span className="text-slate-300">{graphNode.doc_id}</span></div>
                  <div>类型: <span className="text-slate-300">{graphNode.entity_type ?? '-'}</span></div>
                  <div>来源: <span className="text-slate-300">{graphNode.origin ?? '-'}</span></div>
                  <div>
                    审核:{' '}
                    <span className={graphNode.review_status === 'reviewed' ? 'text-emerald-300' : 'text-amber-300'}>
                      {graphNode.review_status ?? '-'}
                    </span>
                  </div>
                  <div>hop: <span className="text-slate-300">{graphNode.hop}</span></div>
                </div>
                <button
                  type="button"
                  onClick={() => setGraphSeed(graphNode.doc_id)}
                  className="mt-3 rounded-md border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:border-teal-400"
                >
                  以此为种子展开
                </button>
              </div>
            )}
          </div>
        </section>

        <ReconciliationQueueView
          data={reconQuery.data}
          loading={reconQuery.isLoading}
          onScan={() => reconScanMutation.mutate()}
          scanning={reconScanMutation.isPending}
          scanResult={reconScanResult}
          status={reconStatus}
          kind={reconKind}
          onStatusChange={setReconStatus}
          onKindChange={setReconKind}
          shadowOnly={reconShadow}
          onShadowOnlyChange={setReconShadow}
          breaker={breakerQuery.data}
          onBreakerReset={(note) => breakerResetMutation.mutate(note)}
          resettingBreaker={breakerResetMutation.isPending}
          onAction={(id, action) => reconActionMutation.mutate({ id, action })}
          onUnalign={(id) => reconUnalignMutation.mutate(id)}
          actionPending={reconActionMutation.isPending || reconUnalignMutation.isPending}
          actionError={reconActionError}
        />

        <ProvenanceLineageView
          data={provQuery.data}
          loading={provQuery.isFetching}
          docId={provDocId}
          input={provInput}
          onInputChange={setProvInput}
          onLookup={() => setProvDocId(provInput.trim())}
          notFound={provQuery.isError}
        />

        <section className="mt-6 grid gap-5 lg:grid-cols-[minmax(0,1fr)_420px]">
          <div className="rounded-xl border border-slate-800 bg-[#111820]">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 p-4">
              <div>
                <h2 className="text-lg font-semibold">Review Queue</h2>
                <p className="mt-1 text-xs text-slate-400">只展示 claim 级元数据，不暴露原始课程正文。</p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Filter className="h-4 w-4 text-slate-500" />
                <select
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                  className="rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none focus:border-teal-400"
                >
                  {reasonOptions.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
                <select
                  value={reviewStatus}
                  onChange={(event) => setReviewStatus(event.target.value)}
                  className="rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none focus:border-teal-400"
                >
                  {statusOptions.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="max-h-[820px] overflow-auto">
              {queueQuery.isLoading && <div className="p-8 text-center text-sm text-slate-400">加载 review queue...</div>}
              {queueQuery.isError && <div className="p-8 text-center text-sm text-red-300">加载失败，请检查管理员权限或服务状态。</div>}
              {!queueQuery.isLoading && !items.length && <div className="p-8 text-center text-sm text-slate-400">当前筛选下没有待处理 claim。</div>}
              {items.map((item) => (
                <button
                  key={item.doc_id}
                  type="button"
                  onClick={() => setSelectedId(item.doc_id)}
                  className={`block w-full border-b border-slate-800 p-4 text-left transition-colors hover:bg-slate-900 ${
                    selectedItem?.doc_id === item.doc_id ? 'bg-slate-900/90' : 'bg-transparent'
                  }`}
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="rounded bg-slate-800 px-2 py-0.5 text-[11px] text-slate-300">{item.review_status}</span>
                        {item.evidence_level && <span className="rounded bg-blue-500/15 px-2 py-0.5 text-[11px] text-blue-200">{item.evidence_level}级</span>}
                        <span className="text-[11px] text-slate-500">{item.entity_type}:{item.entity_id}</span>
                      </div>
                      <div className="mt-2 truncate text-sm font-medium text-slate-100">{item.title || item.doc_id}</div>
                      <div className="mt-1 truncate text-xs text-slate-500">{item.doc_id}</div>
                    </div>
                    <div className="shrink-0 text-right text-xs text-slate-400">
                      <div>conf {formatPercent(item.confidence)}</div>
                      <div className="mt-1">外证 {item.external_source_count}</div>
                    </div>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {item.reasons.map((itemReason) => (
                      <span key={itemReason} className="rounded-full bg-teal-500/10 px-2 py-0.5 text-[11px] text-teal-200">
                        {reasonLabel(itemReason)}
                      </span>
                    ))}
                  </div>
                </button>
              ))}
            </div>
          </div>

          <aside className="rounded-xl border border-slate-800 bg-[#111820] p-5">
            {!selectedItem ? (
              <div className="text-sm text-slate-400">选择一条 claim 后进行审核。</div>
            ) : (
              <div className="space-y-5">
                <div>
                  <div className="text-xs uppercase tracking-[0.18em] text-teal-300">Selected Claim</div>
                  <h2 className="mt-2 text-lg font-semibold leading-snug">{selectedItem.title || selectedItem.doc_id}</h2>
                  <p className="mt-2 break-all text-xs text-slate-500">{selectedItem.doc_id}</p>
                </div>

                <div className="grid grid-cols-2 gap-2 text-xs">
                  <InfoPill label="entity" value={`${selectedItem.entity_type}:${selectedItem.entity_id}`} />
                  <InfoPill label="feedback" value={`${selectedItem.feedback_disagree_count}`} />
                  <InfoPill label="duplicates" value={`${selectedItem.candidate_duplicates.length}`} />
                  <InfoPill label="sources" value={`${selectedItem.sources.length}`} />
                </div>

                <div className="space-y-3">
                  <Field label="Review Status">
                    <select
                      value={form.reviewStatus}
                      onChange={(event) => updateForm('reviewStatus', event.target.value as ReviewStatus)}
                      className="admin-kb-input"
                    >
                      <option value="reviewed">reviewed</option>
                      <option value="needs_review">needs_review</option>
                      <option value="draft">draft</option>
                      <option value="archived">archived</option>
                    </select>
                  </Field>
                  <Field label="Evidence Level">
                    <select
                      value={form.evidenceLevel}
                      onChange={(event) => updateForm('evidenceLevel', event.target.value as EvidenceLevel)}
                      className="admin-kb-input"
                    >
                      {evidenceOptions.map((option) => (
                        <option key={option.value} value={option.value}>{option.label}</option>
                      ))}
                    </select>
                  </Field>
                  <Field label="Confidence">
                    <input
                      value={form.confidence}
                      onChange={(event) => updateForm('confidence', event.target.value)}
                      className="admin-kb-input"
                      inputMode="decimal"
                      placeholder="0.00 - 1.00"
                    />
                  </Field>
                </div>

                <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
                  <div className="mb-3 text-sm font-medium text-slate-200">补充外部证据</div>
                  <div className="space-y-3">
                    <Field label="Kind">
                      <select
                        value={form.sourceKind}
                        onChange={(event) => updateForm('sourceKind', event.target.value)}
                        className="admin-kb-input"
                      >
                        <option value="research">research</option>
                        <option value="guideline">guideline</option>
                        <option value="database">database</option>
                        <option value="course">course</option>
                        <option value="book">book</option>
                        <option value="other">other</option>
                      </select>
                    </Field>
                    <Field label="Source ID">
                      <input
                        value={form.source}
                        onChange={(event) => updateForm('source', event.target.value)}
                        className="admin-kb-input"
                        placeholder="pubmed:19033271 / guideline:..."
                      />
                    </Field>
                    <Field label="Title">
                      <input
                        value={form.sourceTitle}
                        onChange={(event) => updateForm('sourceTitle', event.target.value)}
                        className="admin-kb-input"
                        placeholder="可选"
                      />
                    </Field>
                    <Field label="URL">
                      <input
                        value={form.sourceUrl}
                        onChange={(event) => updateForm('sourceUrl', event.target.value)}
                        className="admin-kb-input"
                        placeholder="https://..."
                      />
                    </Field>
                  </div>
                </div>

                <div className="space-y-2 text-sm text-slate-300">
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={form.clearCandidateDuplicates}
                      onChange={(event) => updateForm('clearCandidateDuplicates', event.target.checked)}
                    />
                    清除候选重复标记
                  </label>
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={form.resolveFeedback}
                      onChange={(event) => updateForm('resolveFeedback', event.target.checked)}
                    />
                    标记用户反馈已处理
                  </label>
                </div>

                <Field label="Review Note">
                  <textarea
                    value={form.note}
                    onChange={(event) => updateForm('note', event.target.value)}
                    className="admin-kb-input min-h-[92px] resize-y"
                    placeholder="记录判断依据，写入 kb_audit"
                  />
                </Field>

                {reviewMutation.isError && (
                  <div className="rounded-md border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-200">
                    保存失败：{extractErrorMessage(reviewMutation.error)}
                  </div>
                )}

                <div className="grid grid-cols-3 gap-2">
                  <button
                    type="button"
                    onClick={() => submitReview('reviewed')}
                    disabled={reviewMutation.isPending}
                    className="inline-flex items-center justify-center gap-2 rounded-md bg-teal-500 px-3 py-2 text-sm font-medium text-slate-950 hover:bg-teal-400 disabled:opacity-60"
                  >
                    <CheckCircle2 className="h-4 w-4" />
                    通过
                  </button>
                  <button
                    type="button"
                    onClick={() => submitReview('needs_review')}
                    disabled={reviewMutation.isPending}
                    className="rounded-md border border-amber-500/40 px-3 py-2 text-sm font-medium text-amber-100 hover:bg-amber-500/10 disabled:opacity-60"
                  >
                    复核
                  </button>
                  <button
                    type="button"
                    onClick={() => submitReview('archived')}
                    disabled={reviewMutation.isPending}
                    className="inline-flex items-center justify-center gap-2 rounded-md border border-red-500/40 px-3 py-2 text-sm font-medium text-red-200 hover:bg-red-500/10 disabled:opacity-60"
                  >
                    <Archive className="h-4 w-4" />
                    归档
                  </button>
                </div>

                <div className="rounded-md bg-slate-950/70 p-3 text-xs leading-relaxed text-slate-400">
                  {queue?.claim_boundary}
                </div>
              </div>
            )}
          </aside>
        </section>
      </div>
      <style jsx global>{`
        .admin-kb-input {
          width: 100%;
          border-radius: 0.375rem;
          border: 1px solid rgb(51 65 85);
          background: rgb(2 6 23);
          padding: 0.5rem 0.75rem;
          font-size: 0.875rem;
          color: rgb(226 232 240);
          outline: none;
        }
        .admin-kb-input:focus {
          border-color: rgb(45 212 191);
        }
      `}</style>
    </main>
  );
}

function MetricCard({ label, value, hint }: { label: string; value: string | number; hint: string }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-[#111820] p-4">
      <div className="text-xs uppercase tracking-[0.12em] text-slate-500">{label}</div>
      <div className="mt-2 text-2xl font-semibold text-slate-100">{value}</div>
      <div className="mt-1 text-xs text-slate-500">{hint}</div>
    </div>
  );
}

function InfoPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-slate-800 bg-slate-950/60 p-2">
      <div className="text-[10px] uppercase tracking-[0.12em] text-slate-500">{label}</div>
      <div className="mt-1 truncate text-xs text-slate-200">{value}</div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <div className="mb-1 text-xs font-medium text-slate-400">{label}</div>
      {children}
    </label>
  );
}

function formatPercent(value: number | null): string {
  if (value == null) return '-';
  return `${Math.round(value * 100)}%`;
}

function sumRecord(record?: Record<string, number>): number | string {
  if (!record) return '-';
  return Object.values(record).reduce((sum, value) => sum + value, 0);
}

function extractErrorMessage(error: unknown): string {
  if (typeof error === 'object' && error && 'response' in error) {
    const response = (error as { response?: { data?: { detail?: string } } }).response;
    return response?.data?.detail ?? '未知错误';
  }
  if (error instanceof Error) return error.message;
  return '未知错误';
}
