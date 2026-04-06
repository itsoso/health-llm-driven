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

export default function HeroCard({ user, healthScore, todayGarmin, waterToday, suppChecked, suppTotal, weatherData, airData, onRefresh }: HeroCardProps) {
  const h = new Date().getHours();
  const greeting = h < 6 ? '夜深了' : h < 11 ? '早上好' : h < 14 ? '中午好' : h < 18 ? '下午好' : '晚上好';
  const displayName = user?.name || user?.username || '';
  const score = healthScore?.total_score || 0;
  const scoreColor = score >= 80 ? '#34d399' : score >= 60 ? '#fbbf24' : '#f87171';
  const scoreLabel = score >= 80 ? '状态优秀' : score >= 60 ? '需要关注' : '需要改善';
  const stepsTarget = 8000;
  const stepsVal = todayGarmin?.steps || 0;
  const stepsPct = Math.min(100, Math.round((stepsVal / stepsTarget) * 100));
  const waterPct = Math.min(100, Math.round((waterToday.total_ml / waterToday.goal_ml) * 100));
  const suppPct = suppTotal > 0 ? Math.round((suppChecked / suppTotal) * 100) : 0;

  const quickMetrics = [
    { icon: '😴', val: todayGarmin?.sleep_score, unit: '分', label: '睡眠', warn: (v: number) => v < 70 },
    { icon: '❤️', val: todayGarmin?.resting_heart_rate || todayGarmin?.avg_heart_rate, unit: 'bpm', label: '心率', warn: (v: number) => v < 45 || v > 75 },
    { icon: '🔋', val: todayGarmin?.body_battery_most_charged, unit: '', label: '电量', sub: todayGarmin?.body_battery_current != null ? `现${todayGarmin.body_battery_current}` : '', warn: (v: number) => v < 60 },
    { icon: '😌', val: todayGarmin?.stress_level, unit: '', label: '压力', warn: (v: number) => v > 40 },
    { icon: '🚶', val: stepsVal, unit: '', label: '步数', pct: stepsPct, color: '#6366f1', warn: (v: number) => v < 5000 },
    { icon: '💧', val: waterToday.total_ml, unit: 'ml', label: '饮水', pct: waterPct, color: '#3b82f6', warn: () => false },
    { icon: '💊', val: `${suppChecked}/${suppTotal}`, unit: '', label: '补剂', pct: suppPct, color: '#8b5cf6', warn: () => false },
  ];

  return (
    <div className="rounded-3xl p-5 relative overflow-hidden shadow-lg"
      style={{ background: 'linear-gradient(135deg, #065f46 0%, #047857 40%, #059669 100%)' }}>
      <div className="absolute -top-12 -right-12 w-40 h-40 rounded-full" style={{ background: 'rgba(255,255,255,0.06)' }} />
      <div className="absolute -bottom-8 -left-8 w-24 h-24 rounded-full" style={{ background: 'rgba(255,255,255,0.04)' }} />
      <div className="relative z-10">
        {/* Row 1: Greeting + Score */}
        <div className="flex items-center gap-4 mb-3">
          <div className="relative shrink-0">
            <AnimatedRing score={score} size={64} strokeWidth={5} />
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-xl font-extrabold text-white">{score || '--'}</span>
              <span className="text-[8px] text-emerald-200/60 font-medium">健康分</span>
            </div>
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between">
              <h1 className="text-lg font-bold text-white tracking-tight">{greeting}{displayName ? `，${displayName}` : ''}</h1>
              <button onClick={onRefresh}
                className="text-[10px] text-white/50 hover:text-white transition-colors flex items-center gap-1 bg-white/10 rounded-full px-2.5 py-1">
                <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                刷新
              </button>
            </div>
            <div className="flex items-center gap-2 mt-0.5 flex-wrap">
              <p className="text-emerald-200/70 text-xs">{new Date().toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' })}</p>
              {weatherData && (
                <span className="text-[10px] text-emerald-200/60">
                  {weatherData.city} {Math.round(weatherData.temperature ?? 0)}° {weatherData.weather || ''}
                  {airData ? ` · AQI ${airData.aqi || '--'}${airData.pm25 != null ? ` · PM2.5 ${airData.pm25}` : ''}` : ''}
                </span>
              )}
              <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full text-white" style={{ background: `${scoreColor}40`, border: `1px solid ${scoreColor}60` }}>{scoreLabel}</span>
              {healthScore?.dimensions && Array.isArray(healthScore.dimensions) && (() => {
                const dims = healthScore.dimensions as any[];
                const worst = dims.reduce((a: any, b: any) => (b.score < a.score ? b : a), dims[0]);
                return worst && worst.score < 40 ? (
                  <span className="text-[9px] px-1.5 py-0.5 rounded-full font-medium bg-red-500/20 text-red-200 border border-red-400/30">{worst.name} 偏低</span>
                ) : null;
              })()}
            </div>
          </div>
        </div>
        {/* Row 2: Quick Metrics */}
        <div className="grid grid-cols-7 gap-1 bg-white/8 rounded-2xl p-2">
          {quickMetrics.map((m: any) => {
            const v = typeof m.val === 'number' ? m.val : null;
            const isWarn = v != null && m.warn(v);
            const displayVal = typeof m.val === 'number' ? (m.val >= 1000 ? m.val.toLocaleString() : m.val) : (m.val ?? '--');
            return (
              <div key={m.label} className={`rounded-xl py-1.5 px-0.5 text-center ${isWarn ? 'bg-amber-500/20' : ''}`}>
                <span className="text-sm">{m.icon}</span>
                <div className={`text-sm font-extrabold leading-tight ${isWarn ? 'text-amber-300' : 'text-white'}`}>
                  {displayVal}<span className="text-[8px] font-normal text-white/40">{m.unit}</span>
                </div>
                <div className="text-[9px] text-white/50 font-medium">{m.label}</div>
                {m.sub && <div className="text-[8px] text-white/40 leading-tight">{m.sub}</div>}
                {m.pct != null && (
                  <div className="mt-0.5 h-1 bg-white/10 rounded-full overflow-hidden mx-1">
                    <div className="h-full rounded-full transition-all duration-500" style={{ width: `${m.pct}%`, background: m.color }} />
                  </div>
                )}
              </div>
            );
          })}
        </div>
        {/* Row 3: Dimension bars */}
        {healthScore?.dimensions && Array.isArray(healthScore.dimensions) && (
          <div className="grid grid-cols-6 gap-1.5 mt-2">
            {(healthScore.dimensions as any[]).map((dim: any) => {
              const s = dim.score || 0;
              const barColor = s >= 70 ? '#34d399' : s >= 40 ? '#fbbf24' : '#f87171';
              return (
                <div key={dim.name} className="text-center">
                  <div className="text-[10px] text-white/60 mb-0.5">{dim.name}</div>
                  <div className="h-2 rounded-full bg-white/12 overflow-hidden">
                    <div className="h-full rounded-full transition-all duration-700" style={{ width: `${s}%`, background: barColor }} />
                  </div>
                  <div className="text-[10px] font-semibold text-white/50 mt-0.5">{s}</div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
