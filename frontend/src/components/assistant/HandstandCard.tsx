'use client';
/**
 * HandstandCard — 倒立卡片, 跟 StrengthCard (俯卧撑/深蹲) 并列.
 * 区别: 倒立按"持续秒数"记, 不是"次数".
 *
 * 数据走 /daily-health/exercise, 用新加的 duration_seconds 字段.
 * exercise_type='倒立', sets=1, intensity=high.
 */
import { useState, useEffect, useCallback } from 'react';
import { api } from '@/services/api/client';
import { dailyHealthApi } from '@/services/api/health';
import { getLocalDateStr } from '@/utils/timezone';

const DAILY_TARGET_SECONDS = 300;        // 默认目标 5 分钟
const QUICK_AMOUNTS = [30, 60, 90, 120]; // 秒

interface HandstandRecord {
  id: number;
  duration_seconds: number;
  created_at: string;
}

function fmtSeconds(total: number): string {
  if (total < 60) return `${total}s`;
  const m = Math.floor(total / 60);
  const s = total % 60;
  return s === 0 ? `${m}m` : `${m}m${s}s`;
}

interface Props {
  exerciseType?: string;       // 默认 '倒立'
  icon?: string;               // 默认 🤸
  dailyTarget?: number;        // 秒, 默认 300
  color?: string;              // 默认 teal
  quickAmounts?: number[];     // 秒数列表, 默认 [30,60,90,120]
}

