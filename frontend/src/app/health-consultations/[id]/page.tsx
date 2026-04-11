'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { healthConsultationApi } from '@/services/api/records';
import ProtectedRoute from '@/components/ProtectedRoute';
import { MarkdownContent } from '@/app/daily-insights/components/MarkdownContent';

type ItemType = 'hypothesis' | 'action' | 'prediction' | 'red_flag' | 'note';

interface ConsultItem {
  id: number;
  consultation_id: number;
  item_type: ItemType;
  item_code?: string;
  priority: number;
  title: string;
  content_markdown?: string;
  meta: any;
  status: string;
  due_date?: string;
  user_note?: string;
  outcome?: string;
  actual_value?: string;
  verified_at?: string;
  completed_at?: string;
}

interface ConsultDetail {
  id: number;
  version: number;
  title: string;
  topic?: string;
  consultation_type: string;
  triggered_by: string;
  chief_complaint?: string;
  status: string;
  summary?: string;
  rationale_markdown: string;
  input_snapshot: any;
  verification_scheduled_at?: string;
  verified_at?: string;
  created_at?: string;
  items: ConsultItem[];
}

interface VerifyResult {
  item_id: number;
  item_code?: string;
  title: string;
  metric_name?: string;
  target: string;
  baseline?: any;
  actual_value: any;
  note: string;
  suggested_status: string;
  data_source: string;
}

const TYPE_CONFIG: Record<string, { label: string; color: string; icon: string; order: number }> = {
  hypothesis: { label: '假设', color: 'bg-purple-50 text-purple-700 border-purple-200', icon: '🧠', order: 1 },
  action: { label: '行动', color: 'bg-blue-50 text-blue-700 border-blue-200', icon: '✓', order: 2 },
  prediction: { label: '可检验预测', color: 'bg-green-50 text-green-700 border-green-200', icon: '📊', order: 3 },
  red_flag: { label: '警戒信号', color: 'bg-rose-50 text-rose-700 border-rose-200', icon: '⚠', order: 4 },
  note: { label: '备注', color: 'bg-gray-50 text-gray-700 border-gray-200', icon: '📝', order: 5 },
};

// 不同 item_type 允许的状态
const STATUS_OPTIONS: Record<ItemType, { value: string; label: string }[]> = {
  hypothesis: [
    { value: 'pending', label: '待验证' },
    { value: 'confirmed', label: '已证实' },
    { value: 'refuted', label: '已否决' },
    { value: 'inconclusive', label: '不能定论' },
  ],
  action: [
    { value: 'pending', label: '待办' },
    { value: 'in_progress', label: '进行中' },
    { value: 'completed', label: '已完成' },
    { value: 'skipped', label: '跳过' },
    { value: 'deferred', label: '延期' },
  ],
  prediction: [
    { value: 'pending', label: '待检验' },
    { value: 'met', label: '达成' },
    { value: 'not_met', label: '未达成' },
    { value: 'partial', label: '部分达成' },
    { value: 'inconclusive', label: '数据不足' },
  ],
  red_flag: [
    { value: 'watching', label: '监视中' },
    { value: 'triggered', label: '已触发' },
    { value: 'resolved', label: '已解除' },
  ],
  note: [
    { value: 'pending', label: '待处理' },
    { value: 'resolved', label: '已解决' },
  ],
};

const STATUS_BADGE: Record<string, string> = {
  pending: 'bg-gray-100 text-gray-600',
  in_progress: 'bg-blue-100 text-blue-700',
  completed: 'bg-emerald-100 text-emerald-700',
  confirmed: 'bg-emerald-100 text-emerald-700',
  refuted: 'bg-rose-100 text-rose-700',
  inconclusive: 'bg-yellow-100 text-yellow-700',
  met: 'bg-emerald-100 text-emerald-700',
  not_met: 'bg-rose-100 text-rose-700',
  partial: 'bg-yellow-100 text-yellow-700',
  watching: 'bg-amber-100 text-amber-700',
  triggered: 'bg-rose-100 text-rose-700',
  resolved: 'bg-emerald-100 text-emerald-700',
  skipped: 'bg-gray-100 text-gray-500',
  deferred: 'bg-gray-100 text-gray-500',
};

