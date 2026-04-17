'use client';
import { useState, useEffect, useCallback } from 'react';
import { api } from '@/services/api/client';
import { dailyHealthApi } from '@/services/api/health';
import { getLocalDateStr } from '@/utils/timezone';

interface StrengthCardProps {
  exerciseType: string;
  icon: string;
  dailyTarget: number;
  color: string;         // e.g. '#3b82f6'
  colorLight: string;    // e.g. 'bg-blue-50'
  colorText: string;     // e.g. 'text-blue-600'
  colorBorder: string;   // e.g. 'border-blue-200'
  colorBar: string;      // e.g. 'bg-blue-500'
  colorBarLight: string; // e.g. 'bg-blue-200'
  quickAmounts?: number[];
}

interface ExerciseRecord {
  id: number;
  reps: number;
  sets: number;
  created_at: string;
}

export default function StrengthCard({
  exerciseType, icon, dailyTarget, color,
  colorLight, colorText, colorBorder, colorBar, colorBarLight,
  quickAmounts = [10, 15, 20, 30, 50],
}: StrengthCardProps) {
  const [todayTotal, setTodayTotal] = useState(0);
  const [todaySets, setTodaySets] = useState(0);
  const [records, setRecords] = useState<ExerciseRecord[]>([]);
  const [showDetail, setShowDetail] = useState(false);
  const [recording, setRecording] = useState(false);
  const [weekData, setWeekData] = useState<number[]>([]);
  const [coachingNote, setCoachingNote] = useState<{checklist?: string; issues?: string; title?: string} | null>(null);
  const [showCoaching, setShowCoaching] = useState(false);

  const today = getLocalDateStr();
  const pct = Math.min(100, Math.round((todayTotal / dailyTarget) * 100));

  const loadData = useCallback(async () => {
    try {
      const res = await dailyHealthApi.getTodayExercises();
      const all: any[] = Array.isArray(res.data) ? res.data : [];
      const filtered = all.filter((e: any) => e.exercise_type === exerciseType);
      setTodayTotal(filtered.reduce((s: number, e: any) => s + (e.reps || 0) * (e.sets || 1), 0));
      setTodaySets(filtered.reduce((s: number, e: any) => s + (e.sets || 1), 0));
      setRecords(filtered.map((e: any) => ({
        id: e.id, reps: e.reps || 0, sets: e.sets || 1,
        created_at: e.created_at || e.record_date,
      })));
    } catch {}

    try {
      const r = await api.get('/daily-health/exercise/me?days=14');
      const recs: any[] = Array.isArray(r.data) ? r.data : r.data?.items || [];
      const byDate: Record<string, number> = {};
      for (const e of recs.filter((e: any) => e.exercise_type === exerciseType)) {
        const d = (e.record_date || '').slice(0, 10);
        byDate[d] = (byDate[d] || 0) + (e.reps || 0) * (e.sets || 1);
      }
      // 本周一到周日
      const now = new Date();
      const dayOfWeek = (now.getDay() + 6) % 7; // 0=周一, 6=周日
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

    // 加载教练笔记
    try {
      const cn = await api.get(`/exercise-coaching/me/${encodeURIComponent(exerciseType)}`);
      if (cn.data) setCoachingNote(cn.data);
    } catch {}
  }, [exerciseType]);

  useEffect(() => { loadData(); }, [loadData]);

  const recordExercise = async (count: number, setsCount: number = 1) => {
    if (recording) return;
    setRecording(true);
    try {
      const total = count * setsCount;
      const res = await api.post('/daily-health/exercise', {
        record_date: today, exercise_type: exerciseType,
        reps: count, sets: setsCount,
        intensity: count >= 30 ? 'high' : count >= 15 ? 'medium' : 'low',
      });
      const newRecord: ExerciseRecord = {
        id: res.data?.id ?? Date.now(),
        reps: count,
        sets: setsCount,
        created_at: res.data?.created_at || new Date().toISOString(),
      };
      setTodayTotal(prev => prev + total);
      setTodaySets(prev => prev + setsCount);
      setRecords(prev => [...prev, newRecord]);
    } catch (e) { console.error('记录失败', e); }
    finally { setRecording(false); }
  };

  const deleteRecord = async (record: ExerciseRecord) => {
    // temp id from Date.now() (>1e12) — not yet synced; force reload from server
    if (!record?.id || record.id > 1e12) {
      await loadData();
      return;
    }
    if (!confirm(`删除这条 ${record.reps} 个${exerciseType}记录？`)) return;
    try {
      await api.delete(`/daily-health/exercise/${record.id}`);
      setRecords(prev => prev.filter(r => r.id !== record.id));
      setTodayTotal(prev => Math.max(0, prev - record.reps));
      setTodaySets(prev => Math.max(0, prev - 1));
    } catch (e) {
      console.error('删除失败', e);
      alert('删除失败，请重试');
    }
  };

  const maxWeek = Math.max(...weekData, dailyTarget);
  const weekDays = ['一', '二', '三', '四', '五', '六', '日'];
  const todayIdx = (new Date().getDay() + 6) % 7; // 0=周一, 6=周日

  const ringColor = color;
  const lightBg = `${color}08`;

  return (
    <div className="rounded-2xl p-4" style={{ background: `linear-gradient(135deg, ${lightBg} 0%, #ffffff 100%)`, boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-lg">{icon}</span>
          <span className="text-sm font-bold" style={{ color: '#1C1C1E' }}>{exerciseType}</span>
        </div>
        <span className="text-[10px]" style={{ color: '#8E8E93' }}>
          目标 {dailyTarget}
        </span>
      </div>

      <div className="flex items-center gap-4">
        <div className="relative shrink-0">
          <svg width={64} height={64} className="-rotate-90">
            <circle cx={32} cy={32} r={26} fill="none" stroke="#E5E5EA" strokeWidth={5} />
            <circle cx={32} cy={32} r={26} fill="none" stroke={pct >= 100 ? '#30D158' : ringColor}
              strokeWidth={5} strokeDasharray={`${2 * Math.PI * 26 * Math.min(pct, 100) / 100} ${2 * Math.PI * 26}`}
              strokeLinecap="round" className="transition-all duration-500"
              style={{ filter: `drop-shadow(0 0 3px ${ringColor}44)` }} />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-lg font-extrabold" style={{ color: '#1C1C1E' }}>{todayTotal}</span>
            <span className="text-[8px]" style={{ color: '#AEAEB2' }}>/{dailyTarget}</span>
          </div>
        </div>

        <div className="flex-1 min-w-0">
          <div className="text-[10px] mb-1" style={{ color: '#8E8E93' }}>单组快录</div>
          <div className="flex flex-wrap gap-1.5">
            {quickAmounts.map(n => (
              <button key={n} onClick={() => recordExercise(n)} disabled={recording}
                className="px-2.5 py-1 rounded-full text-[11px] font-semibold transition-all active:scale-95"
                style={{
                  background: recording ? '#E5E5EA' : `${color}10`,
                  color: recording ? '#AEAEB2' : color,
                  border: `1px solid ${recording ? '#E5E5EA' : `${color}20`}`,
                }}>+{n}</button>
            ))}
          </div>
          {/* 多组快录 */}
          <div className="text-[10px] mt-2 mb-1" style={{ color: '#8E8E93' }}>多组快录</div>
          <div className="flex flex-wrap gap-1.5">
            {[
              { sets: 3, reps: 10, label: '3×10' },
              { sets: 4, reps: 12, label: '4×12' },
              { sets: 4, reps: 15, label: '4×15' },
              { sets: 5, reps: 10, label: '5×10' },
            ].map(p => (
              <button key={p.label} onClick={() => recordExercise(p.reps, p.sets)} disabled={recording}
                className="px-2.5 py-1 rounded-full text-[11px] font-semibold transition-all active:scale-95"
                style={{
                  background: recording ? '#E5E5EA' : `${color}08`,
                  color: recording ? '#AEAEB2' : color,
                  border: `1px solid ${recording ? '#E5E5EA' : `${color}30`}`,
                }}>{p.label}</button>
            ))}
          </div>
          {todayTotal > 0 && (
            <div className="text-[10px] mt-1.5" style={{ color: '#8E8E93' }}>{todaySets}组 · {pct}%</div>
          )}
        </div>
      </div>

      {/* 今日每组详情（始终显示） */}
      {records.length > 0 && (
        <div className="mt-2.5 pt-2 space-y-1" style={{ borderTop: '1px solid #E5E5EA' }}>
          <div className="text-[9px] font-medium mb-1" style={{ color: '#AEAEB2' }}>今日记录</div>
          {records.map((r, i) => (
            <div key={r.id} className="flex items-center text-[11px] gap-2">
              <span className="shrink-0 font-medium" style={{ color: '#8E8E93' }}>{r.sets}组×{r.reps}</span>
              <span className="font-bold" style={{ color }}>{r.reps * r.sets}个</span>
              <span className="flex-1 text-right text-[10px]" style={{ color: '#AEAEB2' }}>
                {new Date(r.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
              </span>
              <button
                onClick={() => deleteRecord(r)}
                className="w-4 h-4 rounded-full flex items-center justify-center transition-all hover:bg-red-50 active:scale-90 shrink-0"
                title="删除" style={{ color: '#FF453A' }}>
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
                  {val > 0 && <span className="text-[7px] font-medium" style={{ color: isToday ? color : '#AEAEB2' }}>{val}</span>}
                  <div className="w-full rounded-sm transition-all"
                    style={{ height: `${barH}px`, background: isToday ? color : val > 0 ? `${color}40` : '#E5E5EA' }} />
                </div>
              );
            })}
          </div>
          <div className="flex gap-1 mt-0.5">
            {weekDays.map((d, i) => (
              <div key={i} className="flex-1 text-center text-[8px] font-medium"
                style={{ color: i === todayIdx ? '#1C1C1E' : '#AEAEB2' }}>
                {d}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 教练笔记（上次动作纠正要点） */}
      {coachingNote && (coachingNote.checklist || coachingNote.issues) && (
        <div className="mt-2.5 pt-2" style={{ borderTop: '1px solid #E5E5EA' }}>
          <button
            onClick={() => setShowCoaching(!showCoaching)}
            className="w-full flex items-center justify-between text-[10px] font-medium"
            style={{ color: '#FF9500' }}
          >
            <span>📋 动作要点</span>
            <span style={{ color: '#AEAEB2' }}>{showCoaching ? '收起' : '展开'}</span>
          </button>
          {showCoaching && (
            <div className="mt-1.5 space-y-1 text-[10px] leading-relaxed" style={{ color: '#475569' }}>
              {(coachingNote.checklist || coachingNote.issues || '').split('\n').filter(Boolean).map((line, i) => (
                <div key={i}>{line}</div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
