'use client';
import { useState, useEffect } from 'react';

interface HeroCardProps {
  user: any;
  healthScore: any;
  todayGarmin: any;
  waterToday: { total_ml: number; goal_ml: number; count: number };
  suppChecked: number;
  suppTotal: number;
  weatherData: any;
  airData: any;
  onRefresh: () => void;
}

function ScoreRing({ score, size = 72 }: { score: number; size?: number }) {
  const strokeWidth = 6;
  const r = (size - strokeWidth) / 2;
  const c = 2 * Math.PI * r;
  const target = c - (score / 100) * c;
  const [offset, setOffset] = useState(c);

  useEffect(() => {
    const t = setTimeout(() => setOffset(target), 80);
    return () => clearTimeout(t);
  }, [target, c]);

  const color = score >= 80 ? '#4ade80' : score >= 60 ? '#fbbf24' : '#f87171';
  const glowColor = score >= 80 ? 'rgba(74,222,128,0.4)' : score >= 60 ? 'rgba(251,191,36,0.4)' : 'rgba(248,113,113,0.4)';

  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)', filter: `drop-shadow(0 0 6px ${glowColor})` }}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(255,255,255,0.15)" strokeWidth={strokeWidth} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={strokeWidth}
          strokeDasharray={c} strokeDashoffset={offset} strokeLinecap="round"
          style={{ transition: 'stroke-dashoffset 1.2s cubic-bezier(0.4,0,0.2,1)' }} />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-[26px] font-black text-white leading-none">{score || '--'}</span>
        <span className="text-[9px] text-white/50 mt-0.5">健康分</span>
      </div>
    </div>
  );
}

function ProgressRing({ value, max, color, label, format }: {
  value: number; max: number; color: string; label: string; format?: (v: number) => string;
}) {
  const size = 50;
  const strokeWidth = 4;
  const r = (size - strokeWidth) / 2;
  const c = 2 * Math.PI * r;
  const pct = Math.min(100, Math.round((value / Math.max(max, 1)) * 100));
  const [offset, setOffset] = useState(c);

  useEffect(() => {
    const target = c - (pct / 100) * c;
    const t = setTimeout(() => setOffset(target), 120);
    return () => clearTimeout(t);
  }, [pct, c]);

  const display = format ? format(value) : (value >= 10000 ? (value / 1000).toFixed(1) + 'k' : value.toLocaleString());

  return (
    <div className="flex flex-col items-center gap-0.5">
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth={strokeWidth} />
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={strokeWidth}
            strokeDasharray={c} strokeDashoffset={offset} strokeLinecap="round"
            style={{ transition: 'stroke-dashoffset 1s cubic-bezier(0.4,0,0.2,1)', filter: `drop-shadow(0 0 3px ${color}55)` }} />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-[12px] font-bold text-white leading-none">{display}</span>
        </div>
      </div>
      <span className="text-[9px] text-white/45">{label}</span>
    </div>
  );
}

