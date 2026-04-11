'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { supplementAuditApi } from '@/services/api/records';
import ProtectedRoute from '@/components/ProtectedRoute';

interface AuditListItem {
  id: number;
  version: number;
  title: string;
  status: string;
  triggered_by: string;
  summary?: string;
  data_period_start?: string;
  data_period_end?: string;
  next_review_at?: string;
  created_at: string;
  items_count: number;
  pending_count: number;
}

const STATUS_COLORS: Record<string, string> = {
  active: 'bg-emerald-100 text-emerald-700',
  superseded: 'bg-gray-100 text-gray-600',
  archived: 'bg-gray-200 text-gray-500',
};

const TRIGGERED_BY_LABEL: Record<string, string> = {
  manual: '手动',
  new_exam: '新体检',
  new_gene: '新基因',
  scheduled: '定时',
  changed_conditions: '慢病变更',
  migration: '迁移',
};

function fmtDate(s?: string) {
  if (!s) return '—';
  return s.slice(0, 10);
}

export default function SupplementAuditsListPage() {
  const [audits, setAudits] = useState<AuditListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    supplementAuditApi
      .listMine(20)
      .then((res) => setAudits(res.data || []))
      .catch((err) => setError(err?.response?.data?.detail || err.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <ProtectedRoute>
      <div className="max-w-3xl mx-auto px-4 py-6">
        <div className="mb-6">
          <h1 className="text-xl font-bold text-gray-900">补剂审计中心</h1>
          <p className="text-xs text-gray-500 mt-1">
            长周期决策文档。基于体检 / 基因 / 慢病 / 打卡数据，提供 keep / add / upgrade / remove / monitor 五段式建议。
            每条建议可追踪 accept / reject / complete 状态。
          </p>
        </div>

        {loading && <div className="text-sm text-gray-500">加载中…</div>}
        {error && <div className="text-sm text-red-600">加载失败: {error}</div>}

        {!loading && !error && audits.length === 0 && (
          <div className="rounded-xl border border-gray-200 bg-white p-6 text-center text-sm text-gray-500">
            暂无审计。触发方式：新体检 / 新基因数据入库时自动生成，或手动在 AI 助理里请求。
          </div>
        )}

        <div className="space-y-3">
          {audits.map((a) => (
            <Link
              key={a.id}
              href={`/supplement-audits/${a.id}`}
              className="block rounded-xl border border-gray-200 bg-white p-4 hover:border-indigo-300 hover:shadow-sm transition"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs font-semibold text-gray-400">v{a.version}</span>
                    <span className={`text-[10px] px-2 py-0.5 rounded-full ${STATUS_COLORS[a.status] || 'bg-gray-100 text-gray-600'}`}>
                      {a.status}
                    </span>
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700">
                      {TRIGGERED_BY_LABEL[a.triggered_by] || a.triggered_by}
                    </span>
                  </div>
                  <h2 className="text-sm font-semibold text-gray-900 truncate">{a.title}</h2>
                  {a.summary && <p className="text-xs text-gray-600 mt-1 line-clamp-2">{a.summary}</p>}
                </div>
                {a.pending_count > 0 && (
                  <div className="shrink-0 text-center">
                    <div className="text-lg font-bold text-orange-500">{a.pending_count}</div>
                    <div className="text-[10px] text-gray-500">pending</div>
                  </div>
                )}
              </div>

              <div className="mt-3 flex items-center gap-4 text-[10px] text-gray-500">
                <span>依据 {fmtDate(a.data_period_start)} → {fmtDate(a.data_period_end)}</span>
                <span>·</span>
                <span>{a.items_count} 项建议</span>
                {a.next_review_at && (
                  <>
                    <span>·</span>
                    <span>下次复查 {fmtDate(a.next_review_at)}</span>
                  </>
                )}
              </div>
            </Link>
          ))}
        </div>
      </div>
    </ProtectedRoute>
  );
}
