'use client';

import { useQuery } from '@tanstack/react-query';
import { Pill, AlertTriangle, Loader2, ShieldCheck } from 'lucide-react';
import { getDeprescribingReview } from '@/services/api/medication';

const FLAG_LABEL: Record<string, string> = {
  polypharmacy: '多药',
  duplicate_class: '同类重复',
  long_term_candidate: '长期使用',
  expired_still_active: '疗程已过仍在用',
};

export default function DeprescribingSection() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['deprescribing-review'],
    queryFn: getDeprescribingReview,
  });

  return (
    <section className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
      <header className="flex items-center gap-2 mb-1">
        <Pill className="w-5 h-5 text-indigo-600" />
        <h2 className="text-lg font-semibold text-gray-800">多药梳理</h2>
      </header>
      <p className="text-sm text-gray-500 mb-4">
        梳理在用药,标出值得与医生讨论是否可精简的候选。这里只做提示,不替你做任何停药决定。
      </p>

      {isLoading ? (
        <div className="flex items-center gap-2 text-sm text-gray-400 py-6 justify-center">
          <Loader2 className="w-4 h-4 animate-spin" /> 加载中…
        </div>
      ) : isError ? (
        <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">
          加载失败,请稍后重试。
        </p>
      ) : data ? (
        <>
          <div className="flex items-center gap-3 mb-4">
            <div className="inline-flex items-baseline gap-1.5 px-3 py-1.5 rounded-lg bg-gray-50">
              <span className="text-2xl font-bold text-gray-800">{data.active_count}</span>
              <span className="text-sm text-gray-500">种在用药</span>
            </div>
            {data.is_polypharmacy && (
              <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-100 text-amber-700">
                <AlertTriangle className="w-3.5 h-3.5" />
                多药
              </span>
            )}
          </div>

          {data.flags.length === 0 ? (
            <div className="flex items-center gap-2 text-sm text-emerald-700 bg-emerald-50 rounded-xl px-4 py-4">
              <ShieldCheck className="w-4 h-4 flex-shrink-0" />
              暂无减药候选提示。
            </div>
          ) : (
            <ul className="space-y-3">
              {data.flags.map((flag, idx) => (
                <li
                  key={`${flag.code}-${idx}`}
                  className="border border-gray-100 rounded-xl p-4 bg-gray-50/50"
                >
                  <div className="flex items-start gap-2">
                    <AlertTriangle className="w-4 h-4 text-amber-500 mt-0.5 flex-shrink-0" />
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-gray-800">
                        <span className="text-amber-600 mr-1.5">
                          [{FLAG_LABEL[flag.code] || flag.code}]
                        </span>
                        {flag.detail}
                      </p>
                      <p className="text-sm text-gray-500 mt-1">{flag.suggestion}</p>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}

          <p className="mt-4 text-xs text-gray-400">{data.disclaimer}</p>
        </>
      ) : null}
    </section>
  );
}