export default function HandstandCard({
  exerciseType = '倒立',
  icon = '🤸',
  dailyTarget = DAILY_TARGET_SECONDS,
  color = '#14b8a6',           // teal-500, 与 mobile c.teal 同色系
  quickAmounts = QUICK_AMOUNTS,
}: Props) {
  const [todayTotal, setTodayTotal] = useState(0);   // 秒
  const [todaySets, setTodaySets] = useState(0);
  const [records, setRecords] = useState<HandstandRecord[]>([]);
  const [recording, setRecording] = useState(false);
  const [weekData, setWeekData] = useState<number[]>([]);  // 每天秒数

  const today = getLocalDateStr();
  const pct = Math.min(100, Math.round((todayTotal / dailyTarget) * 100));

  const loadData = useCallback(async () => {
    try {
      const res = await dailyHealthApi.getTodayExercises();
      const all: any[] = Array.isArray(res.data) ? res.data : [];
      const filtered = all.filter((e: any) => e.exercise_type === exerciseType);
      setTodayTotal(filtered.reduce((s: number, e: any) => s + (e.duration_seconds || 0), 0));
      setTodaySets(filtered.length);
      setRecords(filtered.map((e: any) => ({
        id: e.id,
        duration_seconds: e.duration_seconds || 0,
        created_at: e.created_at || e.record_date,
      })));
    } catch {}

    try {
      const r = await api.get('/daily-health/exercise/me?days=14');
      const recs: any[] = Array.isArray(r.data) ? r.data : r.data?.items || [];
      const byDate: Record<string, number> = {};
      for (const e of recs.filter((e: any) => e.exercise_type === exerciseType)) {
        const d = (e.record_date || '').slice(0, 10);
        byDate[d] = (byDate[d] || 0) + (e.duration_seconds || 0);
      }
      const now = new Date();
      const dayOfWeek = (now.getDay() + 6) % 7;
      const monday = new Date(now);
      monday.setDate(now.getDate() - dayOfWeek);
      const days: number[] = [];
      for (let i = 0; i < 7; i++) {
        const d = new Date(monday);
        d.setDate(monday.getDate() + i);
        days.push(byDate[d.toISOString().slice(0, 10)] || 0);
      }
      setWeekData(days);
    } catch {}
  }, [exerciseType]);

  useEffect(() => { loadData(); }, [loadData]);

  const recordHandstand = async (seconds: number) => {
    if (recording) return;
    setRecording(true);
    try {
      const res = await api.post('/daily-health/exercise', {
        record_date: today,
        exercise_type: exerciseType,
        duration_seconds: seconds,
        sets: 1,
        intensity: seconds >= 90 ? 'high' : seconds >= 60 ? 'medium' : 'low',
      });
      const newRecord: HandstandRecord = {
        id: res.data?.id ?? Date.now(),
        duration_seconds: seconds,
        created_at: res.data?.created_at || new Date().toISOString(),
      };
      setTodayTotal(prev => prev + seconds);
      setTodaySets(prev => prev + 1);
      setRecords(prev => [...prev, newRecord]);
    } catch (e) {
      console.error('记录失败', e);
    } finally {
      setRecording(false);
    }
  };

  const deleteRecord = async (record: HandstandRecord) => {
    if (!record?.id || record.id > 1e12) {
      await loadData();
      return;
    }
    if (!confirm(`删除这条 ${fmtSeconds(record.duration_seconds)} 倒立记录？`)) return;
    try {
      await api.delete(`/daily-health/exercise/${record.id}`);
      setRecords(prev => prev.filter(r => r.id !== record.id));
      setTodayTotal(prev => Math.max(0, prev - record.duration_seconds));
      setTodaySets(prev => Math.max(0, prev - 1));
    } catch (e) {
      console.error('删除失败', e);
      alert('删除失败，请重试');
    }
  };

  const maxWeek = Math.max(...weekData, dailyTarget);
  const weekDays = ['一', '二', '三', '四', '五', '六', '日'];
  const todayIdx = (new Date().getDay() + 6) % 7;
  const lightBg = `${color}08`;

  return (
    <div
      className="rounded-2xl p-4"
      style={{ background: `linear-gradient(135deg, ${lightBg} 0%, #ffffff 100%)`, boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-lg">{icon}</span>
          <span className="text-sm font-bold" style={{ color: '#1C1C1E' }}>{exerciseType}</span>
        </div>
        <span className="text-[10px]" style={{ color: '#8E8E93' }}>
          目标 {fmtSeconds(dailyTarget)}
        </span>
      </div>

      {/* Ring + quick add */}
      <div className="flex items-center gap-4">
        <div className="relative shrink-0">
          <svg width={64} height={64} className="-rotate-90">
            <circle cx={32} cy={32} r={26} fill="none" stroke="#E5E5EA" strokeWidth={5} />
            <circle
              cx={32} cy={32} r={26} fill="none"
              stroke={pct >= 100 ? '#30D158' : color}
              strokeWidth={5}
              strokeDasharray={`${(2 * Math.PI * 26 * Math.min(pct, 100)) / 100} ${2 * Math.PI * 26}`}
              strokeLinecap="round"
              className="transition-all duration-500"
              style={{ filter: `drop-shadow(0 0 3px ${color}44)` }}
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-base font-extrabold" style={{ color: '#1C1C1E' }}>{fmtSeconds(todayTotal)}</span>
            <span className="text-[8px]" style={{ color: '#AEAEB2' }}>/{fmtSeconds(dailyTarget)}</span>
          </div>
        </div>

        <div className="flex-1 min-w-0">
          <div className="text-[10px] mb-1" style={{ color: '#8E8E93' }}>单次快录</div>
          <div className="flex flex-wrap gap-1.5">
            {quickAmounts.map(n => (
              <button
                key={n}
                onClick={() => recordHandstand(n)}
                disabled={recording}
                className="px-2.5 py-1 rounded-full text-[11px] font-semibold transition-all active:scale-95"
                style={{
                  background: recording ? '#E5E5EA' : `${color}10`,
                  color: recording ? '#AEAEB2' : color,
                  border: `1px solid ${recording ? '#E5E5EA' : `${color}20`}`,
                }}
              >
                +{n}s
              </button>
            ))}
          </div>
          {todayTotal > 0 && (
            <div className="text-[10px] mt-1.5" style={{ color: '#8E8E93' }}>{todaySets} 次 · {pct}%</div>
          )}
        </div>
      </div>

      {/* 今日每条详情 */}
      {records.length > 0 && (
        <div className="mt-2.5 pt-2 space-y-1" style={{ borderTop: '1px solid #E5E5EA' }}>
          <div className="text-[9px] font-medium mb-1" style={{ color: '#AEAEB2' }}>今日记录</div>
          {records.map((r) => (
            <div key={r.id} className="flex items-center text-[11px] gap-2">
              <span className="font-bold" style={{ color }}>{fmtSeconds(r.duration_seconds)}</span>
              <span className="flex-1 text-right text-[10px]" style={{ color: '#AEAEB2' }}>
                {new Date(r.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
              </span>
              <button
                onClick={() => deleteRecord(r)}
                className="w-4 h-4 rounded-full flex items-center justify-center transition-all hover:bg-red-50 active:scale-90 shrink-0"
                title="删除"
                style={{ color: '#FF453A' }}
              >
                <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          ))}
        </div>
      )}

      {/* 本周柱状图 */}
      {weekData.length > 0 && (
        <div className="mt-2.5 pt-2" style={{ borderTop: '1px solid #E5E5EA' }}>
          <div className="flex items-end gap-1 h-7">
            {weekData.map((val, i) => {
              const barH = maxWeek > 0 ? Math.max(2, (val / maxWeek) * 28) : 2;
              const isToday = i === todayIdx;
              return (
                <div key={i} className="flex-1 flex flex-col items-center gap-0.5">
                  {val > 0 && (
                    <span className="text-[7px] font-medium" style={{ color: isToday ? color : '#AEAEB2' }}>
                      {fmtSeconds(val)}
                    </span>
                  )}
                  <div
                    className="w-full rounded-sm transition-all"
                    style={{ height: `${barH}px`, background: isToday ? color : val > 0 ? `${color}40` : '#E5E5EA' }}
                  />
                </div>
              );
            })}
          </div>
          <div className="flex gap-1 mt-0.5">
            {weekDays.map((d, i) => (
              <div
                key={i}
                className="flex-1 text-center text-[8px] font-medium"
                style={{ color: i === todayIdx ? '#1C1C1E' : '#AEAEB2' }}
              >
                {d}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
