'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { format } from 'date-fns';
import { zhCN } from 'date-fns/locale';
import ProtectedRoute from '@/components/ProtectedRoute';
import { healthReportApi, HealthReport } from '@/services/api';

function formatMinutes(mins: number | null | undefined): string {
  if (!mins) return '—';
  const h = Math.floor(mins / 60);
  const m = Math.round(mins % 60);
  return `${h}h${m}m`;
}

function ScoreRing({ score, size = 80 }: { score: number | null; size?: number }) {
  const s = score ?? 0;
  const r = (size - 8) / 2;
  const c = 2 * Math.PI * r;
  const offset = c - (s / 100) * c;
  const color = s >= 80 ? '#22c55e' : s >= 60 ? '#eab308' : s >= 40 ? '#f97316' : '#ef4444';

  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="transform -rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#f3f4f6" strokeWidth={6} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={6}
          strokeDasharray={c} strokeDashoffset={offset} strokeLinecap="round" />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="text-xl font-bold" style={{ color }}>{score ?? '—'}</span>
      </div>
    </div>
  );
}

function SummaryCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-white rounded-xl shadow-sm border p-4">
      <h4 className="text-sm font-semibold text-gray-500 mb-3">{title}</h4>
      {children}
    </div>
  );
}

function MetricRow({ label, value, unit }: { label: string; value: any; unit?: string }) {
  return (
    <div className="flex justify-between py-1">
      <span className="text-sm text-gray-600">{label}</span>
      <span className="text-sm font-medium text-gray-900">{value ?? '—'}{unit && ` ${unit}`}</span>
    </div>
  );
}

