'use client';
import AnimatedRing from '@/components/charts/AnimatedRing';

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

function MiniRing({ value, max, color, size = 36 }: { value: number; max: number; color: string; size?: number }) {
  const pct = Math.min(100, Math.round((value / max) * 100));
  const r = (size - 5) / 2;
  const c = 2 * Math.PI * r;
  return (
    <svg width={size} height={size} className="shrink-0 -rotate-90">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth={4} />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={4}
        strokeDasharray={`${c * pct / 100} ${c}`} strokeLinecap="round" className="transition-all duration-700" />
    </svg>
  );
}

export default function HeroCard({ user, healthScore, todayGarmin, waterToday, suppChecked, suppTotal, weatherData, airData, onRefresh }: HeroCardProps) {
  const h = new Date().getHours();
  const greeting = h < 6 ? '夜深了' : h < 11 ? '早上好' : h < 14 ? '中午好' : h < 18 ? '下午好' : '晚上好';
  const displayName = user?.name || user?.username || '';
  const score = healthScore?.total_score || 0;

  // Core vitals - only show the most important 3
  const sleepScore = todayGarmin?.sleep_score;
  const hrv = todayGarmin?.hrv;
  const bodyBattery = todayGarmin?.body_battery_current ?? todayGarmin?.body_battery_most_charged;
  const restingHR = todayGarmin?.resting_heart_rate || todayGarmin?.avg_heart_rate;
  const stress = todayGarmin?.stress_level;
  const spo2 = todayGarmin?.spo2_avg;
  const steps = todayGarmin?.steps || 0;
  const activeMin = todayGarmin?.active_minutes || 0;

  // Determine today's focus message
  const getFocusMessage = () => {
    const issues: string[] = [];
    if (hrv && hrv < 40) issues.push('HRV偏低，注意恢复');
    if (spo2 && spo2 < 92) issues.push(`血氧${spo2}%偏低`);
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
    <div className="rounded-3xl p-5 relative overflow-hidden shadow-lg"
      style={{ background: 'linear-gradient(135deg, #065f46 0%, #047857 40%, #059669 100%)' }}>
      <div className="absolute -top-12 -right-12 w-40 h-40 rounded-full" style={{ background: 'rgba(255,255,255,0.06)' }} />
      <div className="relative z-10">
        {/* Row 1: Score + Greeting */}
        <div className="flex items-center gap-4 mb-4">
          <div className="relative shrink-0">
            <AnimatedRing score={score} size={68} strokeWidth={5} />
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-2xl font-extrabold text-white">{score || '--'}</span>
              <span className="text-[8px] text-emerald-200/60">健康分</span>
            </div>
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between">
              <h1 className="text-lg font-bold text-white">{greeting}{displayName ? `，${displayName}` : ''}</h1>
              <button onClick={onRefresh}
                className="text-[10px] text-white/50 hover:text-white flex items-center gap-1 bg-white/10 rounded-full px-2.5 py-1">
                <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                刷新
              </button>
            </div>
            <div className="flex items-center gap-2 mt-0.5 flex-wrap">
              <p className="text-emerald-200/70 text-xs">{new Date().toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' })}</p>
              {weatherData && (
                <span className="text-[10px] text-emerald-200/60">
                  {weatherData.city} {Math.round(weatherData.temperature ?? 0)}° {weatherData.weather || ''}
                  {airData ? ` · AQI ${airData.aqi || '--'}` : ''}
                </span>
              )}
            </div>
            <p className="text-xs text-emerald-100/80 mt-1.5 font-medium">{getFocusMessage()}</p>
          </div>
        </div>

        {/* Row 2: Core Vitals - 大数字突出 */}
        <div className="grid grid-cols-4 gap-2 mb-3">
          <div className="bg-white/10 rounded-2xl p-2.5 text-center">
            <div className="text-[10px] text-white/50 mb-0.5">😴 睡眠</div>
            <div className={`text-xl font-extrabold ${sleepScore && sleepScore < 60 ? 'text-amber-300' : 'text-white'}`}>
              {sleepScore ?? '--'}<span className="text-[9px] font-normal text-white/40">分</span>
            </div>
          </div>
          <div className="bg-white/10 rounded-2xl p-2.5 text-center">
            <div className="text-[10px] text-white/50 mb-0.5">💓 HRV</div>
            <div className={`text-xl font-extrabold ${hrv && hrv < 40 ? 'text-red-300' : 'text-white'}`}>
              {hrv ?? '--'}<span className="text-[9px] font-normal text-white/40">ms</span>
            </div>
          </div>
          <div className="bg-white/10 rounded-2xl p-2.5 text-center">
            <div className="text-[10px] text-white/50 mb-0.5">🔋 能量</div>
            <div className={`text-xl font-extrabold ${bodyBattery != null && bodyBattery < 30 ? 'text-amber-300' : 'text-white'}`}>
              {bodyBattery ?? '--'}
            </div>
          </div>
          <div className="bg-white/10 rounded-2xl p-2.5 text-center">
            <div className="text-[10px] text-white/50 mb-0.5">❤️ 心率</div>
            <div className="text-xl font-extrabold text-white">
              {restingHR ?? '--'}<span className="text-[9px] font-normal text-white/40">bpm</span>
            </div>
          </div>
        </div>

        {/* Row 3: Progress Rings - 今日进度 */}
        <div className="flex items-center justify-between bg-white/8 rounded-2xl px-3 py-2.5">
          <div className="flex items-center gap-2">
            <MiniRing value={steps} max={8000} color="#818cf8" />
            <div>
              <div className="text-sm font-bold text-white">{steps.toLocaleString()}</div>
              <div className="text-[9px] text-white/40">步数</div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <MiniRing value={activeMin} max={30} color="#f59e0b" />
            <div>
              <div className="text-sm font-bold text-white">{activeMin}</div>
              <div className="text-[9px] text-white/40">活动min</div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <MiniRing value={waterToday.total_ml} max={waterToday.goal_ml} color="#3b82f6" />
            <div>
              <div className="text-sm font-bold text-white">{waterToday.total_ml}</div>
              <div className="text-[9px] text-white/40">饮水ml</div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <MiniRing value={suppChecked} max={Math.max(suppTotal, 1)} color="#a78bfa" />
            <div>
              <div className="text-sm font-bold text-white">{suppChecked}/{suppTotal}</div>
              <div className="text-[9px] text-white/40">补剂</div>
            </div>
          </div>
          {stress != null && (
            <div className="flex items-center gap-2">
              <MiniRing value={Math.max(0, 100 - stress)} max={100} color={stress > 40 ? '#f87171' : '#34d399'} />
              <div>
                <div className="text-sm font-bold text-white">{stress}</div>
                <div className="text-[9px] text-white/40">压力</div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
