'use client';

import { useQuery } from '@tanstack/react-query';
import { GitCompareArrows, Loader2, Info, ArrowDown, ArrowUp } from 'lucide-react';
import { getCausalLinks } from '@/services/api/chronicHealth';

export default function CausalLinksSection() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['causal-links'],
    queryFn: getCausalLinks,
  });

  const effects = data?.intervention_effects ?? [];

  return (
    <section className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
      <header className="flex items-center gap-2 mb-1">
        <GitCompareArrows className="w-5 h-5 text-violet-500" />
        <h2 className="text-lg font-semibold text-gray-800">用药 · 指标关联</h2>
      </header>
      <p className="text-sm text-gray-500 mb-4">
        对比开始用药前后一段时间里相关指标的平均值变化。这是观察到的关联,不能证明因果。
      </p>

      {isLoading ? (
        <div className="flex items-center gap-2 text-sm text-gray-400 py-6 justify-center">
          <Loader2 className="w-4 h-4 animate-spin" /> 加载中…
        </div>
      ) : isError ? (
        <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">
          加载失败,请稍后重试。
        </p>
      ) : effects.length === 0 ? (
        <p className="text-sm text-gray-400 bg-gray-50 rounded-xl px-4 py-6 text-center">
          暂无足够数据计算用药前后的指标变化。
        </p>
      ) : (
        <div className="space-y-3">
          {effects.map((eff, idx) => {
            const dropped = eff.delta < 0;
            return (
              <div
                key={`${eff.medication}-${eff.metric_label}-${idx}`}
                className="border border-gray-100 rounded-xl p-4"
              >
                <div className="flex flex-wrap items-baseline gap-x-2">
                  <span className="font-semibold text-gray-800">{eff.medication}</span>
                  <span className="text-sm text-gray-500">→ {eff.metric_label}</span>
                </div>
                <div className="mt-2 flex items-center gap-2 text-sm">
                  <span className="text-gray-500">{eff.before_mean}</span>
                  {dropped ? (
                    <ArrowDown className="w-4 h-4 text-emerald-500" />
                  ) : (
                    <ArrowUp className="w-4 h-4 text-amber-500" />
                  )}
                  <span className="font-medium text-gray-800">{eff.after_mean}</span>
                  {eff.pct != null && (
                    <span
                      className={`ml-1 text-xs font-medium ${
                        dropped ? 'text-emerald-600' : 'text-amber-600'
                      }`}
                    >
                      {eff.pct > 0 ? '+' : ''}
                      {eff.pct}%
                    </span>
                  )}
                </div>
                <p className="mt-1.5 text-xs text-gray-400">
                  前 {eff.n_before} 次 / 后 {eff.n_after} 次测量的均值
                </p>
              </div>
            );
          })}
        </div>
      )}

      {data?.note && (
        <p className="mt-4 text-xs text-gray-400 flex items-start gap-1.5">
          <Info className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
          {data.note}
        </p>
      )}
    </section>
  );
}
