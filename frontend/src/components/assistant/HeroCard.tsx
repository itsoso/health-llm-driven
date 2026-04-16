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

const FONT = '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Helvetica Neue", system-ui, sans-serif';

// Palette: Oura-inspired warm cream + iOS tinted pastels
const C = {
  ink: '#1c1b1f',
  sub: '#6b6874',
  mute: '#9a96a3',
  divider: 'rgba(28,27,31,0.07)',
  track: 'rgba(28,27,31,0.08)',
  // tinted card backgrounds (for vitals)
  sleepBg: 'linear-gradient(140deg, rgba(120,113,228,0.12), rgba(120,113,228,0.04))',
  sleepFg: '#5e5ce6',
  hrvBg: 'linear-gradient(140deg, rgba(203,93,255,0.13), rgba(203,93,255,0.04))',
  hrvFg: '#bf5af2',
  energyBg: 'linear-gradient(140deg, rgba(255,159,10,0.14), rgba(255,159,10,0.04))',
  energyFg: '#ff9500',
  hrBg: 'linear-gradient(140deg, rgba(255,69,58,0.13), rgba(255,69,58,0.04))',
  hrFg: '#ff453a',
};

function ScoreRing({ score, size = 96 }: { score: number; size?: number }) {
  const strokeWidth = 8;
  const r = (size - strokeWidth) / 2;
  const c = 2 * Math.PI * r;
  const target = c - (score / 100) * c;
  const [offset, setOffset] = useState(c);

  useEffect(() => {
    const t = setTimeout(() => setOffset(target), 80);
    return () => clearTimeout(t);
  }, [target, c]);

  const grad =
    score >= 80 ? ['#4ade80', '#22c55e'] :
    score >= 60 ? ['#fbbf24', '#f59e0b'] :
    ['#fb7185', '#ef4444'];
  const gradId = `ring-grad-${score}`;

  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)', filter: 'drop-shadow(0 6px 12px rgba(239,68,68,0.10))' }}>
        <defs>
          <linearGradient id={gradId} x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor={grad[0]} />
            <stop offset="100%" stopColor={grad[1]} />
          </linearGradient>
        </defs>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(28,27,31,0.06)" strokeWidth={strokeWidth} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={`url(#${gradId})`} strokeWidth={strokeWidth}
          strokeDasharray={c} strokeDashoffset={offset} strokeLinecap="round"
          style={{ transition: 'stroke-dashoffset 1.4s cubic-bezier(0.16,1,0.3,1)' }} />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center" style={{ fontFamily: FONT }}>
        <span className="font-semibold leading-none" style={{ fontSize: 36, letterSpacing: '-0.035em', color: C.ink }}>
          {score || '—'}
        </span>
        <span className="text-[10px] mt-1.5 font-medium tracking-wider" style={{ color: C.mute }}>
          健康分
        </span>
      </div>
    </div>
  );
}

function VitalTile({
  label, value, unit, bg, fg, icon, sub,
}: {
  label: string; value: any; unit: string; bg: string; fg: string; icon: string; sub?: string;
}) {
  return (
    <div
      className="relative rounded-2xl p-2.5 sm:p-3.5 overflow-hidden"
      style={{ background: bg, border: `1px solid ${fg}1a` }}
    >
      <div className="flex items-center justify-between mb-0.5">
        <span className="text-[9px] sm:text-[10px] font-semibold tracking-wider uppercase" style={{ color: fg, opacity: 0.75 }}>
          {label}
        </span>
        <span className="text-[12px] leading-none opacity-60">{icon}</span>
      </div>
      <div className="flex items-baseline gap-0.5">
        <span
          className="font-semibold leading-none"
          style={{ fontSize: 24, letterSpacing: '-0.035em', color: C.ink }}
        >
          {value ?? '—'}
        </span>
        {unit && <span className="text-[10px] font-medium" style={{ color: C.mute }}>{unit}</span>}
      </div>
      {sub && (
        <div className="mt-1 text-[10px] font-medium" style={{ color: fg, opacity: 0.65 }}>
          {sub}
        </div>
      )}
    </div>
  );
}

