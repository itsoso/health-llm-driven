'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { healthConsultationApi } from '@/services/api/records';

interface ConsultListItem {
  id: number;
  version: number;
  title: string;
  topic?: string;
  consultation_type: string;
  status: string;
  summary?: string;
  verification_scheduled_at?: string;
  total_items: number;
  hypothesis_count: number;
  action_count: number;
  prediction_count: number;
  red_flag_count: number;
  pending_count: number;
}

const TYPE_LABEL: Record<string, string> = {
  symptom_advisory: '症状',
  lifestyle_advice: '生活',
  preventive_review: '预防',
  urgent: '紧急',
  followup: '随访',
};

const TYPE_COLOR: Record<string, string> = {
  urgent: 'bg-rose-50 text-rose-700 border-rose-200',
  symptom_advisory: 'bg-indigo-50 text-indigo-700 border-indigo-200',
  lifestyle_advice: 'bg-sky-50 text-sky-700 border-sky-200',
  preventive_review: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  followup: 'bg-amber-50 text-amber-700 border-amber-200',
};

function fmtDate(s?: string) {
  return s ? s.slice(5, 10).replace('-', '/') : '—';
}

/**
 * 健康咨询卡片 (iPhone 首页)
 * - 显示活跃 consultations（含红线警戒 + 待办行动 + 即将到期预测）
 * - 点击条目跳转详情
 */
export default function ConsultationsCard() {
  const [items, setItems] = useState<ConsultListItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // 注: 后端 /me/active 返回单个对象 (当前版本), 这里用列表 API + 状态过滤, 只取 active 的
    healthConsultationApi
      .listMine(10)
      .then((res) => {
        const list = Array.isArray(res.data) ? res.data : [];
        setItems(list.filter((c: any) => c && c.status === 'active'));
      })
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, []);

  // 防御: items 理论上始终是数组, 但 API 返回异常时兜底为 []
  const list: ConsultListItem[] = Array.isArray(items) ? items : [];
  if (!loading && list.length === 0) return null;

  const totalRedFlags = list.reduce((s, c) => s + (c.red_flag_count || 0), 0);
  const totalPending = list.reduce((s, c) => s + (c.pending_count || 0), 0);

  return (
    <div className="rounded-2xl bg-white px-4 py-3 shadow-sm border border-gray-100">
      <div className="flex items-center justify-between mb-2.5">
        <div className="flex items-center gap-2">
          <span className="text-sm">🩺</span>
          <span className="text-sm font-semibold text-gray-800">健康咨询</span>
          {totalRedFlags > 0 && (
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-rose-100 text-rose-700 font-medium">
              ⚠ {totalRedFlags} 警戒
            </span>
          )}
          {totalPending > 0 && (
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-orange-50 text-orange-600 font-medium">
              {totalPending} 待办
            </span>
          )}
        </div>
        <Link href="/health-consultations" className="text-[11px] text-indigo-600 hover:underline">
          全部
        </Link>
      </div>

      {loading && <div className="text-xs text-gray-400">加载中…</div>}

      <div className="space-y-2">
        {list.slice(0, 3).map((c) => (
          <Link
            key={c.id}
            href={`/health-consultations/${c.id}`}
            className="block rounded-xl border border-gray-100 bg-gray-50/60 px-3 py-2.5 transition-all active:scale-[0.98]"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5 mb-0.5 flex-wrap">
                  <span className={`text-[9px] px-1.5 py-0.5 rounded border ${TYPE_COLOR[c.consultation_type] || 'bg-gray-50 text-gray-600 border-gray-200'}`}>
                    {TYPE_LABEL[c.consultation_type] || c.consultation_type}
                  </span>
                  <span className="text-[9px] text-gray-400">v{c.version}</span>
                  {c.red_flag_count > 0 && (
                    <span className="text-[9px] px-1 py-0.5 rounded bg-rose-50 text-rose-700">
                      ⚠{c.red_flag_count}
                    </span>
                  )}
                </div>
                <div className="text-[13px] font-medium text-gray-900 truncate leading-tight">
                  {c.title}
                </div>
                {c.summary && (
                  <div className="text-[11px] text-gray-500 mt-0.5 line-clamp-2 leading-snug">
                    {c.summary}
                  </div>
                )}
                <div className="mt-1 flex items-center gap-2 text-[10px] text-gray-400">
                  {c.hypothesis_count > 0 && <span>🧠 {c.hypothesis_count}</span>}
                  {c.action_count > 0 && <span>✓ {c.action_count}</span>}
                  {c.prediction_count > 0 && <span>📊 {c.prediction_count}</span>}
                  {c.verification_scheduled_at && (
                    <span className="ml-auto">复盘 {fmtDate(c.verification_scheduled_at)}</span>
                  )}
                </div>
              </div>
              {c.pending_count > 0 && (
                <div className="shrink-0 flex flex-col items-center">
                  <div className="text-base font-bold text-orange-500 leading-none">{c.pending_count}</div>
                  <div className="text-[9px] text-gray-400 mt-0.5">待办</div>
                </div>
              )}
            </div>
          </Link>
        ))}
        {list.length > 3 && (
          <Link
            href="/health-consultations"
            className="block text-center text-[11px] text-gray-500 py-1 hover:text-indigo-600"
          >
            还有 {list.length - 3} 条咨询 →
          </Link>
        )}
      </div>
    </div>
  );
}
