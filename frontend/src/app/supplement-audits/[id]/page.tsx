'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { supplementAuditApi } from '@/services/api/records';
import ProtectedRoute from '@/components/ProtectedRoute';
import { MarkdownContent } from '@/app/daily-insights/components/MarkdownContent';

interface AuditItem {
  id: number;
  audit_id: number;
  action_type: 'keep' | 'add' | 'upgrade' | 'remove' | 'monitor' | 'warning';
  priority: number;
  title: string;
  target_metric?: string;
  rationale_markdown: string;
  evidence_refs: any[];
  warnings: any[];
  status: 'pending' | 'accepted' | 'rejected' | 'completed' | 'superseded';
  user_note?: string;
  accepted_at?: string;
  completed_at?: string;
  rejected_reason?: string;
}

interface AuditDetail {
  id: number;
  version: number;
  title: string;
  status: string;
  triggered_by: string;
  summary?: string;
  data_period_start?: string;
  data_period_end?: string;
  next_review_at?: string;
  rationale_markdown: string;
  input_snapshot: any;
  items: AuditItem[];
}

const ACTION_CONFIG: Record<string, { label: string; color: string; icon: string }> = {
  keep: { label: '保持', color: 'bg-emerald-50 text-emerald-700 border-emerald-200', icon: '✓' },
  add: { label: '新增', color: 'bg-indigo-50 text-indigo-700 border-indigo-200', icon: '＋' },
  upgrade: { label: '调整', color: 'bg-amber-50 text-amber-700 border-amber-200', icon: '⟳' },
  remove: { label: '移除', color: 'bg-rose-50 text-rose-700 border-rose-200', icon: '−' },
  monitor: { label: '监测', color: 'bg-sky-50 text-sky-700 border-sky-200', icon: '🩺' },
  warning: { label: '警告', color: 'bg-red-50 text-red-700 border-red-200', icon: '⚠' },
};

const STATUS_BADGE: Record<string, string> = {
  pending: 'bg-gray-100 text-gray-600',
  accepted: 'bg-blue-100 text-blue-700',
  completed: 'bg-emerald-100 text-emerald-700',
  rejected: 'bg-rose-100 text-rose-700',
  superseded: 'bg-gray-200 text-gray-500',
};

const ACTION_ORDER = ['add', 'upgrade', 'remove', 'monitor', 'keep', 'warning'];

