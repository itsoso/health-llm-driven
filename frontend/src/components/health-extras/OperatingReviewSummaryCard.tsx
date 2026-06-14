'use client';

import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { BarChart3, CheckCircle2, ChevronRight, TrendingUp } from 'lucide-react';
import { getOperatingReviewSummary, type OperatingReviewSummary } from '@/services/api/operatingReviewSummary';

export default function OperatingReviewSummaryCard() {
  const { data: summary, isError, isLoading } = useQuery({
    queryKey: ['operating-review-summary', 7],
    queryFn: () => getOperatingReviewSummary(7),
    staleTime: 5 * 60 * 1000,
  });

  const href = summary?.href ?? '/my-progress';
  const title = isError ? '执行复盘加载失败' : summary?.title ?? '执行复盘检查中';
  const subtitle = isError
    ? '稍后刷新，避免用过期执行记录判断趋势。'
    : summary?.subtitle ?? '正在读取最近行动完成情况。';
  const items = summary?.items ?? placeholderItems(isLoading);
  const highlightTone = summary?.highlight?.positive ? 'text-emerald-800' : 'text-amber-800';
  const highlightBg = summary?.highlight?.positive ? 'border-emerald-100 bg-emerald-50' : 'border-amber-100 bg-amber-50';

  return (
    <Link
      href={href}
      className="mb-6 block rounded-xl border border-blue-100 bg-white p-5 shadow-sm transition hover:border-blue-200 hover:shadow-md"
    >
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="flex h-9 w-9 items-center justify-center rounded-lg border border-blue-200 bg-blue-50 text-blue-700">
              <CheckCircle2 className="h-5 w-5" />
            </span>
            <div>
              <p className="text-xs font-bold uppercase tracking-widest text-blue-700">执行复盘</p>
              <h2 className="mt-0.5 text-xl font-black text-gray-900">{title}</h2>
            </div>
          </div>
          <p className="mt-3 max-w-2xl text-sm font-medium text-gray-500">{subtitle}</p>
          {summary?.highlight ? (
            <div className={`mt-3 rounded-lg border px-3 py-2 ${highlightBg}`}>
              <p className="truncate text-xs font-bold text-gray-700">{summary.highlight.label}</p>
              <p className={`truncate text-sm font-black ${highlightTone}`}>{summary.highlight.value}</p>
              <p className="truncate text-xs font-semibold text-gray-500">{summary.highlight.detail}</p>
            </div>
          ) : null}
        </div>

        <div className="grid w-full grid-cols-2 gap-2 sm:grid-cols-4 lg:max-w-2xl">
          {items.map((item) => (
            <div
              key={item.key}
              className={`rounded-lg border px-3 py-2 ${
                item.accent ? 'border-blue-200 bg-blue-50' : 'border-slate-200 bg-slate-50'
              }`}
            >
              <div className="flex items-center gap-1.5">
                {item.accent ? (
                  <TrendingUp className="h-3.5 w-3.5 text-blue-700" />
                ) : (
                  <BarChart3 className="h-3.5 w-3.5 text-gray-500" />
                )}
                <p className="truncate text-xs font-bold text-gray-500">{item.label}</p>
              </div>
              <p className={`mt-1 truncate text-sm font-black ${item.accent ? 'text-blue-800' : 'text-gray-900'}`}>
                {item.value}
              </p>
            </div>
          ))}
        </div>

        <ChevronRight className="hidden h-5 w-5 shrink-0 text-gray-400 lg:block" />
      </div>
    </Link>
  );
}

function placeholderItems(isLoading: boolean): OperatingReviewSummary['items'] {
  const value = isLoading ? '检查中' : '未加载';
  return [
    { key: 'completion_rate', label: '完成率', value, accent: false },
    { key: 'completed', label: '已完成', value, accent: false },
    { key: 'total', label: '总行动', value, accent: false },
    { key: 'learnable', label: '可学习', value, accent: false },
  ];
}
