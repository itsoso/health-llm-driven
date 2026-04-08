'use client';

import { useState, useEffect } from 'react';
import { supplementApi } from '@/services/api/records';

interface GuideItem {
  id: number;
  name: string;
  dosage: string;
  taken: boolean;
  taken_time?: string;
  tips: string[];
  category: string;
}

interface GuideSlot {
  timing: string;
  label: string;
  items: GuideItem[];
}

interface GuideAlert {
  level: string;
  icon: string;
  message: string;
}

interface GuideRec {
  type: string;
  icon: string;
  title: string;
  message: string;
  priority: string;
}

interface GuideSummary {
  total: number;
  taken: number;
  remaining: number;
  completion_rate: number;
}

interface GuideData {
  date: string;
  slots: GuideSlot[];
  alerts: GuideAlert[];
  recommendations: GuideRec[];
  medications: any[];
  context: {
    sleep_quality?: string;
    sleep_score?: number;
    hrv_status?: string;
    hrv_value?: number;
    has_exercise: boolean;
    exercise_types: string[];
    rhinitis_active: boolean;
    sneeze_count: number;
    is_injection_day: boolean;
  };
  summary: GuideSummary;
}

const ALERT_STYLES: Record<string, string> = {
  warning: 'bg-amber-50 border-amber-200 text-amber-800',
  important: 'bg-red-50 border-red-200 text-red-800',
  info: 'bg-blue-50 border-blue-200 text-blue-700',
};

const REC_STYLES: Record<string, string> = {
  high: 'bg-orange-50 border-orange-200',
  medium: 'bg-sky-50 border-sky-200',
  low: 'bg-gray-50 border-gray-200',
};

