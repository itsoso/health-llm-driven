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
  medications: any[];
  context: {
    sleep_quality?: string;
    hrv_status?: string;
    has_exercise: boolean;
    rhinitis_active: boolean;
    is_injection_day: boolean;
  };
  summary: GuideSummary;
}

const ALERT_STYLES: Record<string, string> = {
  warning: 'bg-amber-50 border-amber-200 text-amber-800',
  important: 'bg-red-50 border-red-200 text-red-800',
  info: 'bg-blue-50 border-blue-200 text-blue-700',
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

  const { slots, alerts, summary, medications, context } = guide;

  // 当前时间段高亮
  const hour = new Date().getHours();
  const currentTiming = hour < 11 ? 'morning' : hour < 14 ? 'noon' : hour < 19 ? 'evening' : 'bedtime';

  return (
    <div className="bg-white rounded-xl p-3 border border-gray-100 shadow-sm">
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-1.5">
          <span className="text-[11px] font-semibold text-gray-600">
            💊 每日补剂指南
          </span>
          {context.rhinitis_active && <span className="text-[10px]">👃</span>}
          {context.is_injection_day && <span className="text-[10px]">💉</span>}
          {context.sleep_quality === 'poor' && <span className="text-[10px]">😴</span>}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-gray-400">
            {summary.taken}/{summary.total}
          </span>
          <div className="w-12 h-1.5 bg-gray-100 rounded-full overflow-hidden">
            <div
              className="h-full bg-emerald-400 rounded-full transition-all"
              style={{ width: `${summary.completion_rate}%` }}
            />
          </div>
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-[10px] text-gray-400 hover:text-gray-600"
          >
            {expanded ? '收起' : '展开'}
          </button>
        </div>
      </div>

      {/* Alerts */}
      {alerts.length > 0 && (
        <div className="space-y-1 mb-2">
          {alerts.map((a, i) => (
            <div
              key={i}
              className={`text-[10px] px-2 py-1 rounded-md border ${ALERT_STYLES[a.level] || ALERT_STYLES.info}`}
            >
              {a.icon} {a.message}
            </div>
          ))}
        </div>
      )}

      {/* Slots */}
      <div className="space-y-2">
        {slots.map(slot => {
          const isCurrent = slot.timing === currentTiming;
          const allTaken = slot.items.every(i => i.taken);

          // 非展开模式：只显示当前时间段或有未服用的
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
                        {item.dosage && (
                          <span className="text-[10px] text-gray-400">{item.dosage}</span>
                        )}
                        {item.taken_time && (
                          <span className="text-[9px] text-gray-300 ml-auto">{item.taken_time}</span>
                        )}
                      </div>
                      {/* Tips */}
                      {item.tips.length > 0 && !item.taken && (
                        <div className="mt-0.5 space-y-0.5">
                          {item.tips.map((tip, ti) => (
                            <div key={ti} className="text-[9px] text-gray-500 leading-tight">
                              {tip}
                            </div>
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

      {/* Medications (if any) */}
      {medications.length > 0 && expanded && (
        <div className="mt-2 pt-2 border-t border-gray-100">
          <div className="text-[10px] font-medium text-gray-400 mb-1">💊 用药提醒</div>
          <div className="space-y-1">
            {medications.map((m: any) => (
              <div key={m.id} className="flex items-center gap-2 bg-purple-50 rounded-lg px-2 py-1.5">
                <span className="text-xs">{m.taken_today ? '✅' : '⬜'}</span>
                <span className={`text-xs font-medium ${m.taken_today ? 'text-gray-400' : 'text-gray-700'}`}>
                  {m.name}
                </span>
                {m.dosage && <span className="text-[10px] text-gray-400">{m.dosage}</span>}
                {m.purpose && <span className="text-[9px] text-gray-400 ml-auto">{m.purpose}</span>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
