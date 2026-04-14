'use client';

import { useState, useEffect } from 'react';
import {
  Check, Loader2, Sparkles, Target, TrendingUp, ArrowRight, Lightbulb, AlertTriangle,
  X, Plus, CloudRain, Sun, Cloud, Snowflake, Wind, Plane, Activity, Brain
} from 'lucide-react';
import { smartPlanApi } from '@/services/api/content';
import { AnalyzeData, categoryConfig } from './types';

/* eslint-disable @typescript-eslint/no-explicit-any */

function getWeatherIcon(weather: string) {
  if (weather.includes('雨')) return <CloudRain className="w-4 h-4 text-blue-500" />;
  if (weather.includes('雪')) return <Snowflake className="w-4 h-4 text-cyan-500" />;
  if (weather.includes('晴')) return <Sun className="w-4 h-4 text-amber-500" />;
  if (weather.includes('风')) return <Wind className="w-4 h-4 text-gray-500" />;
  return <Cloud className="w-4 h-4 text-gray-400" />;
}

export function PlanWizard({ targetWeek, debugMode, onClose, onSuccess }: {
  targetWeek: string;
  debugMode: boolean;
  onClose: () => void;
  onSuccess: (data: any, targetWeek: string) => void;
}) {
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [analyzeData, setAnalyzeData] = useState<AnalyzeData | null>(null);
  const [analyzeLoading, setAnalyzeLoading] = useState(true);
  const [analyzeError, setAnalyzeError] = useState<string | null>(null);
  const [selectedFocus, setSelectedFocus] = useState<string[]>([]);
  const [customFocus, setCustomFocus] = useState('');
  const [intensity, setIntensity] = useState<'light' | 'moderate' | 'challenge'>('moderate');
  const [userNotes, setUserNotes] = useState('');
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [progressStep, setProgressStep] = useState(0);

  // Step 1: 加载分析数据
  useEffect(() => {
    (async () => {
      try {
        setAnalyzeLoading(true);
        const res = await smartPlanApi.analyze(targetWeek);
        setAnalyzeData(res.data);
        // 预选建议的 focus
        const suggested = res.data.suggested_focus?.slice(0, 2).map((f: any) => f.label) || [];
        setSelectedFocus(suggested);
      } catch (e: any) {
        setAnalyzeError(e?.response?.data?.detail || '数据分析失败');
      } finally {
        setAnalyzeLoading(false);
      }
    })();
  }, [targetWeek]);

  // Step 3: 生成计划
  const handleGenerate = async () => {
    setGenerating(true);
    setGenerateError(null);
    setStep(3);
    setProgressStep(0);

    const timer = setInterval(() => {
      setProgressStep(prev => Math.min(prev + 1, 3));
    }, 2000);

    try {
      const allFocus = [...selectedFocus];
      if (customFocus.trim()) allFocus.push(customFocus.trim());

      const res = await smartPlanApi.generate({
        target_week: targetWeek,
        user_focus: allFocus,
        user_notes: userNotes,
        intensity,
      }, debugMode);

      clearInterval(timer);
      setProgressStep(4);
      setTimeout(() => {
        onSuccess(res.data, targetWeek);
      }, 1500);
    } catch (e: any) {
      clearInterval(timer);
      setGenerateError(e?.response?.data?.detail || 'AI 生成失败，请稍后重试');
      setStep(2);
      setGenerating(false);
    }
  };

  const toggleFocus = (label: string) => {
    setSelectedFocus(prev =>
      prev.includes(label) ? prev.filter(f => f !== label) : [...prev, label]
    );
  };

  const addCustomFocus = () => {
    if (customFocus.trim() && !selectedFocus.includes(customFocus.trim())) {
      setSelectedFocus(prev => [...prev, customFocus.trim()]);
      setCustomFocus('');
    }
  };

  const formatWeekRange = (start: string, end: string) => {
    const s = new Date(start);
    const e = new Date(end);
    return `${s.getMonth() + 1}/${s.getDate()} - ${e.getMonth() + 1}/${e.getDate()}`;
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="bg-white rounded-2xl w-full max-w-lg max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b">
          <h2 className="text-lg font-bold text-gray-900">
            制定{targetWeek === 'next' ? '下' : '本'}周计划
          </h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Step Indicator */}
        <div className="flex items-center gap-0 px-6 py-3 bg-gray-50">
          {[
            { num: 1, label: '数据回顾' },
            { num: 2, label: '定制偏好' },
            { num: 3, label: '生成计划' },
          ].map((s, idx) => (
            <div key={s.num} className="flex items-center flex-1">
              <div className={`flex items-center gap-1.5 ${step >= s.num ? 'text-blue-600' : 'text-gray-400'}`}>
                <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
                  step > s.num ? 'bg-blue-600 text-white' :
                  step === s.num ? 'bg-blue-600 text-white' :
                  'bg-gray-200 text-gray-500'
                }`}>
                  {step > s.num ? <Check className="w-3.5 h-3.5" /> : s.num}
                </div>
                <span className="text-xs font-medium hidden sm:inline">{s.label}</span>
              </div>
              {idx < 2 && <div className={`flex-1 h-0.5 mx-2 ${step > s.num ? 'bg-blue-600' : 'bg-gray-200'}`} />}
            </div>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          {/* Step 1: 数据回顾 */}
          {step === 1 && (
            analyzeLoading ? (
              <div className="flex flex-col items-center justify-center py-12">
                <Loader2 className="w-8 h-8 animate-spin text-blue-500 mb-3" />
                <p className="text-sm text-gray-500">正在分析你的健康数据...</p>
              </div>
            ) : analyzeError ? (
              <div className="text-center py-12">
                <AlertTriangle className="w-10 h-10 mx-auto text-red-400 mb-3" />
                <p className="text-red-600">{analyzeError}</p>
              </div>
            ) : analyzeData && (
              <>
                {/* 周期信息 */}
                <div className="text-center text-sm text-gray-500">
                  计划周期: {formatWeekRange(analyzeData.week_start, analyzeData.week_end)}
                </div>

                {/* 过去执行情况 */}
                {analyzeData.past_performance.weeks_analyzed > 0 && (
                  <div className="bg-gray-50 rounded-xl p-4">
                    <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-1.5">
                      <Activity className="w-4 h-4" />
                      过去执行情况
                      <span className="text-xs text-gray-400 font-normal">（近{analyzeData.past_performance.weeks_analyzed}周）</span>
                    </h3>
                    <div className="flex items-center gap-3 mb-3">
                      <div className="text-2xl font-bold text-blue-600">{analyzeData.past_performance.avg_completion_rate}%</div>
                      <div className="text-xs text-gray-500">
                        平均完成率
                        <span className={`ml-1 ${analyzeData.past_performance.trend === 'improving' ? 'text-green-600' : analyzeData.past_performance.trend === 'declining' ? 'text-red-600' : 'text-gray-400'}`}>
                          {analyzeData.past_performance.trend === 'improving' ? '↑ 上升' : analyzeData.past_performance.trend === 'declining' ? '↓ 下降' : '→ 稳定'}
                        </span>
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      {Object.entries(analyzeData.past_performance.by_category).map(([cat, stat]) => {
                        const config = categoryConfig[cat] || categoryConfig.other;
                        return (
                          <div key={cat} className="bg-white rounded-lg p-2 text-xs">
                            <div className="flex items-center gap-1 mb-1">
                              <span className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full ${config.color}`}>
                                {config.icon}{config.label}
                              </span>
                            </div>
                            <div className="flex items-center gap-1">
                              <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                                <div className="h-full bg-blue-500 rounded-full" style={{ width: `${stat.rate}%` }} />
                              </div>
                              <span className="text-gray-500 min-w-[32px] text-right">{stat.rate}%</span>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* 身体指标 */}
                {Object.keys(analyzeData.body_metrics).length > 0 && (
                  <div className="bg-gray-50 rounded-xl p-4">
                    <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-1.5">
                      <TrendingUp className="w-4 h-4" />
                      身体指标
                    </h3>
                    <div className="grid grid-cols-3 gap-2">
                      {analyzeData.body_metrics.weight && (
                        <div className="bg-white rounded-lg p-2 text-center">
                          <div className="text-lg font-bold text-gray-800">{analyzeData.body_metrics.weight.current}</div>
                          <div className="text-xs text-gray-400">体重 kg</div>
                          {analyzeData.body_metrics.weight.target && (
                            <div className="text-xs text-blue-500">目标 {analyzeData.body_metrics.weight.target}</div>
                          )}
                        </div>
                      )}
                      {analyzeData.body_metrics.sleep_score != null && (
                        <div className="bg-white rounded-lg p-2 text-center">
                          <div className="text-lg font-bold text-gray-800">{analyzeData.body_metrics.sleep_score}</div>
                          <div className="text-xs text-gray-400">睡眠评分</div>
                        </div>
                      )}
                      {analyzeData.body_metrics.body_battery != null && (
                        <div className="bg-white rounded-lg p-2 text-center">
                          <div className="text-lg font-bold text-gray-800">{analyzeData.body_metrics.body_battery}</div>
                          <div className="text-xs text-gray-400">身体电量</div>
                        </div>
                      )}
                      {analyzeData.body_metrics.stress_level != null && (
                        <div className="bg-white rounded-lg p-2 text-center">
                          <div className="text-lg font-bold text-gray-800">{analyzeData.body_metrics.stress_level}</div>
                          <div className="text-xs text-gray-400">压力水平</div>
                        </div>
                      )}
                      {analyzeData.body_metrics.resting_hr != null && (
                        <div className="bg-white rounded-lg p-2 text-center">
                          <div className="text-lg font-bold text-gray-800">{analyzeData.body_metrics.resting_hr}</div>
                          <div className="text-xs text-gray-400">静息心率</div>
                        </div>
                      )}
                      {analyzeData.body_metrics.bmi != null && (
                        <div className="bg-white rounded-lg p-2 text-center">
                          <div className="text-lg font-bold text-gray-800">{analyzeData.body_metrics.bmi.toFixed(1)}</div>
                          <div className="text-xs text-gray-400">BMI</div>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* 天气预报 */}
                {analyzeData.weather_forecast.available && analyzeData.weather_forecast.daily && (
                  <div className="bg-gray-50 rounded-xl p-4">
                    <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-1.5">
                      <Sun className="w-4 h-4" />
                      {analyzeData.weather_forecast.city}天气预报
                    </h3>
                    <div className="grid grid-cols-7 gap-1">
                      {analyzeData.weather_forecast.daily.map((d, idx) => (
                        <div key={idx} className="text-center bg-white rounded-lg p-1.5">
                          <div className="text-xs text-gray-500">{d.day_name}</div>
                          <div className="my-1">{getWeatherIcon(d.weather)}</div>
                          <div className="text-xs text-gray-400">{d.temp_low}~{d.temp_high}°</div>
                        </div>
                      ))}
                    </div>
                    {analyzeData.weather_forecast.air_quality && (
                      <div className="mt-2 text-xs text-gray-500">
                        空气质量: AQI {analyzeData.weather_forecast.air_quality.aqi} {analyzeData.weather_forecast.air_quality.level}
                      </div>
                    )}
                    {analyzeData.weather_forecast.exercise_advice && (
                      <div className="mt-1 text-xs text-blue-600">{analyzeData.weather_forecast.exercise_advice}</div>
                    )}
                  </div>
                )}

                {/* 行程 */}
                {analyzeData.trips.length > 0 && (
                  <div className="bg-amber-50 rounded-xl p-4">
                    <h3 className="text-sm font-semibold text-amber-700 mb-2 flex items-center gap-1.5">
                      <Plane className="w-4 h-4" />
                      本周行程
                    </h3>
                    {analyzeData.trips.map((trip, idx) => (
                      <div key={idx} className="text-sm">
                        <div className="font-medium text-gray-700">{trip.name} - {trip.destination}</div>
                        {trip.days.map((d, didx) => (
                          <div key={didx} className="text-xs text-gray-500 ml-2">{d.day_name}: {d.title}</div>
                        ))}
                      </div>
                    ))}
                  </div>
                )}

                {/* 活跃目标 */}
                {analyzeData.active_goals.length > 0 && (
                  <div className="bg-indigo-50 rounded-xl p-4">
                    <h3 className="text-sm font-semibold text-indigo-700 mb-2 flex items-center gap-1.5">
                      <Target className="w-4 h-4" />
                      活跃目标
                    </h3>
                    {analyzeData.active_goals.map((goal, idx) => (
                      <div key={idx} className="text-sm">
                        <div className="font-medium text-gray-700">{goal.period_type === 'monthly' ? '月度' : '年度'}目标</div>
                        {goal.metrics.map((m, midx) => (
                          <div key={midx} className="text-xs text-gray-500 ml-2">
                            {m.metric_name}: {m.current_value}{m.unit} → {m.target_value}{m.unit}
                          </div>
                        ))}
                      </div>
                    ))}
                  </div>
                )}
              </>
            )
          )}

          {/* Step 2: 定制偏好 */}
          {step === 2 && analyzeData && (
            <>
              {generateError && (
                <div className="bg-red-50 text-red-700 text-sm rounded-lg p-3 flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                  {generateError}
                </div>
              )}

              {/* 重点方向 */}
              <div>
                <h3 className="text-sm font-semibold text-gray-700 mb-2">本周重点方向</h3>
                <p className="text-xs text-gray-400 mb-3">基于你的数据建议，点击选择或添加自定义</p>
                <div className="flex flex-wrap gap-2">
                  {analyzeData.suggested_focus.map((f, idx) => (
                    <button
                      key={idx}
                      onClick={() => toggleFocus(f.label)}
                      className={`text-sm px-3 py-1.5 rounded-full border transition-all ${
                        selectedFocus.includes(f.label)
                          ? 'bg-blue-600 text-white border-blue-600'
                          : 'bg-white text-gray-700 border-gray-200 hover:border-blue-300'
                      }`}
                      title={f.reason}
                    >
                      {selectedFocus.includes(f.label) ? <Check className="w-3 h-3 inline mr-1" /> : null}
                      {f.label}
                    </button>
                  ))}
                  {/* 已选但不在建议中的 */}
                  {selectedFocus.filter(f => !analyzeData.suggested_focus.some(s => s.label === f)).map((f, idx) => (
                    <button
                      key={`custom-${idx}`}
                      onClick={() => toggleFocus(f)}
                      className="text-sm px-3 py-1.5 rounded-full bg-blue-600 text-white border border-blue-600"
                    >
                      <Check className="w-3 h-3 inline mr-1" />{f}
                    </button>
                  ))}
                </div>
                <div className="flex gap-2 mt-2">
                  <input
                    type="text"
                    value={customFocus}
                    onChange={(e) => setCustomFocus(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addCustomFocus(); } }}
                    placeholder="添加自定义重点..."
                    className="flex-1 text-sm px-3 py-1.5 border border-gray-200 rounded-lg focus:outline-none focus:border-blue-400"
                  />
                  <button onClick={addCustomFocus} disabled={!customFocus.trim()} className="px-3 py-1.5 text-sm bg-gray-100 text-gray-600 rounded-lg hover:bg-gray-200 disabled:opacity-50">
                    <Plus className="w-4 h-4" />
                  </button>
                </div>
              </div>

              {/* 运动强度 */}
              <div>
                <h3 className="text-sm font-semibold text-gray-700 mb-2">运动强度偏好</h3>
                <div className="grid grid-cols-3 gap-2">
                  {[
                    { key: 'light' as const, label: '轻松', desc: '恢复为主', icon: '🌿' },
                    { key: 'moderate' as const, label: '适中', desc: '平衡可持续', icon: '💪' },
                    { key: 'challenge' as const, label: '挑战', desc: '追求突破', icon: '🔥' },
                  ].map(opt => (
                    <button
                      key={opt.key}
                      onClick={() => setIntensity(opt.key)}
                      className={`p-3 rounded-xl border text-center transition-all ${
                        intensity === opt.key
                          ? 'border-blue-600 bg-blue-50 ring-1 ring-blue-600'
                          : 'border-gray-200 hover:border-blue-300'
                      }`}
                    >
                      <div className="text-xl mb-1">{opt.icon}</div>
                      <div className="text-sm font-medium text-gray-800">{opt.label}</div>
                      <div className="text-xs text-gray-400">{opt.desc}</div>
                    </button>
                  ))}
                </div>
              </div>

              {/* 备注 */}
              <div>
                <h3 className="text-sm font-semibold text-gray-700 mb-2">备注（可选）</h3>
                <textarea
                  value={userNotes}
                  onChange={(e) => setUserNotes(e.target.value)}
                  placeholder="如：周三出差不能运动、周末想安排户外跑步、最近膝盖不舒服..."
                  rows={3}
                  className="w-full text-sm px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:border-blue-400 resize-none"
                />
              </div>
            </>
          )}

          {/* Step 3: 生成中 */}
          {step === 3 && (
            <div className="flex flex-col items-center justify-center py-8">
              <div className="w-16 h-16 mb-6 relative">
                <Brain className="w-16 h-16 text-blue-500 animate-pulse" />
              </div>
              <div className="space-y-3 w-full max-w-xs">
                {[
                  { icon: '🧠', text: '分析健康数据...' },
                  { icon: '🌤', text: '结合天气和行程...' },
                  { icon: '📊', text: '制定个性化方案...' },
                  { icon: '✅', text: '生成完成！' },
                ].map((item, idx) => (
                  <div key={idx} className={`flex items-center gap-3 transition-all duration-500 ${
                    progressStep >= idx ? 'opacity-100' : 'opacity-30'
                  }`}>
                    <span className="text-lg">{item.icon}</span>
                    <span className={`text-sm ${progressStep >= idx ? 'text-gray-700' : 'text-gray-400'}`}>{item.text}</span>
                    {progressStep > idx && <Check className="w-4 h-4 text-green-500 ml-auto" />}
                    {progressStep === idx && idx < 3 && <Loader2 className="w-4 h-4 text-blue-500 animate-spin ml-auto" />}
                  </div>
                ))}
              </div>
              <div className="mt-6 w-full max-w-xs">
                <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-blue-500 rounded-full transition-all duration-500"
                    style={{ width: `${Math.min((progressStep / 4) * 100, 100)}%` }}
                  />
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        {step !== 3 && (
          <div className="flex items-center justify-between px-5 py-4 border-t bg-gray-50">
            {step === 1 ? (
              <>
                <div />
                <button
                  onClick={() => setStep(2)}
                  disabled={analyzeLoading || !!analyzeError}
                  className="flex items-center gap-2 px-5 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm font-medium"
                >
                  下一步 <ArrowRight className="w-4 h-4" />
                </button>
              </>
            ) : (
              <>
                <button
                  onClick={() => setStep(1)}
                  className="text-sm text-gray-600 hover:text-gray-800"
                >
                  ← 上一步
                </button>
                <button
                  onClick={handleGenerate}
                  disabled={generating}
                  className="flex items-center gap-2 px-5 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm font-medium"
                >
                  <Sparkles className="w-4 h-4" />
                  生成计划
                </button>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