export default function ConsultationDetailPage() {
  const params = useParams();
  const id = Number(params?.id);
  const [c, setC] = useState<ConsultDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedItem, setExpandedItem] = useState<number | null>(null);
  const [showSnapshot, setShowSnapshot] = useState(false);
  const [showFullMarkdown, setShowFullMarkdown] = useState(false);
  const [verifyResults, setVerifyResults] = useState<VerifyResult[] | null>(null);
  const [verifying, setVerifying] = useState(false);

  const load = () => {
    setLoading(true);
    healthConsultationApi
      .getById(id)
      .then((res) => setC(res.data))
      .catch((err) => setError(err?.response?.data?.detail || err.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (id) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const updateItem = async (itemId: number, patch: any) => {
    try {
      await healthConsultationApi.updateItem(itemId, patch);
      load();
    } catch (err: any) {
      alert('更新失败: ' + (err?.response?.data?.detail || err.message));
    }
  };

  const runVerify = async () => {
    if (!c) return;
    setVerifying(true);
    try {
      const res = await healthConsultationApi.verifyPredictions(c.id);
      setVerifyResults(res.data);
    } catch (err: any) {
      alert('回测失败: ' + (err?.response?.data?.detail || err.message));
    } finally {
      setVerifying(false);
    }
  };

  if (loading) return <div className="p-6 text-sm text-gray-500">加载中…</div>;
  if (error) return <div className="p-6 text-sm text-red-600">加载失败: {error}</div>;
  if (!c) return null;

  const grouped: Record<string, ConsultItem[]> = {};
  for (const it of c.items) {
    if (!grouped[it.item_type]) grouped[it.item_type] = [];
    grouped[it.item_type].push(it);
  }
  for (const k of Object.keys(grouped)) {
    grouped[k].sort((a, b) => a.priority - b.priority);
  }
  const orderedTypes = Object.keys(grouped).sort(
    (a, b) => (TYPE_CONFIG[a]?.order || 99) - (TYPE_CONFIG[b]?.order || 99)
  );

  const predictionCount = (grouped.prediction || []).length;

  return (
    <ProtectedRoute>
      <div className="max-w-3xl mx-auto px-4 py-6 pb-20">
        <div className="mb-4">
          <Link href="/health-consultations" className="text-xs text-indigo-600 hover:underline">
            ← 返回咨询列表
          </Link>
        </div>

        {/* header */}
        <div className="rounded-xl border border-gray-200 bg-white p-5 mb-4">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xs font-semibold text-gray-400">v{c.version}</span>
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700">{c.status}</span>
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700">
              {c.consultation_type}
            </span>
          </div>
          <h1 className="text-lg font-bold text-gray-900">{c.title}</h1>
          {c.topic && <p className="text-xs text-gray-500 mt-1">🏷 {c.topic}</p>}
          {c.chief_complaint && (
            <p className="text-xs text-gray-700 mt-2 italic border-l-2 border-gray-300 pl-2">
              主诉: {c.chief_complaint}
            </p>
          )}
          {c.summary && <p className="text-xs text-gray-600 mt-2">{c.summary}</p>}
          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[10px] text-gray-500">
            <span>创建于 {c.created_at?.slice(0, 10)}</span>
            {c.verification_scheduled_at && <span>· 计划复盘 {c.verification_scheduled_at.slice(0, 10)}</span>}
          </div>

          {/* 自动回测按钮 */}
          {predictionCount > 0 && (
            <div className="mt-4 pt-4 border-t border-gray-100">
              <button
                onClick={runVerify}
                disabled={verifying}
                className="text-xs px-3 py-1.5 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:bg-gray-300 transition"
              >
                {verifying ? '回测中…' : `🔍 自动回测 ${predictionCount} 条预测`}
              </button>
              <p className="text-[10px] text-gray-500 mt-1">
                对比 Garmin 和体检数据的实际值 → 给出每条预测的 met/not_met 建议
              </p>
            </div>
          )}
        </div>

        {/* verify results */}
        {verifyResults && verifyResults.length > 0 && (
          <div className="mb-4 rounded-xl border border-indigo-200 bg-indigo-50/50 p-4">
            <h3 className="text-sm font-semibold text-indigo-900 mb-2">🔍 回测结果</h3>
            <div className="space-y-2">
              {verifyResults.map((r) => (
                <div key={r.item_id} className="text-xs bg-white rounded p-2">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold">{r.item_code} {r.title}</span>
                    <span className={`text-[10px] px-2 py-0.5 rounded ${STATUS_BADGE[r.suggested_status] || 'bg-gray-100'}`}>
                      {r.suggested_status}
                    </span>
                  </div>
                  <div className="text-[10px] text-gray-600 mt-1">
                    基线 {String(r.baseline ?? '—')} / 目标 {r.target} / 实际{' '}
                    <strong>{r.actual_value !== null ? String(r.actual_value) : '无数据'}</strong>
                  </div>
                  <div className="text-[10px] text-gray-500 mt-0.5 italic">{r.note}</div>
                  {r.actual_value !== null && r.suggested_status !== 'pending' && (
                    <button
                      onClick={() =>
                        updateItem(r.item_id, {
                          status: r.suggested_status,
                          actual_value: String(r.actual_value),
                          outcome: r.note,
                        })
                      }
                      className="mt-1 text-[10px] text-indigo-600 hover:underline"
                    >
                      确认并应用此建议
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* items grouped by type */}
        {orderedTypes.map((type) => {
          const items = grouped[type];
          const cfg = TYPE_CONFIG[type];
          return (
            <div key={type} className="mb-4">
              <h2 className="text-xs font-semibold text-gray-700 mb-2 flex items-center gap-2">
                <span>{cfg.icon}</span>
                <span>{cfg.label}</span>
                <span className="text-gray-400">({items.length})</span>
              </h2>
              <div className="space-y-2">
                {items.map((it) => {
                  const isExpanded = expandedItem === it.id;
                  const opts = STATUS_OPTIONS[it.item_type] || [];
                  return (
                    <div key={it.id} className={`rounded-lg border p-3 ${cfg.color}`}>
                      <button
                        className="w-full text-left flex items-start justify-between gap-3"
                        onClick={() => setExpandedItem(isExpanded ? null : it.id)}
                      >
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1 flex-wrap">
                            {it.item_code && (
                              <span className="text-[10px] font-bold text-gray-500">{it.item_code}</span>
                            )}
                            <span className="text-[10px] font-bold text-gray-500">P{it.priority}</span>
                            <span className={`text-[9px] px-1.5 py-0.5 rounded ${STATUS_BADGE[it.status] || 'bg-gray-100'}`}>
                              {it.status}
                            </span>
                            {it.due_date && (
                              <span className="text-[9px] text-gray-500">
                                📅 {it.due_date.slice(0, 10)}
                              </span>
                            )}
                          </div>
                          <div className="text-sm font-semibold text-gray-900">{it.title}</div>
                          {/* prediction 特有的快照 */}
                          {it.item_type === 'prediction' && it.meta?.metric_display && (
                            <div className="text-[10px] text-gray-500 mt-0.5">
                              📊 {it.meta.metric_display}: 基线 {String(it.meta.baseline ?? '—')} → 目标{' '}
                              {it.meta.target}
                            </div>
                          )}
                        </div>
                        <div className="shrink-0 text-xs text-gray-400">{isExpanded ? '▲' : '▼'}</div>
                      </button>

                      {isExpanded && (
                        <div className="mt-3 pt-3 border-t border-current/20 space-y-3">
                          {it.content_markdown && <MarkdownContent content={it.content_markdown} />}

                          {/* meta 展示 (每个 type 不同) */}
                          {it.meta && Object.keys(it.meta).length > 0 && (
                            <div>
                              <div className="text-[10px] font-semibold text-gray-600 mb-1">结构化数据</div>
                              <pre className="text-[9px] bg-white/60 p-2 rounded overflow-x-auto text-gray-700">
                                {JSON.stringify(it.meta, null, 2)}
                              </pre>
                            </div>
                          )}

                          {/* outcome / actual_value / user_note 展示 */}
                          {it.actual_value && (
                            <div className="text-[10px]">
                              <span className="font-semibold text-gray-600">实际值：</span>
                              <span className="text-gray-800">{it.actual_value}</span>
                            </div>
                          )}
                          {it.outcome && (
                            <div className="text-[10px]">
                              <span className="font-semibold text-gray-600">结果：</span>
                              <span className="text-gray-800">{it.outcome}</span>
                            </div>
                          )}
                          {it.user_note && (
                            <div className="text-[10px] text-gray-600 italic">备注: {it.user_note}</div>
                          )}

                          {/* 状态切换按钮 */}
                          <div className="flex gap-1 pt-1 flex-wrap">
                            {opts
                              .filter((o) => o.value !== it.status)
                              .map((o) => (
                                <button
                                  key={o.value}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    updateItem(it.id, { status: o.value });
                                  }}
                                  className="text-[10px] px-2 py-1 rounded bg-white hover:bg-gray-50 border border-current/30"
                                >
                                  → {o.label}
                                </button>
                              ))}
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}

        {/* 完整 markdown */}
        <div className="mt-6 rounded-xl border border-gray-200 bg-white p-4">
          <button
            onClick={() => setShowFullMarkdown(!showFullMarkdown)}
            className="w-full text-left text-sm font-semibold text-gray-800 flex items-center justify-between"
          >
            <span>完整分析推理</span>
            <span className="text-xs text-gray-400">{showFullMarkdown ? '收起 ▲' : '展开 ▼'}</span>
          </button>
          {showFullMarkdown && (
            <div className="mt-3 pt-3 border-t border-gray-100">
              <MarkdownContent content={c.rationale_markdown} />
            </div>
          )}
        </div>

        {/* 输入快照 */}
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
              {JSON.stringify(c.input_snapshot, null, 2)}
            </pre>
          )}
        </div>
      </div>
    </ProtectedRoute>
  );
}