export default function SupplementGuideCard() {
  const [guide, setGuide] = useState<GuideData | null>(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    supplementApi.getDailyGuide()
      .then(res => setGuide(res.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="bg-white rounded-xl p-3 border border-gray-100 shadow-sm animate-pulse">
        <div className="h-4 bg-gray-200 rounded w-32 mb-2" />
        <div className="h-3 bg-gray-100 rounded w-48" />
      </div>
    );
  }

  if (!guide || guide.slots.length === 0) return null;

  const { slots, alerts, recommendations, summary, medications, context } = guide;

  const hour = new Date().getHours();
  const currentTiming = hour < 11 ? 'morning' : hour < 14 ? 'noon' : hour < 19 ? 'evening' : 'bedtime';

  // 高优先级推荐始终显示，低优先级在展开时显示
  const highRecs = recommendations.filter(r => r.priority === 'high');
  const otherRecs = recommendations.filter(r => r.priority !== 'high');

  return (
    <div className="bg-white rounded-xl p-3 border border-gray-100 shadow-sm">
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-1.5">
          <span className="text-[11px] font-semibold text-gray-600">💊 每日补剂指南</span>
          {context.rhinitis_active && <span className="text-[10px]" title={`今日喷嚏${context.sneeze_count}次`}>👃</span>}
          {context.is_injection_day && <span className="text-[10px]">💉</span>}
          {context.sleep_quality === 'poor' && <span className="text-[10px]" title={`睡眠${context.sleep_score}分`}>😴</span>}
          {context.has_exercise && <span className="text-[10px]">🏃</span>}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-gray-400">{summary.taken}/{summary.total}</span>
          <div className="w-12 h-1.5 bg-gray-100 rounded-full overflow-hidden">
            <div className="h-full bg-emerald-400 rounded-full transition-all" style={{ width: `${summary.completion_rate}%` }} />
          </div>
          <button onClick={() => setExpanded(!expanded)} className="text-[10px] text-gray-400 hover:text-gray-600">
            {expanded ? '收起' : '展开'}
          </button>
        </div>
      </div>

      {/* Alerts */}
      {alerts.length > 0 && (
        <div className="space-y-1 mb-2">
          {alerts.map((a, i) => (
            <div key={i} className={`text-[10px] px-2 py-1 rounded-md border ${ALERT_STYLES[a.level] || ALERT_STYLES.info}`}>
              {a.icon} {a.message}
            </div>
          ))}
        </div>
      )}

      {/* Dynamic Recommendations (high priority always, others when expanded) */}
      {highRecs.length > 0 && (
        <div className="space-y-1 mb-2">
          {highRecs.map((r, i) => (
            <div key={`rec-h-${i}`} className={`px-2 py-1.5 rounded-md border ${REC_STYLES[r.priority]}`}>
              <div className="text-[10px] font-semibold text-gray-700">{r.icon} {r.title}</div>
              <div className="text-[9px] text-gray-600 mt-0.5 leading-relaxed">{r.message}</div>
            </div>
          ))}
        </div>
      )}

      {/* Slots */}
      <div className="space-y-2">
        {slots.map(slot => {
          const isCurrent = slot.timing === currentTiming;
          const allTaken = slot.items.every(i => i.taken);
          if (!expanded && !isCurrent && allTaken) return null;

          return (
            <div key={slot.timing}>
              <div className={`text-[10px] font-medium mb-1 ${isCurrent ? 'text-emerald-600' : 'text-gray-400'}`}>
                {slot.label} {isCurrent && '← 当前'}
              </div>
              <div className="space-y-1">
                {slot.items.map(item => (
                  <div
                    key={item.id}
                    className={`flex items-start gap-2 rounded-lg px-2 py-1.5 ${
                      item.taken ? 'bg-gray-50' : isCurrent ? 'bg-emerald-50' : 'bg-blue-50'
                    }`}
                  >
                    <span className="text-xs mt-0.5">{item.taken ? '✅' : '⬜'}</span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1">
                        <span className={`text-xs font-medium ${item.taken ? 'text-gray-400 line-through' : 'text-gray-700'}`}>
                          {item.name}
                        </span>
                        {item.dosage && <span className="text-[10px] text-gray-400">{item.dosage}</span>}
                        {item.taken_time && <span className="text-[9px] text-gray-300 ml-auto">{item.taken_time}</span>}
                      </div>
                      {item.tips.length > 0 && !item.taken && (
                        <div className="mt-0.5 space-y-0.5">
                          {item.tips.map((tip, ti) => (
                            <div key={ti} className="text-[9px] text-gray-500 leading-tight">{tip}</div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>

      {/* Expanded: other recommendations + medications + context */}
      {expanded && (
        <>
          {/* Medium/Low Recommendations */}
          {otherRecs.length > 0 && (
            <div className="mt-2 pt-2 border-t border-gray-100 space-y-1">
              <div className="text-[10px] font-medium text-gray-400 mb-1">💡 服用建议</div>
              {otherRecs.map((r, i) => (
                <div key={`rec-o-${i}`} className={`px-2 py-1.5 rounded-md border ${REC_STYLES[r.priority]}`}>
                  <div className="text-[10px] font-semibold text-gray-700">{r.icon} {r.title}</div>
                  <div className="text-[9px] text-gray-600 mt-0.5 leading-relaxed">{r.message}</div>
                </div>
              ))}
            </div>
          )}

          {/* Medications */}
          {medications.length > 0 && (
            <div className="mt-2 pt-2 border-t border-gray-100">
              <div className="text-[10px] font-medium text-gray-400 mb-1">💊 用药提醒</div>
              <div className="space-y-1">
                {medications.map((m: any) => (
                  <div key={m.id} className="flex items-center gap-2 bg-purple-50 rounded-lg px-2 py-1.5">
                    <span className="text-xs">{m.taken_today ? '✅' : '⬜'}</span>
                    <span className={`text-xs font-medium ${m.taken_today ? 'text-gray-400' : 'text-gray-700'}`}>{m.name}</span>
                    {m.dosage && <span className="text-[10px] text-gray-400">{m.dosage}</span>}
                    {m.purpose && <span className="text-[9px] text-gray-400 ml-auto">{m.purpose}</span>}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Context Summary */}
          <div className="mt-2 pt-2 border-t border-gray-100">
            <div className="text-[10px] font-medium text-gray-400 mb-1">📊 今日身体状态</div>
            <div className="flex flex-wrap gap-1.5">
              {context.sleep_quality && (
                <span className={`text-[9px] px-1.5 py-0.5 rounded ${
                  context.sleep_quality === 'good' ? 'bg-green-100 text-green-700' :
                  context.sleep_quality === 'fair' ? 'bg-yellow-100 text-yellow-700' :
                  'bg-red-100 text-red-700'
                }`}>
                  😴 睡眠{context.sleep_score ? `${context.sleep_score}分` : context.sleep_quality === 'good' ? '良好' : context.sleep_quality === 'fair' ? '一般' : '差'}
                </span>
              )}
              {context.hrv_value && (
                <span className="text-[9px] px-1.5 py-0.5 rounded bg-blue-100 text-blue-700">
                  💓 HRV {context.hrv_value}ms
                </span>
              )}
              {context.has_exercise && (
                <span className="text-[9px] px-1.5 py-0.5 rounded bg-orange-100 text-orange-700">
                  🏃 {context.exercise_types?.join('、') || '运动'}
                </span>
              )}
              {context.rhinitis_active && (
                <span className="text-[9px] px-1.5 py-0.5 rounded bg-pink-100 text-pink-700">
                  👃 鼻炎活跃{context.sneeze_count ? `(${context.sneeze_count}次喷嚏)` : ''}
                </span>
              )}
              {context.is_injection_day && (
                <span className="text-[9px] px-1.5 py-0.5 rounded bg-purple-100 text-purple-700">💉 注射日</span>
              )}
              {!context.sleep_quality && !context.hrv_value && !context.has_exercise && !context.rhinitis_active && (
                <span className="text-[9px] text-gray-400">暂无异常状态，按计划服用即可</span>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