function CounterChip({
  label, value, sub, raw, max, color,
}: {
  label: string; value: string; sub: string; raw: number; max: number; color: string;
}) {
  const pct = Math.min(100, Math.round((raw / Math.max(max, 1)) * 100));
  // minimum visible width so small values (1%) still show a clear marker
  const fillWidth = raw > 0 ? `max(10px, ${pct}%)` : '0%';
  return (
    <div className="min-w-0">
      <div className="flex items-baseline justify-between gap-0.5 mb-1.5">
        <div className="flex items-baseline gap-1 min-w-0">
          <span className="text-[10px] font-semibold tracking-wide whitespace-nowrap" style={{ color: C.sub }}>{label}</span>
          <span className="text-[9px] font-semibold tabular-nums" style={{ color }}>
            {pct}%
          </span>
        </div>
        <div className="flex items-baseline gap-0.5 truncate">
          <span className="text-[13px] font-semibold leading-none tabular-nums" style={{ color: C.ink, letterSpacing: '-0.02em' }}>
            {value}
          </span>
          {sub && <span className="text-[9px] font-medium truncate" style={{ color: C.mute }}>{sub}</span>}
        </div>
      </div>
      <div
        className="relative rounded-full overflow-hidden"
        style={{
          height: 6,
          background: 'rgba(28,27,31,0.09)',
          boxShadow: 'inset 0 1px 2px rgba(28,27,31,0.06)',
        }}
      >
        <div
          className="h-full rounded-full transition-all duration-700 ease-out"
          style={{
            width: fillWidth,
            background: `linear-gradient(90deg, ${color}cc, ${color})`,
            boxShadow: `0 0 8px ${color}66, 0 1px 2px ${color}55`,
          }}
        />
      </div>
    </div>
  );
}

