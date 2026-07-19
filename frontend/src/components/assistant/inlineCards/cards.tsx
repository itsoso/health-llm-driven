'use client';
import React from 'react';
import Image from 'next/image';
import { CardShell } from './CardShell';
import type { CardSpec } from './types';
import { api } from '@/services/api/client';

// ────────────────────────────────────────────────────────────────
// 1. VitalsCard - 今日综合生理
// ────────────────────────────────────────────────────────────────
interface VitalsData {
  sleep?: string; hr?: string; hrv?: string; battery?: string; steps?: string; stress?: string;
}
const VITAL_ITEMS = [
  { k: 'sleep' as const,   icon: '🌙', color: '#BF5AF2', label: '睡眠' },
  { k: 'hr' as const,      icon: '❤️', color: '#FF375F', label: '心率' },
  { k: 'hrv' as const,     icon: '🫀', color: '#5AC8FA', label: 'HRV' },
  { k: 'battery' as const, icon: '⚡', color: '#30D158', label: '电量' },
  { k: 'steps' as const,   icon: '🚶', color: '#FF6723', label: '步数' },
  { k: 'stress' as const,  icon: '☁️', color: '#FF9F0A', label: '压力' },
];
export function VitalsCardView(d: VitalsData) {
  return (
    <CardShell emoji="📊" title="今日生理数据">
      <div className="flex flex-wrap gap-3">
        {VITAL_ITEMS.filter(it => (d as any)[it.k]).map(it => (
          <div key={it.k} className="flex flex-col items-center min-w-[50px]">
            <span className="text-xs">{it.icon}</span>
            <span className="text-sm font-bold tabular-nums" style={{ color: it.color }}>{(d as any)[it.k]}</span>
            <span className="text-[9px] text-slate-400">{it.label}</span>
          </div>
        ))}
      </div>
    </CardShell>
  );
}
export const VitalsCardSpec: CardSpec<VitalsData> = {
  type: 'vitals', label: '今日综合',
  match({ query_lower }) {
    if (/记录|打卡|吃了|喝了|服药|补剂|体重/.test(query_lower)) return null;
    if (/综合|今日如何|整体|所有数据|健康如何/.test(query_lower)) return 10;
    const hits = ['睡眠','心率','hrv','电量','步数','压力'].filter(k => query_lower.includes(k)).length;
    return hits >= 2 ? 8 : null;
  },
  build({ data }) {
    const g = data.garmin;
    const d: VitalsData = {};
    if (g?.total_sleep_duration) d.sleep = `${(g.total_sleep_duration / 60).toFixed(1)}h`;
    if (g?.resting_heart_rate) d.hr = `${g.resting_heart_rate}bpm`;
    if (g?.hrv != null) d.hrv = `${Number(g.hrv).toFixed(1)}ms`;
    if (g?.body_battery_most_charged) d.battery = `${g.body_battery_most_charged}`;
    if (g?.steps) d.steps = g.steps.toLocaleString();
    if (g?.average_stress_level != null) d.stress = `${g.average_stress_level}`;
    if (Object.keys(d).length === 0 && data.score?.total_score) d.sleep = `评分${data.score.total_score}`;
    return Object.keys(d).length > 0 ? d : null;
  },
  render: (d) => <VitalsCardView {...d} />,
};

