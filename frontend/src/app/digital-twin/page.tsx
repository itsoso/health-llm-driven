'use client';
import { fetchWithAiSubject as fetch } from '@/services/aiConsent';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { useAuth } from '@/contexts/AuthContext';
import { WEB_SESSION_TOKEN } from '@/services/api/client';

interface HealthScore {
  total_score: number;
  dimensions: {
    sleep: number;
    exercise: number;
    vitals: number;
    composition: number;
  };
  grade: string;
}

interface HeartRateZones {
  zone1_recovery: [number, number];
  zone2_fat_burn: [number, number];
  zone3_aerobic: [number, number];
  zone4_threshold: [number, number];
  zone5_max: [number, number];
  max_heart_rate: number;
  resting_heart_rate: number;
}

interface DigitalTwinReport {
  user_id: number;
  generated_at: string;
  physiological: {
    bmr: number | null;
    tdee: number | null;
    heart_rate_zones: HeartRateZones | null;
    ideal_weight_range: {
      min_weight: number;
      ideal_weight: number;
      max_weight: number;
    } | null;
  };
  health_score: HealthScore;
  trends: {
    sleep: {
      avg_duration_hours?: number;
      avg_score?: number;
      trend?: string;
      issues?: string[];
    };
    exercise: {
      avg_daily_steps?: number;
      avg_active_calories?: number;
      total_workouts?: number;
    };
    body_composition: {
      current_weight?: number;
      weight_change?: number;
    };
  };
  recommendations: Array<{
    category: string;
    priority: string;
    title: string;
    content: string;
  }>;
}

const API_BASE = '/api';

