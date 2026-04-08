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

function ScoreRing({ score, size = 64 }: { score: number; size?: number }) {
  const strokeWidth = 5;
  const r = (size - strokeWidth) / 2;
  const c = 2 * Math.PI * r;
  const target = c - (score / 100) * c;
  const [offset, setOffset] = useState(c);

  useEffect(() => {
    const t = setTimeout(() => setOffset(target), 80);
    return () => clearTimeout(t);
  }, [target, c]);

  const color = score >= 80 ? '#30D158' : score >= 60 ? '#FF9500' : '#FF3B30';

  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#E5E5EA" strokeWidth={strokeWidth} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={strokeWidth}
          strokeDasharray={c} strokeDashoffset={offset} strokeLinecap="round"
          style={{ transition: 'stroke-dashoffset 1.2s cubic-bezier(0.4,0,0.2,1)' }} />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-[22px] font-black leading-none" style={{ color: '#1C1C1E' }}>{score || '--'}</span>
        <span className="text-[9px] mt-0.5" style={{ color: '#AEAEB2' }}>健康分</span>
      </div>
    </div>
  );
}

function MiniProgress({ value, max, color, label }: { value: number; max: number; color: string; label: string }) {
  const pct = Math.min(100, Math.round((value / Math.max(max, 1)) * 100));
  return (
    <div className="flex-1 min-w-0">
      <div className="flex items-baseline justify-between mb-1">
        <span className="text-xs font-bold" style={{ color: '#1C1C1E' }}>
          {value >= 10000 ? (value / 1000).toFixed(1) + 'k' : value.toLocaleString()}
        </span>
      </div>
      <div className="h-1.5 rounded-full" style={{ background: '#E5E5EA' }}>
        <div className="h-full rounded-full transition-all duration-700" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="text-[10px] mt-0.5 block" style={{ color: '#AEAEB2' }}>{label}</span>
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

  // 维度色
  const COLORS = { sleep: '#5E5CE6', hrv: '#BF5AF2', energy: '#FF9500', hr: '#FF3B30', steps: '#30D158', active: '#FF9500', water: '#00C7BE', supp: '#FF6482', stress: '#BF5AF2' };

  return (
    <div className="rounded-2xl bg-white p-4" style={{ boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
      {/* Row 1: Score + Greeting */}
      <div className="flex items-center gap-3">
        <ScoreRing score={score} size={64} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between">
            <h1 className="text-lg font-bold" style={{ color: '#1C1C1E' }}>
              {greeting}，{displayName}
            </h1>
            <button onClick={onRefresh}
              className="p-1.5 rounded-full transition-colors hover:bg-gray-100 active:scale-95"
              style={{ color: '#AEAEB2' }}>
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            </button>
          </div>
          <p className="text-[11px] mt-0.5 leading-relaxed" style={{ color: '#8E8E93' }}>
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
          <p className="text-xs font-medium mt-0.5" style={{ color: '#1C1C1E' }}>{getFocusMessage()}</p>
        </div>
      </div>

      {/* Divider */}
      <div className="my-3" style={{ borderTop: '1px solid #E5E5EA' }} />

      {/* Row 2: Vitals (Sleep, HRV, Energy, HR) */}
      <div className="grid grid-cols-4 gap-3">
        {[
          { label: '睡眠', value: sleepScore, unit: '分', color: COLORS.sleep, warn: sleepScore != null && sleepScore < 60 },
          { label: 'HRV', value: hrv, unit: 'ms', color: COLORS.hrv, warn: hrv != null && hrv < 40 },
          { label: '能量', value: bodyBattery, unit: '', color: COLORS.energy, warn: bodyBattery != null && bodyBattery < 30 },
          { label: '心率', value: restingHR, unit: 'bpm', color: COLORS.hr, warn: false },
        ].map(item => (
          <div key={item.label} className="text-center">
            <div className="flex items-center justify-center gap-1 mb-0.5">
              <div className="w-1.5 h-1.5 rounded-full" style={{ background: item.color }} />
              <span className="text-[10px]" style={{ color: '#AEAEB2' }}>{item.label}</span>
            </div>
            <span className={`text-xl font-extrabold leading-none ${item.warn ? 'text-amber-500' : ''}`}
              style={item.warn ? undefined : { color: '#1C1C1E' }}>
              {item.value ?? '--'}
            </span>
            {item.unit && <span className="text-[10px] ml-0.5" style={{ color: '#AEAEB2' }}>{item.unit}</span>}
          </div>
        ))}
      </div>

      {/* Divider */}
      <div className="my-3" style={{ borderTop: '1px solid #E5E5EA' }} />

      {/* Row 3: Progress bars (Steps, Active, Water, Supplements, Stress) */}
      <div className="flex gap-3">
        <MiniProgress value={steps} max={10000} color={COLORS.steps} label="步数" />
        <MiniProgress value={activeMin} max={30} color={COLORS.active} label="活动min" />
        <MiniProgress value={waterToday.total_ml} max={waterToday.goal_ml} color={COLORS.water} label="饮水ml" />
        <MiniProgress value={suppChecked} max={Math.max(suppTotal, 1)} color={COLORS.supp} label={`补剂 ${suppChecked}/${suppTotal}`} />
        {stress != null && (
          <MiniProgress value={Math.max(0, 100 - stress)} max={100} color={stress > 40 ? '#FF3B30' : COLORS.stress} label={`压力 ${stress}`} />
        )}
      </div>
    </div>
  );
}