export default function SupplementAuditDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = Number(params?.id);
  const [audit, setAudit] = useState<AuditDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedItem, setExpandedItem] = useState<number | null>(null);
  const [showSnapshot, setShowSnapshot] = useState(false);

  const load = () => {
    setLoading(true);
    supplementAuditApi
      .getById(id)
      .then((res) => setAudit(res.data))
      .catch((err) => setError(err?.response?.data?.detail || err.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (id) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const updateItemStatus = async (itemId: number, status: string, extras: any = {}) => {
    try {
      await supplementAuditApi.updateItem(itemId, { status, ...extras });
      load();
    } catch (err: any) {
      alert('更新失败: ' + (err?.response?.data?.detail || err.message));
    }
  };

  if (loading) return <div className="p-6 text-sm text-gray-500">加载中…</div>;
  if (error) return <div className="p-6 text-sm text-red-600">加载失败: {error}</div>;
  if (!audit) return null;

  const groupedItems = ACTION_ORDER.reduce<Record<string, AuditItem[]>>((acc, at) => {
    acc[at] = (audit.items || []).filter((it) => it.action_type === at).sort((a, b) => a.priority - b.priority);
    return acc;
  }, {});

  return (
    <ProtectedRoute>
      <div className="max-w-3xl mx-auto px-4 py-6 pb-20">
        {/* header */}
        <div className="mb-4">
          <Link href="/supplement-audits" className="text-xs text-indigo-600 hover:underline">
            ← 返回审计列表
          </Link>
        </div>

        <div className="rounded-xl border border-gray-200 bg-white p-5 mb-4">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xs font-semibold text-gray-400">v{audit.version}</span>
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700">{audit.status}</span>
          </div>
          <h1 className="text-lg font-bold text-gray-900">{audit.title}</h1>
          {audit.summary && <p className="text-xs text-gray-600 mt-2">{audit.summary}</p>}
          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[10px] text-gray-500">
            <span>数据依据 {audit.data_period_start?.slice(0, 10)} → {audit.data_period_end?.slice(0, 10)}</span>
            {audit.next_review_at && <span>· 下次复查 {audit.next_review_at.slice(0, 10)}</span>}
          </div>
        </div>

        {/* 五段式 items */}
        {ACTION_ORDER.map((at) => {
          const items = groupedItems[at] || [];
          if (items.length === 0) return null;
          const cfg = ACTION_CONFIG[at];
          return (
            <div key={at} className="mb-4">
              <h2 className="text-xs font-semibold text-gray-700 mb-2 flex items-center gap-2">
                <span>{cfg.icon}</span>
                <span>{cfg.label}</span>
                <span className="text-gray-400">({items.length})</span>
              </h2>
              <div className="space-y-2">
                {items.map((it) => {
                  const isExpanded = expandedItem === it.id;
                  return (
                    <div
                      key={it.id}
                      className={`rounded-lg border p-3 ${cfg.color}`}
                    >
                      <button
                        className="w-full text-left flex items-start justify-between gap-3"
                        onClick={() => setExpandedItem(isExpanded ? null : it.id)}
                      >
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1 flex-wrap">
                            <span className="text-[10px] font-bold text-gray-500">P{it.priority}</span>
                            <span className={`text-[9px] px-1.5 py-0.5 rounded ${STATUS_BADGE[it.status]}`}>
                              {it.status}
                            </span>
                            {it.warnings?.length > 0 && (
                              <span className="text-[9px] text-rose-600">⚠ {it.warnings.length}</span>
                            )}
                          </div>
                          <div className="text-sm font-semibold text-gray-900">{it.title}</div>
                          {it.target_metric && (
                            <div className="text-[10px] text-gray-500 mt-0.5">📊 {it.target_metric}</div>
                          )}
                        </div>
                        <div className="shrink-0 text-xs text-gray-400">{isExpanded ? '▲' : '▼'}</div>
                      </button>

                      {isExpanded && (
                        <div className="mt-3 pt-3 border-t border-current/20 space-y-3">
                          <MarkdownContent content={it.rationale_markdown} />

                          {it.evidence_refs?.length > 0 && (
                            <div>
                              <div className="text-[10px] font-semibold text-gray-600 mb-1">证据引用 ({it.evidence_refs.length})</div>
                              <div className="flex flex-wrap gap-1">
                                {it.evidence_refs.map((e: any, idx: number) => (
                                  <span key={idx} className="text-[9px] px-1.5 py-0.5 rounded bg-white/60 text-gray-700">
                                    {e.type}:{e.id || e.name || e.value || e.condition || JSON.stringify(e).slice(0, 20)}
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}

                          {it.warnings?.length > 0 && (
                            <div>
                              <div className="text-[10px] font-semibold text-rose-700 mb-1">⚠ 注意事项</div>
                              <ul className="text-[10px] text-rose-700 space-y-0.5 list-disc list-inside">
                                {it.warnings.map((w: string, idx: number) => <li key={idx}>{w}</li>)}
                              </ul>
                            </div>
                          )}

                          {it.user_note && (
                            <div className="text-[10px] text-gray-600 italic">备注: {it.user_note}</div>
                          )}

                          {/* action buttons */}
                          {it.status === 'pending' && (
                            <div className="flex gap-2 pt-1">
                              <button
                                onClick={(e) => { e.stopPropagation(); updateItemStatus(it.id, 'accepted'); }}
                                className="text-[10px] px-2 py-1 rounded bg-white hover:bg-gray-50 border border-current/30"
                              >
                                接受
                              </button>
                              <button
                                onClick={(e) => { e.stopPropagation(); updateItemStatus(it.id, 'completed'); }}
                                className="text-[10px] px-2 py-1 rounded bg-white hover:bg-gray-50 border border-current/30"
                              >
                                已完成
                              </button>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  const reason = prompt('拒绝原因 (可选)');
                                  updateItemStatus(it.id, 'rejected', { rejected_reason: reason || '' });
                                }}
                                className="text-[10px] px-2 py-1 rounded bg-white hover:bg-gray-50 border border-current/30"
                              >
                                拒绝
                              </button>
                            </div>
                          )}
                          {it.status === 'accepted' && (
                            <button
                              onClick={(e) => { e.stopPropagation(); updateItemStatus(it.id, 'completed'); }}
                              className="text-[10px] px-2 py-1 rounded bg-white hover:bg-gray-50 border border-current/30"
                            >
                              标记为已完成
                            </button>
                          )}
                          {(it.status === 'completed' || it.status === 'rejected') && (
                            <button
                              onClick={(e) => { e.stopPropagation(); updateItemStatus(it.id, 'pending'); }}
                              className="text-[10px] px-2 py-1 rounded bg-white hover:bg-gray-50 border border-current/30"
                            >
                              重置为 pending
                            </button>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}

        {/* 完整推理 */}
        <div className="mt-6 rounded-xl border border-gray-200 bg-white p-4">
          <h2 className="text-sm font-semibold text-gray-800 mb-3">完整分析推理</h2>
          <MarkdownContent content={audit.rationale_markdown} />
        </div>

        {/* 输入快照 (折叠) */}
        <div className="mt-4 rounded-xl border border-gray-200 bg-white p-4">
          <button
            onClick={() => setShowSnapshot(!showSnapshot)}
            className="w-full text-left text-sm font-semibold text-gray-800 flex items-center justify-between"
          >
            <span>输入数据快照</span>
            <span className="text-xs text-gray-400">{showSnapshot ? '收起 ▲' : '展开 ▼'}</span>
          </button>
          {showSnapshot && (
            <pre className="mt-3 text-[9px] bg-gray-50 p-3 rounded overflow-x-auto text-gray-700">
              {JSON.stringify(audit.input_snapshot, null, 2)}
            </pre>
          )}
        </div>
      </div>
    </ProtectedRoute>
  );
}
