'use client';

import { useQuery } from '@tanstack/react-query';
import {
  Activity,
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  Info,
  Loader2,
  Minus,
} from 'lucide-react';
import ProtectedRoute from '@/components/ProtectedRoute';
import {
  getLiverAssessment,
  IndicatorTrend,
  TrendVerdict,
} from '@/services/api/chronicHealth';

const DISCLAIMER =
  '以上为基于历史数据的趋势提示,非诊断。请结合腹部超声及医生意见判断。';

// verdict → 配色 (好转绿 / 恶化红 / 平稳灰)
const VERDICT_STYLE: Record<
  TrendVerdict,
  { label: string; chip: string; bar: string }
> = {
  improving: {
    label: '好转',
    chip: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    bar: 'border-l-emerald-400',
  },
  worsening: {
    label: '恶化',
    chip: 'bg-red-50 text-red-700 border-red-200',
    bar: 'border-l-red-400',
  },
  stable: {
    label: '平稳',
    chip: 'bg-gray-50 text-gray-600 border-gray-200',
    bar: 'border-l-gray-300',
  },
};

function DirectionIcon({ trend }: { trend: IndicatorTrend }) {
  if (trend.direction === 'up') return <ArrowUpRight className="w-4 h-4" />;
  if (trend.direction === 'down') return <ArrowDownRight className="w-4 h-4" />;
  return <Minus className="w-4 h-4" />;
}