function HealthReportContent() {
  const queryClient = useQueryClient();
  const [selectedReport, setSelectedReport] = useState<HealthReport | null>(null);
  const [generating, setGenerating] = useState(false);

  const { data: reports, isLoading } = useQuery({
    queryKey: ['health-reports'],
    queryFn: async () => {
      const res = await healthReportApi.list(undefined, 20);
      return res.data;
    },
  });

  const generateMutation = useMutation({
    mutationFn: async (type: string) => {
      setGenerating(true);
      const res = await healthReportApi.generate(type);
      return res.data;
    },
    onSuccess: (report) => {
      queryClient.invalidateQueries({ queryKey: ['health-reports'] });
      setSelectedReport(report);
      setGenerating(false);
    },
    onError: () => setGenerating(false),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => healthReportApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['health-reports'] });
      setSelectedReport(null);
    },
  });

  const reportList = Array.isArray(reports) ? reports : [];

  if (isLoading) {
    return (
      <main className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-green-50 pt-4 pb-8 px-8">
        <div className="max-w-6xl mx-auto text-center py-20">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4" />
          <p className="text-gray-800 text-lg">加载中...</p>
        </div>
      </main>
    );
  }

  // 报告详情视图
  if (selectedReport) {
    const r = selectedReport;
    return (
      <main className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-green-50 pt-4 pb-8 px-8">
        <div className="max-w-4xl mx-auto">
          <button onClick={() => setSelectedReport(null)} className="text-blue-600 hover:text-blue-800 mb-4">&larr; 返回列表</button>

          {/* 报告头部 */}
          <div className="bg-white rounded-2xl shadow-sm border p-6 mb-6">
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-2xl font-bold text-gray-900">{r.title}</h1>
                <p className="text-gray-500 mt-1">
                  {format(new Date(r.start_date), 'yyyy/MM/dd')} — {format(new Date(r.end_date), 'yyyy/MM/dd')}
                </p>
              </div>
              <ScoreRing score={r.health_score} size={100} />
            </div>

            {/* 对比 */}
            {Object.keys(r.comparison || {}).length > 0 && (
              <div className="flex gap-4 mt-4 pt-4 border-t">
                {r.comparison.health_score_change !== undefined && (
                  <span className={`text-sm ${r.comparison.health_score_change >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                    健康评分 {r.comparison.health_score_change > 0 ? '+' : ''}{r.comparison.health_score_change}
                  </span>
                )}
                {r.comparison.steps_change_pct !== undefined && (
                  <span className={`text-sm ${r.comparison.steps_change_pct >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                    步数 {r.comparison.steps_change_pct > 0 ? '+' : ''}{r.comparison.steps_change_pct}%
                  </span>
                )}
              </div>
            )}
          </div>

          {/* 各维度摘要 */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
            <SummaryCard title="运动">
              <MetricRow label="日均步数" value={r.exercise_summary?.avg_daily_steps?.toLocaleString()} unit="步" />
              <MetricRow label="总步数" value={r.exercise_summary?.total_steps?.toLocaleString()} unit="步" />
              <MetricRow label="总消耗" value={r.exercise_summary?.total_calories_burned} unit="kcal" />
              <MetricRow label="平均心率" value={r.exercise_summary?.avg_heart_rate} unit="bpm" />
            </SummaryCard>

            <SummaryCard title="睡眠">
              <MetricRow label="平均时长" value={formatMinutes(r.sleep_summary?.avg_sleep_duration)} />
              <MetricRow label="平均评分" value={r.sleep_summary?.avg_sleep_score} />
              <MetricRow label="深睡占比" value={formatMinutes(r.sleep_summary?.avg_deep_sleep)} />
              <MetricRow label="REM占比" value={formatMinutes(r.sleep_summary?.avg_rem_sleep)} />
            </SummaryCard>

            <SummaryCard title="饮食">
              <MetricRow label="日均热量" value={r.diet_summary?.avg_daily_calories} unit="kcal" />
              <MetricRow label="日均蛋白质" value={r.diet_summary?.avg_daily_protein} unit="g" />
              <MetricRow label="日均碳水" value={r.diet_summary?.avg_daily_carbs} unit="g" />
              <MetricRow label="记录天数" value={r.diet_summary?.record_days} unit="天" />
            </SummaryCard>

            <SummaryCard title="情绪">
              <MetricRow label="平均情绪" value={r.mood_summary?.avg_mood_score} unit="/5" />
              <MetricRow label="平均精力" value={r.mood_summary?.avg_energy_level} unit="/5" />
              <MetricRow label="平均压力" value={r.mood_summary?.avg_stress_level} unit="/5" />
              <MetricRow label="记录天数" value={r.mood_summary?.record_days} unit="天" />
            </SummaryCard>

            <SummaryCard title="体重">
              <MetricRow label="起始体重" value={r.weight_summary?.start_weight} unit="kg" />
              <MetricRow label="最新体重" value={r.weight_summary?.end_weight} unit="kg" />
              <MetricRow label="体重变化" value={r.weight_summary?.weight_change} unit="kg" />
              <MetricRow label="记录次数" value={r.weight_summary?.record_count} unit="次" />
            </SummaryCard>

            <SummaryCard title="体征">
              <MetricRow label="静息心率" value={r.vital_signs_summary?.avg_resting_heart_rate} unit="bpm" />
              <MetricRow label="HRV" value={r.vital_signs_summary?.avg_hrv} unit="ms" />
              <MetricRow label="压力等级" value={r.vital_signs_summary?.avg_stress_level} />
              <MetricRow label="Body Battery" value={r.vital_signs_summary?.avg_body_battery} />
            </SummaryCard>
          </div>

          {/* 建议 */}
          {r.ai_recommendations?.length > 0 && (
            <div className="bg-white rounded-2xl shadow-sm border p-6">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">健康建议</h3>
              <ul className="space-y-3">
                {r.ai_recommendations.map((rec, i) => (
                  <li key={i} className="flex gap-3">
                    <span className="text-blue-500 mt-0.5">💡</span>
                    <span className="text-gray-700 text-sm leading-relaxed">{rec}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </main>
    );
  }

  // 列表视图
  return (
    <main className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-green-50 pt-4 pb-8 px-8">
      <div className="max-w-6xl mx-auto">
        <div className="flex justify-between items-center mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">健康报告</h1>
            <p className="text-gray-500 mt-1">生成周报/月报，全方位了解你的健康状况</p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => generateMutation.mutate('weekly')}
              disabled={generating}
              className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              {generating ? '生成中...' : '生成周报'}
            </button>
            <button
              onClick={() => generateMutation.mutate('monthly')}
              disabled={generating}
              className="bg-green-600 text-white px-4 py-2 rounded-lg hover:bg-green-700 disabled:opacity-50 transition-colors"
            >
              {generating ? '生成中...' : '生成月报'}
            </button>
          </div>
        </div>

        {reportList.length === 0 ? (
          <div className="bg-white rounded-2xl shadow-sm border p-12 text-center">
            <p className="text-gray-400 text-lg mb-4">还没有健康报告</p>
            <p className="text-gray-400">点击上方按钮生成你的第一份报告</p>
          </div>
        ) : (
          <div className="space-y-3">
            {reportList.map((report: HealthReport) => (
              <div
                key={report.id}
                onClick={() => setSelectedReport(report)}
                className="bg-white rounded-xl shadow-sm border p-4 hover:shadow-md transition-shadow cursor-pointer"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <ScoreRing score={report.health_score} size={56} />
                    <div>
                      <h3 className="font-semibold text-gray-900">{report.title}</h3>
                      <p className="text-sm text-gray-500">
                        {format(new Date(report.start_date), 'MM/dd')} - {format(new Date(report.end_date), 'MM/dd')}
                        <span className="ml-2 px-2 py-0.5 bg-blue-50 text-blue-600 rounded text-xs">
                          {report.report_type === 'weekly' ? '周报' : report.report_type === 'monthly' ? '月报' : '年报'}
                        </span>
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="text-right text-sm text-gray-500">
                      {format(new Date(report.created_at), 'MM/dd HH:mm')}
                    </div>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        if (confirm('确定删除这份报告？')) deleteMutation.mutate(report.id);
                      }}
                      className="text-gray-400 hover:text-red-600 text-sm"
                    >
                      删除
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}

export default function HealthReportPage() {
  return <ProtectedRoute><HealthReportContent /></ProtectedRoute>;
}
