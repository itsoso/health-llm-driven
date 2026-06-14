'use client';

import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { ArrowUpRight, BarChart3, ChevronRight, FlaskConical } from 'lucide-react';
import { getOutcomeProofSummary } from '@/services/api/outcomeProofSummary';

export default function OutcomeProofSummaryCard() {
  const { data: summary, isError, isLoading } = useQuery({
    queryKey: ['outcome-proof-summary', 30],
    queryFn: () => getOutcomeProofSummary(30),
    staleTime: 5 * 60 * 1000,
  });

  const href = summary?.href ?? '/my-progress';
  const title = isError ? '个人证据加载失败' : summary?.title ?? '个人证据检查中';
  const subtitle = isError
    ? '稍后刷新，避免用过期结果判断干预。'
    : summary?.subtitle ?? '正在读取 AI 建议的验证结果。';
  const items = summary?.items ?? placeholderItems(isLoading);

  return (
    <Link
      href={href}
      className="mb-6 block rounded-xl border border-emerald-100 bg-white p-5 shadow-sm transition hover:border-emerald-200 hover:shadow-md"
    >
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="flex h-9 w-9 items-center justify-center rounded-lg border border-emerald-200 bg-emerald-50 text-emerald-700">
              <FlaskConical className="h-5 w-5" />
            </span>
            <div>
              <p className="text-xs font-bold uppercase tracking-widest text-emerald-700">个人证据</p>
              <h2 className="mt-0.5 text-xl font-black text-gray-900">{title}</h2>
            </div>
          </div>
          <p className="mt-3 max-w-2xl text-sm font-medium text-gray-500">{subtitle}</p>
          {summary?.highlight ? (
            <div className="mt-3 rounded-lg border border-emerald-100 bg-emerald-50 px-3 py-2">
              <p className="truncate text-xs font-bold text-gray-700">{summary.highlight.title}</p>
              <p className="truncate text-sm font-black text-emerald-800">{summary.highlight.detail}</p>
            </div>
          ) : null}
        </div>

        <div className="grid w-full grid-cols-2 gap-2 sm:grid-cols-4 lg:max-w-2xl">
          {items.map((item) => (
            <div
              key={item.key}
              className={`rounded-lg border px-3 py-2 ${
                item.accent ? 'border-emerald-200 bg-emerald-50' : 'border-slate-200 bg-slate-50'
              }`}
            >
              <div className="flex items-center gap-1.5">
                {item.accent ? (
                  <ArrowUpRight className="h-3.5 w-3.5 text-emerald-700" />
                ) : (
                  <BarChart3 className="h-3.5 w-3.5 text-gray-500" />
                )}
                <p className="truncate text-xs font-bold text-gray-500">{item.label}</p>
              </div>
              <p className={`mt-1 truncate text-sm font-black ${item.accent ? 'text-emerald-800' : 'text-gray-900'}`}>
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

function placeholderItems(isLoading: boolean) {
  const value = isLoading ? '检查中' : '未加载';
  return [
    { key: 'graded', label: '已验证', value, accent: false },
    { key: 'improved', label: '已改善', value, accent: false },
    { key: 'verifying', label: '验证中', value, accent: false },
    { key: 'rate', label: '改善率', value, accent: false },
  ];
}