export default function HeroCard({
  user, healthScore, todayGarmin, waterToday, suppChecked, suppTotal, weatherData, airData, onRefresh,
}: HeroCardProps) {
  const h = new Date().getHours();
  const greeting = h < 6 ? '夜深了' : h < 11 ? '早上好' : h < 14 ? '中午好' : h < 18 ? '下午好' : '晚上好';
  const displayName = user?.name || user?.username || '';
  const score = healthScore?.total_score || 0;

  const sleepScore = todayGarmin?.sleep_score;
  const hrv = todayGarmin?.hrv;
  const bodyBatteryCurrent = todayGarmin?.body_battery_current;
  const bodyBatteryPeak = todayGarmin?.body_battery_most_charged;
  const bodyBattery = bodyBatteryCurrent ?? bodyBatteryPeak;
  const restingHR = todayGarmin?.resting_heart_rate || todayGarmin?.avg_heart_rate;
  const stress = todayGarmin?.stress_level;
  const steps = todayGarmin?.steps || 0;
  const activeMin = Math.max(todayGarmin?.active_minutes || 0, (todayGarmin?.moderate_intensity_minutes || 0) + (todayGarmin?.vigorous_intensity_minutes || 0));

  const focus = (() => {
    if (hrv != null && hrv < 40) return { level: 'warn', text: 'HRV 偏低' };
    if (todayGarmin?.spo2_avg && todayGarmin.spo2_avg < 92) return { level: 'warn', text: `血氧 ${todayGarmin.spo2_avg}%` };
    if (bodyBattery != null && bodyBattery < 30) return { level: 'warn', text: '能量不足' };
    if (stress != null && stress > 50) return { level: 'warn', text: '压力偏高' };
    if (steps < 3000 && h >= 15) return { level: 'warn', text: '步数不足' };
    if (sleepScore && sleepScore < 60) return { level: 'warn', text: '睡眠质量差' };
    if (bodyBattery && bodyBattery >= 80) return { level: 'good', text: '状态很好' };
    if (sleepScore && sleepScore >= 85) return { level: 'good', text: '睡眠充足' };
    return { level: 'neutral', text: '保持节奏' };
  })();
  const focusPalette =
    focus.level === 'warn' ? { bg: 'rgba(255,149,0,0.14)', fg: '#c76a00', dot: '#ff9500' } :
    focus.level === 'good' ? { bg: 'rgba(52,199,89,0.14)', fg: '#1e8c3c', dot: '#34c759' } :
    { bg: 'rgba(28,27,31,0.06)', fg: C.sub, dot: C.mute };

  const fmtK = (v: number) => (v >= 1000 ? (v / 1000).toFixed(1) + 'k' : String(v));
  const counters = [
    { label: '步数', value: fmtK(steps), sub: '/10k', raw: steps, max: 10000, color: '#5e5ce6' },
    { label: '活动', value: String(activeMin), sub: ' min', raw: activeMin, max: 30, color: '#ff9500' },
    { label: '饮水', value: fmtK(waterToday.total_ml), sub: `/${fmtK(waterToday.goal_ml || 2000)} ml`, raw: waterToday.total_ml, max: waterToday.goal_ml || 2000, color: '#64d2ff' },
    { label: '补剂', value: String(suppChecked), sub: `/${suppTotal}`, raw: suppChecked, max: Math.max(suppTotal, 1), color: '#30d158' },
    { label: '压力', value: stress != null ? String(stress) : '—', sub: '', raw: stress != null ? Math.max(0, 100 - stress) : 0, max: 100, color: stress != null && stress > 40 ? '#ff453a' : '#00c7be' },
  ];

  const dateStr = new Date().toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'short' });

  return (
    <div
      className="relative overflow-hidden"
      style={{
        fontFamily: FONT,
        borderRadius: 24,
        // Warm premium mesh background
        background:
          'radial-gradient(ellipse 80% 60% at 0% 0%, rgba(255,221,200,0.55) 0%, rgba(255,221,200,0) 60%),' +
          'radial-gradient(ellipse 70% 60% at 100% 0%, rgba(218,215,255,0.55) 0%, rgba(218,215,255,0) 60%),' +
          'radial-gradient(ellipse 100% 60% at 50% 100%, rgba(207,232,255,0.5) 0%, rgba(207,232,255,0) 60%),' +
          '#fdfbf7',
        border: '1px solid rgba(28,27,31,0.06)',
        boxShadow: '0 1px 2px rgba(28,27,31,0.04), 0 12px 32px -12px rgba(28,27,31,0.10)',
      }}
    >
      <div className="relative px-4 sm:px-6 py-4 sm:py-5">
        {/* ── Top row: greeting + focus + refresh ── */}
        <div className="flex items-center justify-between gap-2 mb-3 sm:mb-5">
          <div className="flex items-center gap-2 min-w-0">
            <h1 className="font-semibold leading-none truncate"
              style={{ fontSize: 17, color: C.ink, letterSpacing: '-0.02em' }}>
              {greeting}，{displayName}
            </h1>
            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] font-semibold shrink-0"
              style={{ background: focusPalette.bg, color: focusPalette.fg }}>
              <span className="w-[5px] h-[5px] rounded-full" style={{ background: focusPalette.dot }} />
              {focus.text}
            </span>
          </div>

          <div className="flex items-center gap-1.5 shrink-0">
            <button onClick={onRefresh}
              className="p-1.5 rounded-full transition-all active:scale-90 hover:bg-black/5"
              style={{ color: C.mute }} title="刷新">
              <svg className="w-[15px] h-[15px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            </button>
          </div>
        </div>

        {/* ── Weather bar (compact on mobile) ── */}
        {weatherData && (
          <div className="flex flex-wrap items-center gap-1.5 mb-3 text-[10px] sm:text-[11px]">
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full font-medium"
              style={{ background: 'rgba(255,255,255,0.65)', border: `1px solid ${C.divider}`, color: C.sub }}>
              📍 {weatherData.city} {Math.round(weatherData.temperature ?? 0)}°
              {weatherData.weather ? ` ${weatherData.weather}` : ''}
              {airData ? ` · AQI ${airData.aqi || '—'}` : ''}
              {airData?.pm25 != null ? ` · PM2.5 ${airData.pm25}` : ''}
            </span>
            {weatherData.tomorrow && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full font-medium"
                style={{ background: 'rgba(255,255,255,0.65)', border: `1px solid ${C.divider}`, color: C.sub }}>
                明 {weatherData.tomorrow.weather || ''}
                {weatherData.tomorrow.temp_min != null && ` ${Math.round(weatherData.tomorrow.temp_min)}–${Math.round(weatherData.tomorrow.temp_max)}°`}
              </span>
            )}
          </div>
        )}

        {/* ── Hero row: score ring + 4 vital tiles ── */}
        <div className="flex gap-3 sm:gap-4">
          <div className="flex items-center shrink-0">
            <ScoreRing score={score} size={80} />
          </div>
          <div className="grid grid-cols-2 gap-2 flex-1">
            <VitalTile label="睡眠" value={sleepScore} unit="分" bg={C.sleepBg} fg={C.sleepFg} icon="🌙" />
            <VitalTile label="HRV" value={hrv} unit="ms" bg={C.hrvBg} fg={C.hrvFg} icon="💓" />
            <VitalTile
              label="能量"
              value={bodyBatteryCurrent ?? bodyBatteryPeak ?? null}
              unit=""
              bg={C.energyBg}
              fg={C.energyFg}
              icon="⚡"
              sub={bodyBatteryPeak != null && bodyBatteryCurrent != null && bodyBatteryPeak !== bodyBatteryCurrent
                ? `峰 ${bodyBatteryPeak}`
                : undefined}
            />
            <VitalTile label="心率" value={restingHR} unit="bpm" bg={C.hrBg} fg={C.hrFg} icon="❤️" />
          </div>
        </div>

        {/* ── Bottom strip: 5 counters ── */}
        <div className="mt-3 pt-3 grid grid-cols-5 gap-1.5 sm:gap-3" style={{ borderTop: `1px solid ${C.divider}` }}>
          {counters.map((c) => (
            <CounterChip key={c.label} {...c} />
          ))}
        </div>
      </div>
    </div>
  );
}