function TrendCard({
  name,
  trend,
  summaryLine,
}: {
  name: string;
  trend: IndicatorTrend | null;
  summaryLine?: string;
}) {
  if (!trend) {
    return (
      <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-4">
        <p className="font-semibold text-gray-800">{name} 趋势</p>
        <p className="text-sm text-gray-400 mt-1">历史数据不足,无法计算趋势。</p>
      </div>
    );
  }

  const style = VERDICT_STYLE[trend.verdict];
  const pct = trend.pct_change;
  const pctText = `${pct > 0 ? '+' : ''}${pct}%`;

  return (
    <div
      className={`bg-white rounded-xl border border-gray-100 border-l-4 ${style.bar} shadow-sm p-4`}
    >
      <div className="flex items-center justify-between gap-2">
        <p className="font-semibold text-gray-800">{name} 趋势</p>
        <span
          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border ${style.chip}`}
        >
          <DirectionIcon trend={trend} />
          {style.label}
        </span>
      </div>

      <div className="mt-3 flex items-baseline gap-2 text-sm text-gray-600">
        <span className="font-mono">{trend.first_value}</span>
        <ArrowRight className="w-3.5 h-3.5 text-gray-300" />
        <span className="font-mono font-semibold text-gray-800">
          {trend.last_value}
        </span>
        <span className="text-xs text-gray-400">U/L · {pctText}</span>
      </div>
      <p className="mt-1 text-xs text-gray-400">
        {trend.first_date} → {trend.last_date} · 共 {trend.n} 次记录
      </p>

      {summaryLine && (
        <p className="mt-2 text-sm text-gray-600">{summaryLine}</p>
      )}
    </div>
  );
}

function MetricRow({
  label,
  value,
  hint,
}: {
  label: string;
  value: React.ReactNode;
  hint?: string;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-2 border-b border-gray-50 last:border-0">
      <span className="text-sm text-gray-500 flex-shrink-0">{label}</span>
      <span className="text-sm text-gray-800 text-right">
        {value}
        {hint && <span className="block text-xs text-gray-400 mt-0.5">{hint}</span>}
      </span>
    </div>
  );
}

function LiverContent() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['liver-assessment'],
    queryFn: getLiverAssessment,
  });

  return (
    <main className="min-h-screen bg-gradient-to-br from-amber-50 via-white to-emerald-50 pt-4 pb-12 px-4 sm:px-8">
      <div className="max-w-3xl mx-auto">
        {/* 标题 */}
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-gray-800 flex items-center gap-2">
            <Activity className="w-6 h-6 text-amber-600" />
            肝脏趋势
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            消费历史肝酶记录,给出 ALT/GGT 长期趋势、AST/ALT 比值、FIB-4 与脂肪肝风险提示。
          </p>
        </div>

        {isLoading ? (
          <div className="flex items-center gap-2 text-sm text-gray-400 py-16 justify-center">
            <Loader2 className="w-4 h-4 animate-spin" /> 加载中…
          </div>
        ) : isError ? (
          <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-3">
            肝脏趋势加载失败,请稍后重试。
          </p>
        ) : !data?.available ? (
          // 空态
          <div className="bg-white rounded-2xl border border-gray-100 shadow-sm px-6 py-12 text-center">
            <Info className="w-8 h-8 text-gray-300 mx-auto mb-3" />
            <p className="text-sm text-gray-500">
              {data?.reason || '暂无可用于肝脏趋势评估的历史数据。'}
            </p>
          </div>
        ) : (
          <div className="space-y-8">
            {/* 趋势卡 */}
            <section>
              <h2 className="text-lg font-semibold text-gray-800 mb-3">肝酶趋势</h2>
              <div className="grid gap-3 sm:grid-cols-2">
                <TrendCard
                  name="ALT"
                  trend={data.alt_trend}
                  summaryLine={data.summary_lines[0]}
                />
                <TrendCard
                  name="GGT"
                  trend={data.ggt_trend}
                  summaryLine={data.summary_lines[1]}
                />
              </div>
            </section>

            {/* 关键指标 */}
            <section>
              <h2 className="text-lg font-semibold text-gray-800 mb-3">关键指标</h2>
              <div className="bg-white rounded-xl border border-gray-100 shadow-sm px-4 py-2">
                <MetricRow
                  label="AST/ALT 比值"
                  value={
                    data.ast_alt_ratio != null ? (
                      <span className="font-mono font-semibold">
                        {data.ast_alt_ratio}
                      </span>
                    ) : (
                      <span className="text-gray-400">缺 AST 或 ALT</span>
                    )
                  }
                />
                <MetricRow
                  label="FIB-4 肝纤维化指数"
                  value={
                    data.fib4 != null ? (
                      <span className="font-mono font-semibold">
                        {data.fib4}
                        {data.fib4_band && (
                          <span className="ml-2 text-xs font-normal text-gray-500">
                            ({data.fib4_band})
                          </span>
                        )}
                      </span>
                    ) : (
                      <span className="text-gray-400">
                        缺血小板,补血常规即可评估
                      </span>
                    )
                  }
                />
                <MetricRow
                  label="脂肪肝风险"
                  value={
                    data.fatty_liver_risk ? (
                      <span className="text-orange-600 font-medium">
                        {data.fatty_liver_risk}
                      </span>
                    ) : (
                      <span className="text-gray-400">未见明显提示</span>
                    )
                  }
                />
              </div>
            </section>

            {/* 建议 */}
            {data.advice.length > 0 && (
              <section>
                <h2 className="text-lg font-semibold text-gray-800 mb-3">建议</h2>
                <ul className="bg-white rounded-xl border border-gray-100 shadow-sm divide-y divide-gray-50">
                  {data.advice.map((line, idx) => (
                    <li
                      key={idx}
                      className="flex items-start gap-2 px-4 py-3 text-sm text-gray-700"
                    >
                      <Info className="w-4 h-4 text-amber-500 mt-0.5 flex-shrink-0" />
                      <span>{line}</span>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {/* 免责 */}
            <p className="text-xs text-gray-400 leading-relaxed">{DISCLAIMER}</p>
          </div>
        )}
      </div>
    </main>
  );
}

export default function LiverPage() {
  return (
    <ProtectedRoute>
      <LiverContent />
    </ProtectedRoute>
  );
}