export default function HeroCard({ user, healthScore, todayGarmin, waterToday, suppChecked, suppTotal, weatherData, airData, onRefresh }: HeroCardProps) {
  const h = new Date().getHours();
  const greeting = h < 6 ? '夜深了' : h < 11 ? '早上好' : h < 14 ? '中午好' : h < 18 ? '下午好' : '晚上好';
  const displayName = user?.name || user?.username || '';
  const score = healthScore?.total_score || 0;

  const sleepScore = todayGarmin?.sleep_score;
  const hrv = todayGarmin?.hrv;
  const bodyBattery = todayGarmin?.body_battery_current ?? todayGarmin?.body_battery_most_charged;
  const restingHR = todayGarmin?.resting_heart_rate || todayGarmin?.avg_heart_rate;
  const stress = todayGarmin?.stress_level;
  const steps = todayGarmin?.steps || 0;
  const activeMin = todayGarmin?.active_minutes || 0;

  const getFocusMessage = () => {
    const issues: string[] = [];
    if (hrv && hrv < 40) issues.push('HRV偏低，注意恢复');
    if (todayGarmin?.spo2_avg && todayGarmin.spo2_avg < 92) issues.push(`血氧${todayGarmin.spo2_avg}%偏低`);
    if (bodyBattery != null && bodyBattery < 30) issues.push('能量不足');
    if (stress && stress > 50) issues.push('压力偏高');
    if (steps < 3000 && h >= 15) issues.push('步数不足');
    if (sleepScore && sleepScore < 60) issues.push('睡眠质量差');
    if (issues.length > 0) return issues[0];
    if (bodyBattery && bodyBattery >= 80) return '状态很好，适合运动';
    if (sleepScore && sleepScore >= 85) return '睡眠充足，精力充沛';
    return '保持节奏，持续追踪';
  };

  return (
    <div className="rounded-[20px] relative overflow-hidden"
      style={{ background: 'linear-gradient(135deg, #1a3a2a 0%, #1e4d3d 35%, #1a5c4a 65%, #186850 100%)' }}>

      {/* Ambient glow */}
      <div className="absolute -top-20 -right-20 w-52 h-52 rounded-full" style={{ background: 'rgba(52,211,153,0.08)' }} />
      <div className="absolute -bottom-16 -left-10 w-40 h-40 rounded-full" style={{ background: 'rgba(16,185,129,0.06)' }} />

      <div className="relative z-10 p-5">
        {/* Row 1: Score + Greeting */}
        <div className="flex items-center gap-4 mb-4">
          <ScoreRing score={score} size={72} />
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between">
              <h1 className="text-lg font-bold text-white tracking-wide">
                {greeting}，{displayName}
              </h1>
              <button onClick={onRefresh}
                className="p-1.5 rounded-full text-white/30 hover:text-white/70 hover:bg-white/10 transition-all active:scale-95">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
              </button>
            </div>
            <p className="text-[11px] text-white/40 mt-0.5 leading-relaxed">
              {new Date().toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' })}
              {weatherData && (
                <> · {weatherData.city} {Math.round(weatherData.temperature ?? 0)}° {weatherData.weather || ''}
                  {airData ? ` · AQI ${airData.aqi || '--'}${airData.pm25 ? ` · PM2.5 ${airData.pm25}` : ''}` : ''}
                  {weatherData.tomorrow && (
                    <> · 明 {weatherData.tomorrow.weather || ''} {weatherData.tomorrow.temp_min != null ? `${Math.round(weatherData.tomorrow.temp_min)}~${Math.round(weatherData.tomorrow.temp_max)}°` : ''}</>
                  )}
                </>
              )}
            </p>
            <p className="text-xs text-emerald-200/70 font-medium mt-0.5">{getFocusMessage()}</p>
          </div>
        </div>

        {/* Row 2: Vitals - frosted glass cards */}
        <div className="grid grid-cols-4 gap-2 mb-3">
          {[
            { icon: '🌙', label: '睡眠', value: sleepScore, unit: '分', warn: sleepScore != null && sleepScore < 60 },
            { icon: '💜', label: 'HRV', value: hrv, unit: 'ms', warn: hrv != null && hrv < 40 },
            { icon: '⚡', label: '能量', value: bodyBattery, unit: '', warn: bodyBattery != null && bodyBattery < 30 },
            { icon: '❤️', label: '心率', value: restingHR, unit: 'bpm', warn: false },
          ].map(item => (
            <div key={item.label}
              className="rounded-xl p-2 text-center backdrop-blur-sm"
              style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.06)' }}>
              <div className="text-[10px] text-white/40 mb-0.5">
                <span className="mr-0.5">{item.icon}</span>{item.label}
              </div>
              <div className={`text-lg font-extrabold leading-none ${item.warn ? 'text-amber-300' : 'text-white'}`}>
                {item.value ?? '--'}
              </div>
              {item.unit && <span className="text-[9px] text-white/30">{item.unit}</span>}
            </div>
          ))}
        </div>

        {/* Row 3: Progress rings */}
        <div className="flex items-center justify-between px-1">
          <ProgressRing value={steps} max={10000} color="#a78bfa" label="步数"
            format={(v) => v >= 10000 ? (v / 1000).toFixed(1) + 'k' : v.toLocaleString()} />
          <ProgressRing value={activeMin} max={30} color="#fb923c" label="活动min" />
          <ProgressRing value={waterToday.total_ml} max={waterToday.goal_ml} color="#38bdf8" label="饮水ml" />
          <ProgressRing value={suppChecked} max={Math.max(suppTotal, 1)} color="#4ade80" label="补剂"
            format={(v) => `${v}/${suppTotal}`} />
          {stress != null && (
            <ProgressRing value={Math.max(0, 100 - stress)} max={100}
              color={stress > 40 ? '#f87171' : '#2dd4bf'} label="压力"
              format={() => String(stress)} />
          )}
        </div>
      </div>
    </div>
  );
}