// ────────────────────────────────────────────────────────────────
// 2. SleepCard
// ────────────────────────────────────────────────────────────────
interface SleepData {
  score?: number; duration_h?: number;
  deep_min?: number; rem_min?: number; light_min?: number; awake_min?: number;
}
function ScoreRing({ score, size = 52 }: { score: number; size?: number }) {
  const sw = 5, r = (size - sw) / 2, c = 2 * Math.PI * r;
  const off = c * (1 - Math.min(score / 100, 1));
  const color = score >= 80 ? '#30D158' : score >= 60 ? '#FF9F0A' : '#FF453A';
  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size}>
        <circle cx={size/2} cy={size/2} r={r} stroke="#F2F2F7" strokeWidth={sw} fill="none" />
        <circle cx={size/2} cy={size/2} r={r} stroke={color} strokeWidth={sw} fill="none"
                strokeLinecap="round" strokeDasharray={c} strokeDashoffset={off}
                transform={`rotate(-90 ${size/2} ${size/2})`} />
      </svg>
      <span className="absolute text-base font-extrabold tabular-nums" style={{ color }}>{score}</span>
    </div>
  );
}
function fmtMin(m?: number) {
  if (m == null) return null;
  const h = Math.floor(m / 60), r = m % 60;
  return h > 0 ? `${h}h${r}m` : `${r}m`;
}
export function SleepCardView({ score, duration_h, deep_min, rem_min, light_min, awake_min }: SleepData) {
  const stages = [
    { label: '深睡', min: deep_min, color: '#5856D6' },
    { label: 'REM', min: rem_min, color: '#BF5AF2' },
    { label: '浅睡', min: light_min, color: '#AF52DE' },
    { label: '清醒', min: awake_min, color: '#FF9F0A' },
  ].filter(s => s.min != null);
  return (
    <CardShell emoji="🌙" title="睡眠分析" bg="#FAF5FF" border="#E9D5FF">
      <div className="flex items-center gap-3">
        {score != null && <ScoreRing score={score} />}
        <div className="flex-1 min-w-0">
          {duration_h != null && <div className="text-lg font-extrabold text-slate-900 tabular-nums">{duration_h.toFixed(1)}h</div>}
          <div className="flex flex-wrap gap-2.5 mt-1">
            {stages.map(s => (
              <div key={s.label} className="flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full" style={{ background: s.color }} />
                <span className="text-[10px] text-slate-500">{s.label}</span>
                <span className="text-[10px] font-semibold text-slate-700 tabular-nums">{fmtMin(s.min)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </CardShell>
  );
}
export const SleepCardSpec: CardSpec<SleepData> = {
  type: 'sleep', label: '睡眠分析',
  match({ query_lower }) {
    if (/记录|打卡/.test(query_lower)) return null;
    return /睡眠|深睡|rem|浅睡|睡得|入睡|清醒/.test(query_lower) ? 20 : null;
  },
  build({ data }) {
    const g = data.garmin; if (!g) return null;
    const d: SleepData = {};
    if (g.sleep_score != null) d.score = g.sleep_score;
    if (g.total_sleep_duration) d.duration_h = g.total_sleep_duration / 60;
    if (g.deep_sleep_duration != null) d.deep_min = Math.round(g.deep_sleep_duration);
    if (g.rem_sleep_duration != null) d.rem_min = Math.round(g.rem_sleep_duration);
    if (g.light_sleep_duration != null) d.light_min = Math.round(g.light_sleep_duration);
    if (g.awake_duration != null) d.awake_min = Math.round(g.awake_duration);
    return Object.keys(d).length > 0 ? d : null;
  },
  render: (d) => <SleepCardView {...d} />,
};

// ────────────────────────────────────────────────────────────────
// 3. WeightCard
// ────────────────────────────────────────────────────────────────
interface WeightData { current_kg?: number; trend_7d?: number[]; change_7d_kg?: number; bmi?: number; }
function Sparkline({ points }: { points: number[] }) {
  if (points.length < 2) return null;
  const w = 100, h = 32, pad = 2;
  const min = Math.min(...points), max = Math.max(...points);
  const range = max - min || 1;
  const pts = points.map((v, i) => {
    const x = (i / (points.length - 1)) * (w - pad * 2) + pad;
    const y = h - pad - ((v - min) / range) * (h - pad * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  const trend = points[points.length - 1] - points[0];
  const color = trend < -0.1 ? '#30D158' : trend > 0.1 ? '#FF453A' : '#8E8E93';
  const [lx, ly] = pts.split(' ').pop()!.split(',').map(Number);
  return (
    <svg width={w} height={h}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={lx} cy={ly} r={2.5} fill={color} />
    </svg>
  );
}
export function WeightCardView({ current_kg, trend_7d, change_7d_kg, bmi }: WeightData) {
  const up = (change_7d_kg ?? 0) > 0;
  const changeColor = change_7d_kg == null || Math.abs(change_7d_kg) < 0.05
    ? '#8E8E93' : up ? '#FF453A' : '#30D158';
  return (
    <CardShell emoji="⚖️" title="体重" bg="#F0FFFD" border="#B2F5EA">
      <div className="flex items-center gap-3">
        <div className="flex-1">
          <div className="text-2xl font-extrabold text-slate-900 tabular-nums">
            {current_kg != null ? `${current_kg.toFixed(1)}kg` : '--'}
          </div>
          <div className="flex items-center gap-3 mt-0.5">
            {change_7d_kg != null && (
              <span className="text-[11px] font-semibold tabular-nums" style={{ color: changeColor }}>
                {up ? '↑' : '↓'} {Math.abs(change_7d_kg).toFixed(1)}kg · 7天
              </span>
            )}
            {bmi != null && <span className="text-[10px] text-slate-400">BMI {bmi.toFixed(1)}</span>}
          </div>
        </div>
        {trend_7d && trend_7d.length >= 2 && <Sparkline points={trend_7d} />}
      </div>
    </CardShell>
  );
}
export const WeightCardSpec: CardSpec<WeightData> = {
  type: 'weight', label: '体重',
  match({ query_lower }) {
    if (/记录|打卡|称/.test(query_lower) && !/趋势|变化|多少|现在/.test(query_lower)) return null;
    return /体重|bmi|胖|瘦|减肥|减脂/.test(query_lower) ? 15 : null;
  },
  async build({ api }) {
    try {
      const res = await api.get('/weight/me?limit=7');
      const recs: any[] = res.data || [];
      if (recs.length === 0) return null;
      const sorted = [...recs].sort((a, b) => (a.record_date || '').localeCompare(b.record_date || ''));
      const vals = sorted.map(r => r.weight_kg).filter(v => v != null);
      if (vals.length === 0) return null;
      const cur = vals[vals.length - 1];
      const d: WeightData = { current_kg: cur, trend_7d: vals };
      if (vals.length >= 2) d.change_7d_kg = cur - vals[0];
      if (sorted[sorted.length - 1]?.bmi) d.bmi = sorted[sorted.length - 1].bmi;
      return d;
    } catch { return null; }
  },
  render: (d) => <WeightCardView {...d} />,
};

// ────────────────────────────────────────────────────────────────
// 4. SupplementCard
// ────────────────────────────────────────────────────────────────
interface SupplementData { checked: number; total: number; pending_names: string[]; }
export function SupplementCardView({ checked, total, pending_names }: SupplementData) {
  const pct = total > 0 ? Math.round((checked / total) * 100) : 0;
  const barColor = pct >= 80 ? '#30D158' : pct >= 50 ? '#FF9F0A' : '#FF453A';
  return (
    <CardShell emoji="💊" title="补剂打卡" badge={`${checked}/${total}`} badgeColor={barColor}
               bg="#FAF5FF" border="#E9D5FF">
      <div className="h-1.5 bg-slate-200 rounded-full overflow-hidden">
        <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, background: barColor }} />
      </div>
      {pending_names.length > 0 && (
        <div className="mt-2">
          <span className="text-[10px] text-slate-500">未打卡：</span>
          <div className="flex flex-wrap gap-1 mt-1">
            {pending_names.slice(0, 4).map(n => (
              <span key={n} className="px-1.5 py-0.5 rounded-lg bg-slate-100 text-[10px] text-slate-700 max-w-[120px] truncate">
                ⏳ {n}
              </span>
            ))}
            {pending_names.length > 4 && <span className="text-[10px] text-slate-400 self-center">+{pending_names.length - 4}</span>}
          </div>
        </div>
      )}
      {pending_names.length === 0 && total > 0 && (
        <div className="mt-2 text-[11px] font-semibold text-emerald-600">✅ 今日补剂已全部打卡</div>
      )}
    </CardShell>
  );
}
export const SupplementCardSpec: CardSpec<SupplementData> = {
  type: 'supplement_status', label: '补剂打卡',
  match({ query_lower }) {
    return /补剂吃了吗|补剂进度|今天吃了什么补剂|补剂状态|补剂打卡|未吃的补剂/.test(query_lower) ? 15 : null;
  },
  async build({ api }) {
    try {
      const res = await api.get('/supplements/me/today-status');
      const list: any[] = res.data || [];
      if (list.length === 0) return null;
      const seen = new Set<string>();
      const dedup = list.filter(s => {
        const key = `${s.supplement?.name || s.supplement_name || s.name}_${s.supplement?.timing || s.timing || 'morning'}`;
        if (seen.has(key)) return false;
        seen.add(key); return true;
      });
      const checked = dedup.filter(s => s.record?.taken || s.is_taken || s.checked).length;
      const pending_names = dedup.filter(s => !(s.record?.taken || s.is_taken || s.checked))
                                 .map(s => s.supplement?.name || s.supplement_name || s.name || '未知');
      return { checked, total: dedup.length, pending_names };
    } catch { return null; }
  },
  render: (d) => <SupplementCardView {...d} />,
};

// ────────────────────────────────────────────────────────────────
// 5. WeatherCard
// ────────────────────────────────────────────────────────────────
interface WeatherData { temperature?: number; weather?: string; city?: string; aqi?: number; pm25?: number; advice?: string; }
function aqiLabel(aqi?: number) {
  if (aqi == null) return { label: '—', color: '#8E8E93' };
  if (aqi <= 50) return { label: '优', color: '#30D158' };
  if (aqi <= 100) return { label: '良', color: '#FFCC00' };
  if (aqi <= 150) return { label: '轻度', color: '#FF9F0A' };
  if (aqi <= 200) return { label: '中度', color: '#FF6723' };
  if (aqi <= 300) return { label: '重度', color: '#FF453A' };
  return { label: '严重', color: '#AF52DE' };
}
function exerciseAdvice(aqi?: number, temp?: number) {
  if (aqi != null && aqi > 150) return '不建议户外运动';
  if (temp != null && temp > 32) return '避开正午，傍晚运动';
  if (temp != null && temp < 5) return '注意保暖，可室内';
  if (aqi != null && aqi <= 50) return '适合户外运动';
  return '适中，注意量力';
}
export function WeatherCardView({ temperature, weather, city, aqi, pm25, advice }: WeatherData) {
  const q = aqiLabel(aqi);
  return (
    <CardShell emoji="🌤️" title={city ? `${city}环境` : '环境'} bg="#F0F9FF" border="#BAE6FD">
      <div className="flex items-center justify-between">
        <div className="flex items-baseline gap-1.5">
          <span className="text-3xl font-extrabold text-slate-900 tabular-nums">
            {temperature != null ? `${Math.round(temperature)}°` : '--'}
          </span>
          {weather && <span className="text-xs text-slate-500">{weather}</span>}
        </div>
        <div className="text-right">
          <div className="flex items-center gap-1 justify-end">
            <span className="w-2 h-2 rounded-full" style={{ background: q.color }} />
            <span className="text-base font-extrabold tabular-nums" style={{ color: q.color }}>{aqi ?? '--'}</span>
            <span className="text-[11px] font-semibold" style={{ color: q.color }}>{q.label}</span>
          </div>
          {pm25 != null && <div className="text-[10px] text-slate-400 tabular-nums">PM2.5 {pm25}</div>}
        </div>
      </div>
      <div className="flex items-center gap-1 mt-2 text-[11px] text-slate-500">
        <span className="text-emerald-500">🏃</span>
        {advice || exerciseAdvice(aqi, temperature)}
      </div>
    </CardShell>
  );
}
export const WeatherCardSpec: CardSpec<WeatherData> = {
  type: 'weather', label: '环境',
  match({ query_lower }) {
    return /天气|气温|温度|aqi|空气|pm2|户外|适合跑|适合运动/.test(query_lower) ? 15 : null;
  },
  build({ data }) {
    const w = data.weather?.weather ?? data.weather;
    const a = data.aqi;
    const city = data.profile?.manual_location?.city || data.profile?.detected_location?.city || data.profile?.city;
    const d: WeatherData = {};
    if (w?.temperature != null) d.temperature = w.temperature;
    if (w?.weather) d.weather = w.weather;
    if (city) d.city = city;
    if (a?.aqi != null) d.aqi = a.aqi;
    if (a?.pm25 != null) d.pm25 = a.pm25;
    return Object.keys(d).length > 0 ? d : null;
  },
  render: (d) => <WeatherCardView {...d} />,
};

// ────────────────────────────────────────────────────────────────
// 6. BPCard (ACC/AHA 2017 分级)
// ────────────────────────────────────────────────────────────────
interface BPSafetyGuidance {
  severity: 'high';
  title?: string;
  recheck_instruction: string;
  emergency_instruction: string;
  action_path: string;
}
interface BPData {
  systolic: number;
  diastolic: number;
  pulse?: number;
  measured_at?: string;
  category?: string;
  category_color?: string;
  safety_guidance?: BPSafetyGuidance | null;
}
const BP_FALLBACK_COLOR = '#64748B';

export function BPCardView({ systolic, diastolic, pulse, measured_at, category, category_color, safety_guidance }: BPData) {
  const displayCategory = category || '未分类';
  const displayColor = category_color || BP_FALLBACK_COLOR;
  return (
    <CardShell emoji="🩺" title="血压" badge={displayCategory} badgeColor={displayColor} bg="#FFF5F5" border="#FECACA">
      <div className="flex items-center justify-between">
        <div className="flex items-baseline gap-1.5">
          <span className="text-2xl font-extrabold tabular-nums" style={{ color: displayColor }}>
            {systolic}<span className="text-lg font-normal text-slate-400"> / </span>{diastolic}
          </span>
          <span className="text-[10px] text-slate-400">mmHg</span>
        </div>
        {pulse != null && (
          <div className="text-right">
            <div className="text-lg font-bold text-slate-900 tabular-nums">{pulse}</div>
            <div className="text-[9px] text-slate-400">脉搏 bpm</div>
          </div>
        )}
      </div>
      {measured_at && <div className="text-[10px] text-slate-400 mt-1">{measured_at}</div>}
      {safety_guidance && (
        <div className="mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs leading-5 text-red-900" role="alert">
          <div>{safety_guidance.recheck_instruction}</div>
          <div className="mt-1">{safety_guidance.emergency_instruction}</div>
          <a className="mt-1 inline-block font-semibold text-red-800 underline" href={safety_guidance.action_path}>复测后记录</a>
        </div>
      )}
    </CardShell>
  );
}
export const BPCardSpec: CardSpec<BPData> = {
  type: 'blood_pressure', label: '血压',
  match({ query_lower }) {
    return /血压|bp|收缩压|舒张压|高压|低压/.test(query_lower) ? 15 : null;
  },
  async build({ api }) {
    try {
      const res = await api.get('/blood-pressure/records/me', { params: { limit: 1 } });
      const r = Array.isArray(res.data) ? res.data[0] : null;
      if (!r || r.systolic == null || r.diastolic == null) return null;
      return {
        systolic: r.systolic, diastolic: r.diastolic, pulse: r.pulse,
        measured_at: r.record_date ? String(r.record_date) : undefined,
        category: r.category || undefined,
        category_color: r.category_color || undefined,
        safety_guidance: r.safety_guidance || undefined,
      } as BPData;
    } catch { return null; }
  },
  render: (d) => <BPCardView {...d} />,
};

// ────────────────────────────────────────────────────────────────
// 7. ScoreCard
// ────────────────────────────────────────────────────────────────
interface ScoreData { score: number; label?: string; sub?: string; }
export function ScoreCardView({ score, label, sub }: ScoreData) {
  return (
    <CardShell emoji="✨" title={label || '健康评分'}>
      <div className="flex items-center gap-3">
        <ScoreRing score={score} size={56} />
        <div className="flex-1 min-w-0">
          <div className="text-sm font-bold text-slate-900">{label || '健康评分'}</div>
          {sub && <div className="text-[10px] text-slate-400 mt-0.5">{sub}</div>}
        </div>
      </div>
    </CardShell>
  );
}
export const ScoreCardSpec: CardSpec<ScoreData> = {
  type: 'score', label: '健康评分',
  match({ query_lower }) { return /评分|打分|健康分|分数|健康度/.test(query_lower) ? 15 : null; },
  build({ data }) {
    const s = data.score?.total_score; if (s == null) return null;
    const subs: string[] = [];
    if (data.score?.sleep_score) subs.push(`睡眠 ${data.score.sleep_score}`);
    if (data.score?.activity_score) subs.push(`活动 ${data.score.activity_score}`);
    if (data.score?.recovery_score) subs.push(`恢复 ${data.score.recovery_score}`);
    return { score: s, sub: subs.join(' · ') || undefined };
  },
  render: (d) => <ScoreCardView {...d} />,
};

// ────────────────────────────────────────────────────────────────
// 8. RecordCard
// ────────────────────────────────────────────────────────────────
interface RecordData { type: string; detail: string; }
const RECORD_ICONS: Record<string, { emoji: string; bg: string; border: string }> = {
  water:          { emoji: '💧', bg: '#F0FAFF', border: '#BAE6FD' },
  supplement:     { emoji: '💊', bg: '#FAF5FF', border: '#E9D5FF' },
  diet:           { emoji: '🍽️', bg: '#FFF7F0', border: '#FED7AA' },
  exercise:       { emoji: '🏃', bg: '#FFF5F7', border: '#FECACA' },
  weight:         { emoji: '⚖️', bg: '#F0FFFD', border: '#B2F5EA' },
  blood_pressure: { emoji: '🩺', bg: '#FFF5F5', border: '#FECACA' },
  rhinitis:       { emoji: '👃', bg: '#F0F9FF', border: '#BAE6FD' },
  checkin:        { emoji: '✅', bg: '#F0FFF4', border: '#BBF7D0' },
  medication:     { emoji: '🧪', bg: '#FAF5FF', border: '#E9D5FF' },
  default:        { emoji: '✅', bg: '#F0FFF4', border: '#BBF7D0' },
};
export function RecordCardView({ type, detail }: RecordData) {
  const cfg = RECORD_ICONS[type] || RECORD_ICONS.default;
  return (
    <div className="rounded-2xl px-3 py-2 my-1 flex items-center gap-2 shadow-sm"
         style={{ background: cfg.bg, border: `1px solid ${cfg.border}` }}>
      <span className="text-sm">{cfg.emoji}</span>
      <span className="text-sm text-slate-800 flex-1">{detail}</span>
      <span className="text-sm text-emerald-500">✓</span>
    </div>
  );
}
export const RecordCardSpec: CardSpec<RecordData> = {
  type: 'record', label: '记录确认',
  match({ query_lower, toolsUsed }) {
    if (toolsUsed.has('health_record')) return 20;
    if (/记录|打卡|吃了|喝了|喝水|服药|补剂.*吃|刚吃|刚喝|体重是|血压是|洗鼻了|喷嚏/.test(query_lower)) return 12;
    return null;
  },
  build({ query_lower }) {
    let type = 'default';
    if (/喝水|喝了.*水/.test(query_lower)) type = 'water';
    else if (/补剂|服药/.test(query_lower)) type = 'supplement';
    else if (/吃了|早餐|午餐|晚餐|加餐/.test(query_lower)) type = 'diet';
    else if (/体重/.test(query_lower)) type = 'weight';
    else if (/血压/.test(query_lower)) type = 'blood_pressure';
    else if (/喷嚏|洗鼻|鼻炎/.test(query_lower)) type = 'rhinitis';
    else if (/跑|运动|锻炼|训练/.test(query_lower)) type = 'exercise';
    return { type, detail: '已记录' };
  },
  render: (d) => <RecordCardView {...d} />,
};

// ────────────────────────────────────────────────────────────────
// 9. RecordQualityCard - 记录后的个人化建议
// ────────────────────────────────────────────────────────────────
interface RecordQualityMetric { label?: string; value?: string; }
interface RecordQualityData {
  domain?: string;
  title?: string;
  summary?: string;
  metrics?: RecordQualityMetric[];
  progress?: {
    calories_total?: number;
    meals_count?: number;
    protein_total_g?: number;
    protein_target_g?: number;
    remaining_protein_g?: number;
  };
  primary_judgement?: string;
  personal_cautions?: string[];
  next_action?: string;
  boundary?: string;
}
function recordQualityTheme(domain?: string) {
  if (domain === 'exercise') {
    return { emoji: '🏃', bg: '#FFF5F7', border: '#FECACA', badge: '运动', badgeColor: '#BE185D' };
  }
  return { emoji: '🍽️', bg: '#F0FDF4', border: '#BBF7D0', badge: '饮食', badgeColor: '#059669' };
}
function safeTextList(value?: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => String(item || '').trim())
    .filter(Boolean)
    .slice(0, 2);
}
export function RecordQualityCardView(data: RecordQualityData) {
  const theme = recordQualityTheme(data.domain);
  const metrics = Array.isArray(data.metrics) ? data.metrics.filter(m => m?.label && m?.value).slice(0, 5) : [];
  const cautions = safeTextList(data.personal_cautions);
  const progress = data.progress;
  const hasProteinProgress = progress?.protein_total_g != null && progress?.protein_target_g != null;
  return (
    <CardShell
      emoji={theme.emoji}
      title={data.title || '已记录'}
      badge={theme.badge}
      badgeColor={theme.badgeColor}
      bg={theme.bg}
      border={theme.border}
    >
      {data.summary && <div className="text-sm font-semibold leading-5 text-slate-900">{data.summary}</div>}
      {metrics.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {metrics.map((m) => (
            <span key={`${m.label}-${m.value}`} className="rounded-lg bg-white px-2 py-1 text-[11px] font-semibold text-slate-700 ring-1 ring-emerald-100">
              <span className="text-slate-400">{m.label}</span> {m.value}
            </span>
          ))}
        </div>
      )}
      {hasProteinProgress && (
        <div className="mt-2 rounded-xl bg-emerald-50 px-3 py-2 ring-1 ring-emerald-100">
          <div className="flex items-center justify-between gap-3">
            <span className="text-[11px] font-semibold text-emerald-700">今日蛋白</span>
            <span className="text-xs font-extrabold tabular-nums text-emerald-800">
              {Math.round(progress!.protein_total_g!)}/{Math.round(progress!.protein_target_g!)}g
            </span>
          </div>
          <div className="mt-1 text-[10px] leading-4 text-slate-500">
            {[
              progress?.calories_total != null ? `已记 ${Math.round(progress.calories_total)} kcal` : null,
              progress?.meals_count != null ? `${progress.meals_count} 餐` : null,
              progress?.remaining_protein_g != null ? `还差约 ${Math.round(progress.remaining_protein_g)}g 蛋白` : null,
            ].filter(Boolean).join(' · ')}
          </div>
        </div>
      )}
      {data.primary_judgement && (
        <div className="mt-2 text-xs font-bold leading-5 text-slate-900">{data.primary_judgement}</div>
      )}
      {cautions.length > 0 && (
        <div className="mt-2 space-y-1">
          {cautions.map((item) => (
            <div key={item} className="rounded-xl bg-white px-3 py-2 text-[11px] leading-5 text-amber-800 ring-1 ring-amber-100">
              {item}
            </div>
          ))}
        </div>
      )}
      {data.next_action && (
        <div className="mt-2 rounded-xl bg-white px-3 py-2 text-[11px] font-bold leading-5 text-emerald-700 ring-1 ring-emerald-100">
          下一步：{data.next_action}
        </div>
      )}
      <div className="mt-2 text-[10px] leading-4 text-slate-400">
        {data.boundary || '健康管理建议，不替代医生诊断、处方或治疗。'}
      </div>
    </CardShell>
  );
}
export const RecordQualityCardSpec: CardSpec<RecordQualityData> = {
  type: 'record_quality', label: '记录后建议',
  match() { return null; },
  build() { return null; },
  render: (d) => <RecordQualityCardView {...d} />,
};

// ────────────────────────────────────────────────────────────────
// 10. DietCard - 今日饮食
// ────────────────────────────────────────────────────────────────
interface DietData {
  calories?: number;
  protein?: number;
  carbs?: number;
  fat?: number;
  fiber?: number;
  meals_count?: number;
  meals_by_type?: Record<string, number>;
}
const MEAL_META: Record<string, { label: string; emoji: string; color: string }> = {
  breakfast: { label: '早餐', emoji: '☀️', color: '#FF9F0A' },
  lunch:     { label: '午餐', emoji: '🍚', color: '#FF6723' },
  dinner:    { label: '晚餐', emoji: '🌙', color: '#BF5AF2' },
  snack:     { label: '加餐', emoji: '🍎', color: '#5AC8FA' },
};
function todayISO(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
export function DietCardView({
  calories, protein, carbs, fat, fiber, meals_count, meals_by_type,
}: DietData) {
  const macros = [
    { k: 'protein', label: '蛋白', value: protein, color: '#FF375F' },
    { k: 'carbs',   label: '碳水', value: carbs,   color: '#FF9F0A' },
    { k: 'fat',     label: '脂肪', value: fat,     color: '#BF5AF2' },
    { k: 'fiber',   label: '纤维', value: fiber,   color: '#30D158' },
  ].filter((m) => m.value != null && m.value > 0);
  const hasMeals = meals_by_type && Object.keys(meals_by_type).length > 0;
  return (
    <CardShell emoji="🍽️" title="今日饮食" bg="#FFF7F0" border="#FED7AA">
      <div className="flex items-baseline justify-between">
        <div>
          <span className="text-2xl font-extrabold text-slate-900 tabular-nums">
            {calories != null ? Math.round(calories) : '--'}
          </span>
          <span className="text-xs text-slate-400 ml-1">kcal</span>
        </div>
        {meals_count != null && meals_count > 0 && (
          <span className="text-[11px] text-slate-400">{meals_count} 餐</span>
        )}
      </div>
      {macros.length > 0 && (
        <div className="flex flex-wrap gap-3 mt-1.5">
          {macros.map((m) => (
            <div key={m.k} className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full" style={{ background: m.color }} />
              <span className="text-[10px] text-slate-500">{m.label}</span>
              <span className="text-[11px] font-bold tabular-nums" style={{ color: m.color }}>
                {m.value!.toFixed(0)}g
              </span>
            </div>
          ))}
        </div>
      )}
      {hasMeals && (
        <div className="flex flex-wrap gap-3 mt-2">
          {(['breakfast', 'lunch', 'dinner', 'snack'] as const).map((t) => {
            const cal = meals_by_type?.[t];
            if (cal == null || cal === 0) return null;
            const meta = MEAL_META[t];
            return (
              <div key={t} className="flex items-center gap-1">
                <span className="text-[11px]">{meta.emoji}</span>
                <span className="text-[10px] text-slate-500">{meta.label}</span>
                <span className="text-[11px] font-bold tabular-nums" style={{ color: meta.color }}>
                  {Math.round(cal)}
                </span>
              </div>
            );
          })}
        </div>
      )}
      {!hasMeals && (!calories || calories === 0) && (
        <div className="text-[11px] text-slate-400 mt-1">今日暂无饮食记录 · 说「我刚吃了…」即可记上</div>
      )}
    </CardShell>
  );
}
export const DietCardSpec: CardSpec<DietData> = {
  type: 'diet', label: '今日饮食',
  match({ query_lower, toolsUsed }) {
    if (/刚吃|刚喝|吃了|喝了|记录.*饮食|记录.*吃/.test(query_lower)) return null;
    if (toolsUsed.has('record_diet')) return null;
    return /饮食|吃了什么|今日吃|今天吃|热量|卡路里|蛋白|碳水|脂肪|营养|calories/.test(query_lower) ? 18 : null;
  },
  async build({ api }) {
    try {
      const res = await api.get(`/diet/records/me/date/${todayISO()}`);
      const d = res.data;
      if (!d) return null;
      const byType: Record<string, number> = {};
      for (const m of (d.meals || [])) {
        const k = m.meal_type || 'snack';
        byType[k] = (byType[k] || 0) + (m.calories || 0);
      }
      return {
        calories: d.total_calories,
        protein: d.total_protein,
        carbs: d.total_carbs,
        fat: d.total_fat,
        fiber: d.total_fiber,
        meals_count: d.meals_count,
        meals_by_type: byType,
      } as DietData;
    } catch { return null; }
  },
  render: (d) => <DietCardView {...d} />,
};

// ────────────────────────────────────────────────────────────────
// 10. DietDraftCard - server-issued, current-page photo confirmation
// ────────────────────────────────────────────────────────────────
interface DietDraftData {
  meal_type?: string;
  food_items?: string | string[];
  calories?: number;
  protein?: number;
  carbs?: number;
  fat?: number;
  fiber?: number;
  confidence?: number;
  photo_url?: string;
  boundary?: string;
  recorded?: boolean;
  record_id?: number;
  receipt_message?: string;
}

const DIET_DRAFT_MEALS: Record<string, string> = {
  breakfast: '早餐', lunch: '午餐', dinner: '晚餐', snack: '加餐',
};

function dietDraftPhotoURL(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  return trimmed.startsWith('/api/v1/upload/files/diet/') ? trimmed : null;
}

function displayDietNumber(value: unknown): string | null {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null;
  return Number.isInteger(value) ? String(value) : String(Math.round(value * 100) / 100);
}

export function DietDraftCardView(data: DietDraftData) {
  const foodItems = Array.isArray(data.food_items)
    ? data.food_items.filter((item): item is string => typeof item === 'string').join(' + ')
    : data.food_items;
  const photoURL = dietDraftPhotoURL(data.photo_url);
  const metrics = [
    ['热量', displayDietNumber(data.calories), 'kcal'],
    ['蛋白', displayDietNumber(data.protein), 'g'],
    ['碳水', displayDietNumber(data.carbs), 'g'],
    ['脂肪', displayDietNumber(data.fat), 'g'],
  ].filter((metric): metric is [string, string, string] => Boolean(metric[1]));
  const meal = DIET_DRAFT_MEALS[data.meal_type || ''] || '这餐';
  const receipt = data.receipt_message || (data.record_id ? `已保存到今日饮食 · 记录 #${data.record_id}` : '已保存到今日饮食');

  return (
    <CardShell
      emoji="🍽️"
      title={data.recorded ? `${meal}已记录` : `${meal}待确认`}
      badge={data.recorded ? '已保存' : '图像估算'}
      badgeColor={data.recorded ? '#1F8A5B' : '#C97A2E'}
      bg="#FFF7F0"
      border="#FED7AA"
    >
      {photoURL ? (
        <img
          src={photoURL}
          alt="本次识别的餐食照片"
          className="mb-3 aspect-[4/3] w-full rounded-lg border border-[#F1DFC9] object-cover"
        />
      ) : null}
      <div className="text-sm font-semibold leading-6 text-[#29261F]">{foodItems || '待核对餐食'}</div>
      {metrics.length > 0 ? (
        <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
          {metrics.map(([label, value, unit]) => (
            <div key={label} className="rounded-lg bg-white/75 px-2.5 py-2 ring-1 ring-[#F1E2CF]">
              <div className="text-[10px] text-[#948F80]">{label}</div>
              <div className="mt-0.5 text-sm font-extrabold tabular-nums text-[#29261F]">{value}<span className="ml-0.5 text-[10px] font-medium text-[#948F80]">{unit}</span></div>
            </div>
          ))}
        </div>
      ) : null}
      {data.recorded ? (
        <div className="mt-3 text-xs font-semibold text-[#176F49]">✓ {receipt}</div>
      ) : data.boundary ? (
        <div className="mt-3 text-[11px] leading-5 text-[#8A5D14]">{data.boundary}</div>
      ) : null}
    </CardShell>
  );
}

export const DietDraftCardSpec: CardSpec<DietDraftData> = {
  type: 'diet_draft', label: '饮食确认',
  match: () => null,
  build: () => null,
  render: (data) => <DietDraftCardView {...data} />,
};

// ────────────────────────────────────────────────────────────────
// 11. MedicalExamImportResultCard - runtime skill import result
// ────────────────────────────────────────────────────────────────
interface MedicalExamImportResultData {
  exam_id: number;
  exam_date?: string | null;
  exam_type?: string | null;
  hospital_name?: string | null;
  items_count?: number | null;
  abnormal_count?: number | null;
  conclusions_count?: number | null;
  conclusion?: string | null;
  source: 'pdf' | 'image' | 'text' | string;
  review_required?: boolean;
  safety_note?: string;
}

function sourceLabel(source: string) {
  if (source === 'pdf') return 'PDF';
  if (source === 'image') return '图片 OCR';
  if (source === 'text') return '文字';
  return source;
}

function ImportMetric({ label, value, risk }: { label: string; value: string; risk?: boolean }) {
  return (
    <div className="min-w-[76px] rounded-xl bg-white px-3 py-2 ring-1 ring-[#EDE7DA]">
      <div className="text-[10px] text-[#948F80]">{label}</div>
      <div className={`mt-0.5 text-xs font-extrabold tabular-nums ${risk ? 'text-[#B8791F]' : 'text-[#29261F]'}`}>
        {value}
      </div>
    </div>
  );
}

export function MedicalExamImportResultCardView(data: MedicalExamImportResultData) {
  const itemsCount = data.items_count ?? 0;
  const abnormalCount = data.abnormal_count ?? 0;
  const safetyNote = data.safety_note ?? 'OCR/AI 解析结果需要复核后再用于判断。';
  return (
    <CardShell
      emoji="📋"
      title="体检报告已导入"
      badge={abnormalCount > 0 ? `${abnormalCount} 项异常` : '待复核'}
      badgeColor={abnormalCount > 0 ? '#B8791F' : '#C96442'}
      bg="#FBF3EE"
      border="#EDD9CF"
    >
      <div className="flex flex-wrap gap-2">
        <ImportMetric label="来源" value={sourceLabel(String(data.source))} />
        <ImportMetric label="指标" value={`${itemsCount} 项指标`} />
        <ImportMetric label="异常" value={`${abnormalCount} 项异常`} risk={abnormalCount > 0} />
      </div>

      {(data.exam_date || data.hospital_name) && (
        <div className="mt-2 line-clamp-2 text-xs text-[#948F80]">
          {[data.exam_date, data.hospital_name].filter(Boolean).join(' · ')}
        </div>
      )}

      {data.conclusion && (
        <div className="mt-2 line-clamp-2 text-xs leading-5 text-[#6B665A]">
          {data.conclusion}
        </div>
      )}

      {data.review_required !== false && (
        <div className="mt-2 rounded-xl bg-[#F5EBD6] px-3 py-2 text-[11px] leading-5 text-[#8A5D14] ring-1 ring-[#EAD9B4]">
          {safetyNote}
        </div>
      )}

      <div className="mt-3 flex flex-wrap gap-2">
        <a
          href="/medical-exams"
          className="rounded-xl border border-[#E3C7BC] bg-white px-3 py-2 text-xs font-bold text-[#C96442] transition-colors hover:bg-[#FBF3EE]"
        >
          查看体检记录
        </a>
        <span className="rounded-xl bg-[#C96442] px-3 py-2 text-xs font-bold text-white">
          已放入对话上下文
        </span>
      </div>
    </CardShell>
  );
}

export const MedicalExamImportResultCardSpec: CardSpec<MedicalExamImportResultData> = {
  type: 'medical_exam_import_result',
  label: '体检导入结果',
  match() {
    return null;
  },
  build() {
    return null;
  },
  render: (d) => <MedicalExamImportResultCardView {...d} />,
};

// ────────────────────────────────────────────────────────────────
// 11. AIGCMediaJobCard - Xiaoba private Wan creation task
// ────────────────────────────────────────────────────────────────
interface AIGCMediaJobData {
  job_id: string;
  kind: string;
  status: string;
  progress: number;
  title?: string;
  result?: { media_type?: string | null; url?: string | null } | null;
  error_message?: string | null;
}

const AIGC_ACTIVE_STATUSES = new Set(['queued', 'running']);
const AIGC_POLL_INTERVAL_MS = 6000;

function aigcKindLabel(kind: string): string {
  switch (kind) {
    case 'text_to_image': return '文生图';
    case 'image_to_image': return '图片创作';
    case 'text_to_video': return '文生短视频';
    case 'image_to_video': return '图生短视频';
    default: return '媒体创作';
  }
}

function aigcStatusMeta(status: string): { label: string; color: string } {
  switch (status) {
    case 'running': return { label: '生成中', color: '#16805C' };
    case 'succeeded': return { label: '已完成', color: '#16805C' };
    case 'failed': return { label: '未完成', color: '#C84B3C' };
    case 'cancelled': return { label: '已取消', color: '#8E8E93' };
    case 'submission_unknown': return { label: '提交待核验', color: '#B7791F' };
    default: return { label: '排队中', color: '#4B8F72' };
  }
}

function normalizeAIGCMediaJob(raw: unknown, fallback: AIGCMediaJobData): AIGCMediaJobData | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null;
  const value = raw as Record<string, unknown>;
  const id = typeof value.id === 'string' ? value.id : fallback.job_id;
  return {
    ...fallback,
    ...value,
    job_id: typeof value.job_id === 'string' ? value.job_id : id,
  } as AIGCMediaJobData;
}

export function AIGCMediaJobCardView(initialData: AIGCMediaJobData) {
  const [data, setData] = React.useState(initialData);

  React.useEffect(() => {
    setData(initialData);
  }, [initialData]);

  React.useEffect(() => {
    const jobID = String(initialData.job_id || '').trim();
    if (!jobID) return;
    let active = true;
    const refresh = async () => {
      try {
        const response = await api.get(`/aigc/media/jobs/${encodeURIComponent(jobID)}`);
        const next = normalizeAIGCMediaJob(response.data, initialData);
        if (active && next) setData(next);
      } catch {
        // Keep the last valid projection. The result URL is short-lived and the
        // next successful refresh will replace it before display.
      }
    };
    void refresh();
    const timer = window.setInterval(() => {
      if (AIGC_ACTIVE_STATUSES.has(String(data.status || '').toLowerCase())) void refresh();
    }, AIGC_POLL_INTERVAL_MS);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [data.status, initialData]);

  const status = String(data.status || 'queued').toLowerCase();
  const statusMeta = aigcStatusMeta(status);
  const progress = Math.max(0, Math.min(100, Math.round(Number(data.progress) || 0)));
  const resultURL = typeof data.result?.url === 'string' ? data.result.url : null;
  const mediaType = String(data.result?.media_type || '').toLowerCase();
  const isImage = mediaType.startsWith('image/');
  const isVideo = mediaType.startsWith('video/');
  const detail = status === 'queued'
    ? '小巴已提交任务，正在等待百炼处理。'
    : status === 'running'
      ? '生成完成后会自动保存到你的私有空间。'
      : status === 'succeeded'
        ? '结果仅对当前账号可见。'
        : status === 'submission_unknown'
          ? '提交结果待核验，已停止自动重试以避免重复生成。'
        : (data.error_message || '本次创作未完成，修改描述后可以重新生成。');

  return (
    <CardShell
      emoji="✦"
      title={data.title || '小巴创作'}
      badge={aigcKindLabel(String(data.kind || ''))}
      badgeColor="#16805C"
      bg="#F1FAF5"
      border="#BFE4D1"
    >
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <div className="text-sm font-extrabold" style={{ color: statusMeta.color }}>{statusMeta.label}</div>
          <div className="mt-0.5 text-[11px] leading-5 text-slate-500">{detail}</div>
        </div>
      </div>
      {AIGC_ACTIVE_STATUSES.has(status) && (
        <div className="mt-2 flex items-center gap-2">
          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-emerald-100">
            <div className="h-full rounded-full bg-emerald-600 transition-all" style={{ width: `${Math.max(progress, 4)}%` }} />
          </div>
          <span className="w-8 text-right text-[10px] font-bold tabular-nums text-slate-500">{progress}%</span>
        </div>
      )}
      {resultURL && isImage && (
        <a href={resultURL} target="_blank" rel="noreferrer" className="mt-3 block overflow-hidden rounded-xl ring-1 ring-emerald-100">
          <Image
            src={resultURL}
            alt="小巴生成的图片"
            width={768}
            height={768}
            unoptimized
            className="aspect-square w-full object-cover"
          />
        </a>
      )}
      {resultURL && isVideo && (
        <a
          href={resultURL}
          target="_blank"
          rel="noreferrer"
          className="mt-3 flex min-h-11 items-center justify-between rounded-xl bg-white px-3 text-xs font-bold text-emerald-700 ring-1 ring-emerald-100"
        >
          <span>打开短视频</span><span aria-hidden="true">↗</span>
        </a>
      )}
    </CardShell>
  );
}

export const AIGCMediaJobCardSpec: CardSpec<AIGCMediaJobData> = {
  type: 'aigc_media_job',
  label: '小巴创作任务',
  match() { return null; },
  build() { return null; },
  render: (data) => <AIGCMediaJobCardView {...data} />,
};

interface AIGCMediaConfirmationData {
  confirmation_id: string;
  kind: string;
  status?: string;
  title?: string;
  provider?: string;
  source_attached?: boolean;
}

export function AIGCMediaConfirmationCardView(data: AIGCMediaConfirmationData) {
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [job, setJob] = React.useState<AIGCMediaJobData | null>(null);
  const confirmationID = String(data.confirmation_id || '').trim();

  const confirm = async () => {
    if (!confirmationID || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const response = await api.post(`/aigc/media/confirmations/${encodeURIComponent(confirmationID)}/confirm`);
      const payload = response.data;
      if (!payload || typeof payload !== 'object' || typeof payload.id !== 'string') {
        throw new Error('aigc_confirmation_missing_job');
      }
      setJob({ ...(payload as Record<string, unknown>), job_id: payload.id } as AIGCMediaJobData);
    } catch {
      setError('提交未完成，请稍后重试。');
    } finally {
      setSubmitting(false);
    }
  };

  if (job) return <AIGCMediaJobCardView {...job} />;
  return (
    <CardShell emoji="✦" title={data.title || '小巴创作草稿'} badge={aigcKindLabel(String(data.kind || ''))} badgeColor="#16805C" bg="#F1FAF5" border="#BFE4D1">
      <div className="rounded-lg bg-emerald-50 px-3 py-2 text-xs leading-5 text-slate-600">
        将发送你的创作描述{data.source_attached ? '和当前图片' : ''}给{data.provider || '百炼 Wan'}生成。
      </div>
      {error && <div className="mt-2 text-xs text-red-600">{error}</div>}
      <button
        type="button"
        onClick={() => { void confirm(); }}
        disabled={!confirmationID || submitting}
        className="mt-3 flex min-h-11 w-full items-center justify-center rounded-lg bg-emerald-700 px-3 text-sm font-extrabold text-white transition-opacity disabled:cursor-not-allowed disabled:opacity-60"
      >
        {submitting ? '正在提交…' : '发送给百炼并生成'}
      </button>
    </CardShell>
  );
}

export const AIGCMediaConfirmationCardSpec: CardSpec<AIGCMediaConfirmationData> = {
  type: 'aigc_media_confirmation',
  label: '小巴创作确认',
  match() { return null; },
  build() { return null; },
  render: (data) => <AIGCMediaConfirmationCardView {...data} />,
};