export default function DigitalTwinPage() {
  const { user } = useAuth();
  const [report, setReport] = useState<DigitalTwinReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (user) {
      fetchReport();
    }
  }, [user]);

  const fetchReport = async () => {
    setLoading(true);
    setError(null);

    try {
      const res = await fetch(`${API_BASE}/digital-twin/report`, {
        headers: { Authorization: `Bearer ${WEB_SESSION_TOKEN}` }
      });

      if (!res.ok) {
        throw new Error('获取报告失败');
      }

      const data = await res.json();
      setReport(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : '未知错误');
    } finally {
      setLoading(false);
    }
  };

  const getGradeColor = (grade: string) => {
    switch (grade) {
      case 'A': return 'text-green-500';
      case 'B': return 'text-blue-500';
      case 'C': return 'text-yellow-500';
      case 'D': return 'text-orange-500';
      default: return 'text-red-500';
    }
  };

  const getScoreColor = (score: number) => {
    if (score >= 80) return 'bg-green-500';
    if (score >= 60) return 'bg-yellow-500';
    return 'bg-red-500';
  };

  const getTrendIcon = (trend?: string) => {
    switch (trend) {
      case 'improving': return '📈';
      case 'declining': return '📉';
      case 'stable': return '➡️';
      default: return '❓';
    }
  };

  if (!user) {
    return (
      <div className="min-h-screen bg-gray-900 text-white flex items-center justify-center">
        <div className="text-center">
          <p className="mb-4">请先登录</p>
          <Link href="/login" className="text-blue-400 hover:underline">登录</Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-purple-900 to-gray-900 text-white">
      {/* Header */}
      <header className="sticky top-0 z-10 bg-black/30 backdrop-blur-lg border-b border-white/10">
        <div className="max-w-6xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link href="/" className="text-gray-400 hover:text-white">
              ← 返回
            </Link>
            <h1 className="text-xl font-bold bg-gradient-to-r from-cyan-400 to-purple-400 bg-clip-text text-transparent">
              🧬 数字孪生
            </h1>
          </div>
          <button
            onClick={fetchReport}
            disabled={loading}
            className="px-4 py-2 bg-purple-600 hover:bg-purple-500 rounded-lg text-sm disabled:opacity-50"
          >
            {loading ? '加载中...' : '🔄 刷新'}
          </button>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-8">
        {loading && (
          <div className="flex items-center justify-center py-20">
            <div className="animate-spin rounded-full h-12 w-12 border-4 border-purple-500 border-t-transparent"></div>
          </div>
        )}

        {error && (
          <div className="bg-red-900/30 border border-red-500 rounded-xl p-4 mb-6">
            <p className="text-red-300">❌ {error}</p>
          </div>
        )}

        {report && !loading && (
          <div className="space-y-8">
            {/* 健康评分卡片 */}
            <section className="bg-white/5 backdrop-blur rounded-2xl p-6 border border-white/10">
              <h2 className="text-lg font-semibold mb-6 flex items-center gap-2">
                <span className="text-2xl">🏆</span>
                综合健康评分
              </h2>

              <div className="flex items-center gap-8 mb-6">
                <div className="text-center">
                  <div className={`text-6xl font-bold ${getGradeColor(report.health_score.grade)}`}>
                    {report.health_score.total_score}
                  </div>
                  <div className={`text-2xl font-bold mt-2 ${getGradeColor(report.health_score.grade)}`}>
                    等级 {report.health_score.grade}
                  </div>
                </div>

                <div className="flex-1 space-y-3">
                  {Object.entries(report.health_score.dimensions).map(([key, value]) => (
                    <div key={key} className="flex items-center gap-3">
                      <span className="w-20 text-gray-400 text-sm">
                        {key === 'sleep' ? '😴 睡眠' :
                         key === 'exercise' ? '🏃 运动' :
                         key === 'vitals' ? '💓 身体状态' : '⚖️ 身体成分'}
                      </span>
                      <div className="flex-1 bg-gray-700 rounded-full h-3 overflow-hidden">
                        <div
                          className={`h-full ${getScoreColor(value)} transition-all duration-500`}
                          style={{ width: `${value}%` }}
                        />
                      </div>
                      <span className="w-12 text-right text-sm">{value}</span>
                    </div>
                  ))}
                </div>
              </div>
            </section>

            {/* 基础生理指标 */}
            <section className="bg-white/5 backdrop-blur rounded-2xl p-6 border border-white/10">
              <h2 className="text-lg font-semibold mb-6 flex items-center gap-2">
                <span className="text-2xl">🫀</span>
                基础生理指标
              </h2>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="bg-black/20 rounded-xl p-4 text-center">
                  <div className="text-gray-400 text-sm mb-1">基础代谢率</div>
                  <div className="text-2xl font-bold text-cyan-400">
                    {report.physiological.bmr || '--'}
                  </div>
                  <div className="text-xs text-gray-500">千卡/天</div>
                </div>

                <div className="bg-black/20 rounded-xl p-4 text-center">
                  <div className="text-gray-400 text-sm mb-1">每日总消耗</div>
                  <div className="text-2xl font-bold text-green-400">
                    {report.physiological.tdee || '--'}
                  </div>
                  <div className="text-xs text-gray-500">千卡/天</div>
                </div>

                <div className="bg-black/20 rounded-xl p-4 text-center">
                  <div className="text-gray-400 text-sm mb-1">最大心率</div>
                  <div className="text-2xl font-bold text-red-400">
                    {report.physiological.heart_rate_zones?.max_heart_rate || '--'}
                  </div>
                  <div className="text-xs text-gray-500">次/分</div>
                </div>

                <div className="bg-black/20 rounded-xl p-4 text-center">
                  <div className="text-gray-400 text-sm mb-1">静息心率</div>
                  <div className="text-2xl font-bold text-purple-400">
                    {report.physiological.heart_rate_zones?.resting_heart_rate || '--'}
                  </div>
                  <div className="text-xs text-gray-500">次/分</div>
                </div>
              </div>

              {/* 心率区间 */}
              {report.physiological.heart_rate_zones && (
                <div className="mt-6">
                  <h3 className="text-sm font-medium text-gray-400 mb-3">目标心率区间</h3>
                  <div className="grid grid-cols-1 md:grid-cols-5 gap-2">
                    {[
                      { key: 'zone1_recovery', label: '恢复区', color: 'bg-gray-500' },
                      { key: 'zone2_fat_burn', label: '燃脂区', color: 'bg-green-500' },
                      { key: 'zone3_aerobic', label: '有氧区', color: 'bg-yellow-500' },
                      { key: 'zone4_threshold', label: '阈值区', color: 'bg-orange-500' },
                      { key: 'zone5_max', label: '极限区', color: 'bg-red-500' },
                    ].map(zone => {
                      const range = report.physiological.heart_rate_zones?.[zone.key as keyof HeartRateZones] as [number, number];
                      return (
                        <div key={zone.key} className={`${zone.color} rounded-lg p-3 text-center`}>
                          <div className="text-xs font-medium">{zone.label}</div>
                          <div className="text-lg font-bold">{range?.[0]}-{range?.[1]}</div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* 理想体重范围 */}
              {report.physiological.ideal_weight_range && (
                <div className="mt-6">
                  <h3 className="text-sm font-medium text-gray-400 mb-3">理想体重范围 (BMI 18.5-24)</h3>
                  <div className="flex items-center gap-4">
                    <span className="text-sm text-gray-500">
                      {report.physiological.ideal_weight_range.min_weight} kg
                    </span>
                    <div className="flex-1 bg-gray-700 rounded-full h-3 relative">
                      <div className="absolute inset-0 bg-gradient-to-r from-yellow-500 via-green-500 to-yellow-500 rounded-full" />
                      <div
                        className="absolute top-1/2 -translate-y-1/2 w-4 h-4 bg-white rounded-full border-2 border-green-500 shadow-lg"
                        style={{
                          left: `${((report.physiological.ideal_weight_range.ideal_weight - report.physiological.ideal_weight_range.min_weight) /
                                 (report.physiological.ideal_weight_range.max_weight - report.physiological.ideal_weight_range.min_weight)) * 100}%`
                        }}
                        title={`理想: ${report.physiological.ideal_weight_range.ideal_weight} kg`}
                      />
                    </div>
                    <span className="text-sm text-gray-500">
                      {report.physiological.ideal_weight_range.max_weight} kg
                    </span>
                  </div>
                  <div className="text-center text-sm text-green-400 mt-2">
                    理想体重: {report.physiological.ideal_weight_range.ideal_weight} kg
                  </div>
                </div>
              )}
            </section>

            {/* 趋势分析 */}
            <section className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {/* 睡眠趋势 */}
              <div className="bg-white/5 backdrop-blur rounded-2xl p-6 border border-white/10">
                <h3 className="font-semibold mb-4 flex items-center gap-2">
                  <span>😴</span> 睡眠趋势
                  <span className="ml-auto">{getTrendIcon(report.trends.sleep.trend)}</span>
                </h3>
                <div className="space-y-3">
                  <div className="flex justify-between">
                    <span className="text-gray-400">平均时长</span>
                    <span className="font-medium">{report.trends.sleep.avg_duration_hours || '--'} 小时</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">平均得分</span>
                    <span className="font-medium">{report.trends.sleep.avg_score || '--'}</span>
                  </div>
                  {report.trends.sleep.issues && report.trends.sleep.issues.length > 0 && (
                    <div className="mt-3 pt-3 border-t border-white/10">
                      <div className="text-sm text-yellow-400">⚠️ 问题:</div>
                      {report.trends.sleep.issues.map((issue, i) => (
                        <div key={i} className="text-sm text-gray-400">• {issue}</div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* 运动趋势 */}
              <div className="bg-white/5 backdrop-blur rounded-2xl p-6 border border-white/10">
                <h3 className="font-semibold mb-4 flex items-center gap-2">
                  <span>🏃</span> 运动趋势
                </h3>
                <div className="space-y-3">
                  <div className="flex justify-between">
                    <span className="text-gray-400">日均步数</span>
                    <span className="font-medium">{report.trends.exercise.avg_daily_steps?.toLocaleString() || '--'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">活动消耗</span>
                    <span className="font-medium">{report.trends.exercise.avg_active_calories || '--'} 千卡</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">运动次数</span>
                    <span className="font-medium">{report.trends.exercise.total_workouts || 0} 次</span>
                  </div>
                </div>
              </div>

              {/* 体重趋势 */}
              <div className="bg-white/5 backdrop-blur rounded-2xl p-6 border border-white/10">
                <h3 className="font-semibold mb-4 flex items-center gap-2">
                  <span>⚖️</span> 体重趋势
                </h3>
                <div className="space-y-3">
                  <div className="flex justify-between">
                    <span className="text-gray-400">当前体重</span>
                    <span className="font-medium">{report.trends.body_composition.current_weight || '--'} kg</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">90天变化</span>
                    <span className={`font-medium ${
                      (report.trends.body_composition.weight_change || 0) < 0
                        ? 'text-green-400'
                        : (report.trends.body_composition.weight_change || 0) > 0
                          ? 'text-red-400'
                          : ''
                    }`}>
                      {report.trends.body_composition.weight_change !== undefined
                        ? `${report.trends.body_composition.weight_change > 0 ? '+' : ''}${report.trends.body_composition.weight_change} kg`
                        : '--'}
                    </span>
                  </div>
                </div>
              </div>
            </section>

            {/* 个性化建议 */}
            {report.recommendations && report.recommendations.length > 0 && (
              <section className="bg-white/5 backdrop-blur rounded-2xl p-6 border border-white/10">
                <h2 className="text-lg font-semibold mb-6 flex items-center gap-2">
                  <span className="text-2xl">💡</span>
                  个性化建议
                </h2>
                <div className="space-y-4">
                  {report.recommendations.map((rec, index) => (
                    <div
                      key={index}
                      className={`p-4 rounded-xl border ${
                        rec.priority === 'high'
                          ? 'bg-red-900/20 border-red-500/30'
                          : 'bg-yellow-900/20 border-yellow-500/30'
                      }`}
                    >
                      <div className="flex items-center gap-2 mb-2">
                        <span className={`px-2 py-0.5 rounded text-xs ${
                          rec.priority === 'high' ? 'bg-red-500' : 'bg-yellow-500'
                        }`}>
                          {rec.priority === 'high' ? '重要' : '建议'}
                        </span>
                        <span className="font-medium">{rec.title}</span>
                      </div>
                      <p className="text-sm text-gray-300">{rec.content}</p>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {/* 报告生成时间 */}
            <div className="text-center text-sm text-gray-500">
              报告生成时间: {new Date(report.generated_at).toLocaleString('zh-CN')}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
