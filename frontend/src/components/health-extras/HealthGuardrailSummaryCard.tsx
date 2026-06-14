'use client';

import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, CheckCircle2, ChevronRight, ShieldCheck } from 'lucide-react';
import { getHealthGuardrailSummary } from '@/services/api/healthGuardrailSummary';

export default function HealthGuardrailSummaryCard() {
  const { data: summary, isError, isLoading } = useQuery({
    queryKey: ['health-guardrail-summary'],
    queryFn: getHealthGuardrailSummary,
    staleTime: 10 * 60 * 1000,
  });

  const attention = isError || (summary?.attentionCount ?? 0) > 0;
  const href = summary?.href ?? '/health-extras';
  const title = isError ? '健康守门加载失败' : summary?.title ?? '健康守门检查中';
  const subtitle = isError
    ? '稍后刷新，避免基于不完整状态做判断。'
    : summary?.subtitle ?? '正在检查数据可信度、用药梳理和慢病维护项。';
  const toneClass = attention
    ? 'border-amber-200 bg-amber-50 text-amber-800'
    : 'border-emerald-200 bg-emerald-50 text-emerald-800';
  const iconClass = attention ? 'text-amber-700' : 'text-emerald-700';

  return (
    <Link
      href={href}
      className="mb-6 block rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition hover:border-teal-200 hover:shadow-md"
    >
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className={`flex h-9 w-9 items-center justify-center rounded-lg border ${toneClass}`}>
              <ShieldCheck className={`h-5 w-5 ${iconClass}`} />
            </span>
            <div>
              <p className="text-xs font-bold uppercase tracking-widest text-teal-700">健康守门</p>
              <h2 className="mt-0.5 text-xl font-black text-gray-900">{title}</h2>
            </div>
          </div>
          <p className="mt-3 max-w-2xl text-sm font-medium text-gray-500">{subtitle}</p>
        </div>

        <div className="grid w-full grid-cols-2 gap-2 sm:grid-cols-4 lg:max-w-2xl">
          {(summary?.items ?? placeholderItems(isLoading)).map((item) => (
            <div
              key={item.key}
              className={`rounded-lg border px-3 py-2 ${
                item.attention
                  ? 'border-amber-200 bg-amber-50'
                  : 'border-slate-200 bg-slate-50'
              }`}
            >
              <div className="flex items-center gap-1.5">
                {item.attention ? (
                  <AlertTriangle className="h-3.5 w-3.5 text-amber-700" />
                ) : (
                  <CheckCircle2 className="h-3.5 w-3.5 text-teal-700" />
                )}
                <p className="truncate text-xs font-bold text-gray-500">{item.label}</p>
              </div>
              <p className={`mt-1 truncate text-sm font-black ${item.attention ? 'text-amber-800' : 'text-gray-900'}`}>
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
    { key: 'data_integrity', label: '数据自检', value, attention: false },
    { key: 'deprescribing', label: '用药梳理', value, attention: false },
    { key: 'connection', label: '社会连接', value, attention: false },
    { key: 'causal_links', label: '指标关联', value, attention: false },
  ];
}
