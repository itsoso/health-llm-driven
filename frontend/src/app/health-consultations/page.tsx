'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { healthConsultationApi } from '@/services/api/records';
import ProtectedRoute from '@/components/ProtectedRoute';

interface ConsultListItem {
  id: number;
  version: number;
  title: string;
  topic?: string;
  consultation_type: string;
  triggered_by: string;
  status: string;
  summary?: string;
  verification_scheduled_at?: string;
  created_at: string;
  total_items: number;
  hypothesis_count: number;
  action_count: number;
  prediction_count: number;
  red_flag_count: number;
  pending_count: number;
}

const STATUS_COLORS: Record<string, string> = {
  active: 'bg-emerald-100 text-emerald-700',
  superseded: 'bg-gray-100 text-gray-600',
  verified: 'bg-blue-100 text-blue-700',
  archived: 'bg-gray-200 text-gray-500',
};

const TYPE_LABEL: Record<string, string> = {
  symptom_advisory: '症状咨询',
  lifestyle_advice: '生活建议',
  preventive_review: '预防评估',
  urgent: '紧急',
  followup: '随访',
};

function fmtDate(s?: string) {
  return s ? s.slice(0, 10) : '—';
}

export default function HealthConsultationsListPage() {
  const [items, setItems] = useState<ConsultListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    healthConsultationApi
      .listMine(20)
      .then((res) => setItems(res.data || []))
      .catch((err) => setError(err?.response?.data?.detail || err.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <ProtectedRoute>
      <div className="max-w-3xl mx-auto px-4 py-6">
        <div className="mb-6">
          <h1 className="text-xl font-bold text-gray-900">健康咨询中心</h1>
          <p className="text-xs text-gray-500 mt-1">
            多层级症状咨询追踪。每次咨询包含假设 / 行动 / 可检验预测 / 警戒信号四类。
            预测会在到期时自动对比 Garmin 和体检数据做回测。
          </p>
        </div>

        {loading && <div className="text-sm text-gray-500">加载中…</div>}
        {error && <div className="text-sm text-red-600">加载失败: {error}</div>}

        {!loading && !error && items.length === 0 && (
          <div className="rounded-xl border border-gray-200 bg-white p-6 text-center text-sm text-gray-500">
            暂无咨询记录。
          </div>
        )}

        <div className="space-y-3">
          {items.map((c) => (
            <Link
              key={c.id}
              href={`/health-consultations/${c.id}`}
              className="block rounded-xl border border-gray-200 bg-white p-4 hover:border-indigo-300 hover:shadow-sm transition"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <span className="text-xs font-semibold text-gray-400">v{c.version}</span>
                    <span className={`text-[10px] px-2 py-0.5 rounded-full ${STATUS_COLORS[c.status] || 'bg-gray-100 text-gray-600'}`}>
                      {c.status}
                    </span>
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700">
                      {TYPE_LABEL[c.consultation_type] || c.consultation_type}
                    </span>
                    {c.red_flag_count > 0 && (
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-rose-50 text-rose-700">
                        ⚠ {c.red_flag_count} 警戒
                      </span>
                    )}
                  </div>
                  <h2 className="text-sm font-semibold text-gray-900 truncate">{c.title}</h2>
                  {c.topic && <p className="text-[10px] text-gray-500 mt-0.5">🏷 {c.topic}</p>}
                  {c.summary && <p className="text-xs text-gray-600 mt-1 line-clamp-2">{c.summary}</p>}
                </div>
                {c.pending_count > 0 && (
                  <div className="shrink-0 text-center">
                    <div className="text-lg font-bold text-orange-500">{c.pending_count}</div>
                    <div className="text-[10px] text-gray-500">pending</div>
                  </div>
                )}
              </div>

              {/* 四类 items 统计 */}
              <div className="mt-3 flex items-center gap-1.5 flex-wrap">
                {c.hypothesis_count > 0 && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-50 text-purple-700">
                    🧠 假设 {c.hypothesis_count}
                  </span>
                )}
                {c.action_count > 0 && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-50 text-blue-700">
                    ✓ 行动 {c.action_count}
                  </span>
                )}
                {c.prediction_count > 0 && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-green-50 text-green-700">
                    📊 预测 {c.prediction_count}
                  </span>
                )}
                {c.red_flag_count > 0 && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-rose-50 text-rose-700">
                    ⚠ 警戒 {c.red_flag_count}
                  </span>
                )}
              </div>

              <div className="mt-2 flex items-center gap-3 text-[10px] text-gray-500">
                <span>{fmtDate(c.created_at)}</span>
                {c.verification_scheduled_at && (
                  <>
                    <span>·</span>
                    <span>下次复盘 {fmtDate(c.verification_scheduled_at)}</span>
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
