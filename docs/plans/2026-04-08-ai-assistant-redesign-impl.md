# AI Assistant 页面 Apple Health 风格重设计 — 实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 `/ai-assistant` 页面从深绿色密集仪表盘重设计为 Apple Health 风格的白底卡片流，全面提升视觉、层次、交互。

**Architecture:** 纯前端样式+布局重构，不改 API/hook。修改 8 个组件文件 + 1 个页面文件。所有数据流、props、API 调用保持不变。

**Tech Stack:** Next.js 14, React, TypeScript, Tailwind CSS, inline styles

---

## 设计规范常量（所有 Task 共用）

在实现时遵循以下色彩和间距规范：

```
页面背景: #F2F2F7
卡片: white, rounded-2xl (16px), shadow: 0 1px 3px rgba(0,0,0,0.08)
标题文字: #1C1C1E
主数据: #1C1C1E, text-4xl/text-3xl
副文字: #8E8E93
标签: #AEAEB2
分割线: #E5E5EA
卡片间距: gap-3 (12px)
卡片内边距: p-4 (16px)
页面边距: px-4 (16px)

维度色:
  睡眠=#5E5CE6  心脏=#FF3B30  运动=#30D158  饮食=#FF9500
  体重=#007AFF  HRV=#BF5AF2   饮水=#00C7BE  补剂=#FF6482
```

---

### Task 1: HeroCard — 白底三层结构

**Files:**
- Modify: `frontend/src/components/assistant/HeroCard.tsx` (全部重写)

**Step 1: 重写 HeroCard 组件**

保留 props 接口 `HeroCardProps` 和 `ScoreRing` 组件（调整颜色）。重写整个 JSX：

```tsx
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
```

**Step 2: 验证构建**

Run: `cd frontend && npm run build 2>&1 | tail -20`
Expected: 编译通过，无 TypeScript 错误

**Step 3: Commit**

```bash
git add frontend/src/components/assistant/HeroCard.tsx
git commit -m "refactor: HeroCard 改为 Apple Health 白底三层结构"
```

---

### Task 2: DataGrid — 白底卡片网格

**Files:**
- Modify: `frontend/src/components/assistant/DataGrid.tsx` (全部重写)

**Step 1: 重写 DataGrid**

保留接口 `DataGridProps` 不变。所有卡片改为白底 + 维度色点缀：

```tsx
'use client';
import { useRouter } from 'next/navigation';

interface DataGridProps {
  todayGarmin: any;
  dietToday: any;
  bpLatest: any;
  rhinitisToday: any;
  weightStats: any;
}

export default function DataGrid({ todayGarmin, dietToday, bpLatest, rhinitisToday, weightStats }: DataGridProps) {
  const router = useRouter();
  const cardStyle = { boxShadow: '0 1px 3px rgba(0,0,0,0.08)' };
  const pressStyle = 'active:scale-[0.98] transition-all duration-150 cursor-pointer';

  const sleepDeep = todayGarmin?.deep_sleep_duration || 0;
  const sleepRem = todayGarmin?.rem_sleep_duration || 0;
  const sleepLight = todayGarmin?.light_sleep_duration || 0;
  const sleepTotal = todayGarmin?.total_sleep_duration || 0;
  const sleepH = Math.floor(sleepTotal / 60);
  const sleepM = sleepTotal % 60;
  const spo2 = todayGarmin?.spo2_avg;

  const fmtMin = (m: number) => m >= 60 ? `${Math.floor(m / 60)}h${m % 60}m` : `${m}m`;

  return (
    <div className="space-y-3">
      {/* Row 1: Sleep (2/3) + Diet (1/3) */}
      <div className="grid grid-cols-3 gap-3">
        {/* Sleep */}
        {sleepTotal > 0 && (
          <div className={`col-span-2 rounded-2xl bg-white p-4 ${pressStyle}`} style={cardStyle}
            onClick={() => router.push('/garmin')}>
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-1.5">
                <div className="w-1.5 h-1.5 rounded-full" style={{ background: '#5E5CE6' }} />
                <span className="text-xs font-semibold" style={{ color: '#1C1C1E' }}>睡眠</span>
              </div>
              <span className="text-xs" style={{ color: '#AEAEB2' }}>{sleepH}h{sleepM > 0 ? `${sleepM}m` : ''}</span>
            </div>
            <div className="flex items-end gap-4">
              <div>
                <span className="text-4xl font-extrabold" style={{ color: '#1C1C1E' }}>{todayGarmin?.sleep_score || '--'}</span>
                <span className="text-sm ml-1" style={{ color: '#AEAEB2' }}>分</span>
              </div>
              <div className="flex-1 space-y-1.5">
                <div className="flex h-2 rounded-full overflow-hidden">
                  {sleepDeep > 0 && <div style={{ width: `${(sleepDeep / sleepTotal) * 100}%`, background: '#3634A3' }} className="rounded-l-full" />}
                  {sleepRem > 0 && <div style={{ width: `${(sleepRem / sleepTotal) * 100}%`, background: '#5E5CE6' }} />}
                  {sleepLight > 0 && <div style={{ width: `${(sleepLight / sleepTotal) * 100}%`, background: '#A5A4F3' }} className="rounded-r-full" />}
                </div>
                <div className="flex items-center gap-3 text-[10px]" style={{ color: '#8E8E93' }}>
                  <span>深睡 {fmtMin(sleepDeep)}</span>
                  <span>REM {fmtMin(sleepRem)}</span>
                  <span>浅睡 {fmtMin(sleepLight)}</span>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-3 mt-2 text-xs">
              <span className="font-semibold" style={{ color: todayGarmin?.hrv && todayGarmin.hrv < 40 ? '#FF3B30' : '#5E5CE6' }}>
                HRV {todayGarmin?.hrv || '--'}ms
              </span>
              {spo2 && <span className="font-semibold" style={{ color: spo2 < 92 ? '#FF3B30' : '#5E5CE6' }}>SpO2 {spo2}%</span>}
            </div>
          </div>
        )}

        {/* Diet */}
        <div className={`rounded-2xl bg-white p-4 ${pressStyle}`} style={cardStyle}
          onClick={() => router.push('/diet')}>
          <div className="flex items-center gap-1.5 mb-2">
            <div className="w-1.5 h-1.5 rounded-full" style={{ background: '#FF9500' }} />
            <span className="text-xs font-semibold" style={{ color: '#1C1C1E' }}>饮食</span>
          </div>
          <div className="text-3xl font-extrabold" style={{ color: '#1C1C1E' }}>
            {dietToday?.total_calories ? Math.round(dietToday.total_calories) : 0}
            <span className="text-[10px] font-normal ml-0.5" style={{ color: '#AEAEB2' }}>kcal</span>
          </div>
          {dietToday?.meals_count > 0 && <div className="text-[10px] mb-2" style={{ color: '#AEAEB2' }}>{dietToday.meals_count}餐</div>}
          <div className="flex gap-2 mt-2">
            {[
              { label: '蛋白', val: Math.round(dietToday?.total_protein || 0), color: '#FF3B30' },
              { label: '碳水', val: Math.round(dietToday?.total_carbs || 0), color: '#FF9500' },
              { label: '脂肪', val: Math.round(dietToday?.total_fat || 0), color: '#FFCC00' },
            ].map(m => (
              <div key={m.label} className="flex-1 text-center">
                <div className="text-xs font-bold" style={{ color: '#1C1C1E' }}>{m.val}g</div>
                <div className="h-1 rounded-full mt-0.5 opacity-70" style={{ background: m.color }} />
                <div className="text-[9px] mt-0.5" style={{ color: '#AEAEB2' }}>{m.label}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Row 2: BP + Weight */}
      <div className="grid grid-cols-2 gap-3">
        {/* Blood Pressure */}
        {bpLatest && bpLatest.total_records > 0 && (
          <div className={`rounded-2xl bg-white p-4 ${pressStyle}`} style={cardStyle}
            onClick={() => router.push('/blood-pressure')}>
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-1.5">
                <div className="w-1.5 h-1.5 rounded-full" style={{ background: '#FF3B30' }} />
                <span className="text-xs font-semibold" style={{ color: '#1C1C1E' }}>血压</span>
              </div>
              {(() => {
                const isNormal = bpLatest.normal_count >= bpLatest.total_records * 0.8;
                return (
                  <span className="text-[10px] px-2 py-0.5 rounded-full font-medium"
                    style={{ background: isNormal ? '#E8FAF0' : '#FEF2F2', color: isNormal ? '#30D158' : '#FF3B30' }}>
                    {isNormal ? '正常' : '偏高'}
                  </span>
                );
              })()}
            </div>
            <div className="text-3xl font-extrabold" style={{ color: '#1C1C1E' }}>
              {Math.round(bpLatest.average_systolic)}<span className="text-lg font-normal" style={{ color: '#AEAEB2' }}>/</span>{Math.round(bpLatest.average_diastolic)}
              <span className="text-[10px] font-normal ml-1" style={{ color: '#AEAEB2' }}>mmHg</span>
            </div>
            <div className="text-[10px] mt-1" style={{ color: '#8E8E93' }}>
              脉搏 {bpLatest.average_pulse ? Math.round(bpLatest.average_pulse) : '--'} · {bpLatest.total_records}次
            </div>
          </div>
        )}

        {/* Weight */}
        <div className="rounded-2xl bg-white p-4" style={cardStyle}>
          <div className="flex items-center gap-1.5 mb-2">
            <div className="w-1.5 h-1.5 rounded-full" style={{ background: '#007AFF' }} />
            <span className="text-xs font-semibold" style={{ color: '#1C1C1E' }}>体重</span>
          </div>
          <div className="text-3xl font-extrabold" style={{ color: '#1C1C1E' }}>
            {weightStats?.current_weight || '--'}
            <span className="text-[10px] font-normal ml-0.5" style={{ color: '#AEAEB2' }}>kg</span>
          </div>
          {weightStats?.weight_change_30d != null && (
            <div className="text-[10px] font-semibold mt-1"
              style={{ color: weightStats.weight_change_30d > 0 ? '#FF3B30' : '#30D158' }}>
              30天 {weightStats.weight_change_30d > 0 ? '+' : ''}{weightStats.weight_change_30d}kg {weightStats.weight_change_30d <= 0 ? '↓' : '↑'}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
```

**Step 2: 验证构建**

Run: `cd frontend && npm run build 2>&1 | tail -20`
Expected: 编译通过

**Step 3: Commit**

```bash
git add frontend/src/components/assistant/DataGrid.tsx
git commit -m "refactor: DataGrid 改为 Apple Health 白底卡片网格"
```

---

### Task 3: StrengthCard — 白底、小圆环、pill 按钮

**Files:**
- Modify: `frontend/src/components/assistant/StrengthCard.tsx` (样式重写)

**Step 1: 更新 StrengthCard 样式**

保留全部业务逻辑（state、API calls、loadData、recordExercise），只改 JSX return 部分。关键变更：

- 外层：`bg-white rounded-2xl p-4` + `boxShadow: '0 1px 3px rgba(0,0,0,0.08)'`
- 进度环：缩小到 48px，轨道色 `#E5E5EA`，完成色 `#30D158`，已完成(>=100%)用 `#30D158`
- 快速按钮：`rounded-full bg-[#F2F2F7] text-[#1C1C1E] text-[11px] px-3 py-1`，hover 时变对应 color 的浅色
- 周 sparkline：今日用 `#30D158`，其他天有数据用 `#30D158` opacity-30，无数据用 `#E5E5EA`
- 标题/数据文字全部用 `#1C1C1E`，副文字用 `#8E8E93`

具体改动是替换 return 语句中的所有 className 和 style。保留原有的 `showDetail` 逻辑。

**重写 return 部分 (从 `return (` 到文件末尾):**

```tsx
  return (
    <div className="rounded-2xl bg-white p-4" style={{ boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-lg">{icon}</span>
          <span className="text-sm font-bold" style={{ color: '#1C1C1E' }}>{exerciseType}</span>
        </div>
        <button onClick={() => setShowDetail(!showDetail)} className="text-[10px] hover:opacity-70" style={{ color: '#8E8E93' }}>
          {showDetail ? '收起' : '详情'}
        </button>
      </div>

      <div className="flex items-center gap-4">
        <div className="relative shrink-0">
          <svg width={48} height={48} className="-rotate-90">
            <circle cx={24} cy={24} r={20} fill="none" stroke="#E5E5EA" strokeWidth={4} />
            <circle cx={24} cy={24} r={20} fill="none" stroke="#30D158"
              strokeWidth={4} strokeDasharray={`${2 * Math.PI * 20 * Math.min(pct, 100) / 100} ${2 * Math.PI * 20}`}
              strokeLinecap="round" className="transition-all duration-500" />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-sm font-extrabold" style={{ color: '#1C1C1E' }}>{todayTotal}</span>
            <span className="text-[7px]" style={{ color: '#AEAEB2' }}>/{dailyTarget}</span>
          </div>
        </div>

        <div className="flex-1 min-w-0">
          <div className="text-[10px] mb-1.5" style={{ color: '#8E8E93' }}>第{todaySets + 1}组</div>
          <div className="flex flex-wrap gap-1.5">
            {quickAmounts.map(n => (
              <button key={n} onClick={() => recordExercise(n)} disabled={recording}
                className="px-2.5 py-1 rounded-full text-[11px] font-semibold transition-all active:scale-95"
                style={{
                  background: recording ? '#E5E5EA' : '#F2F2F7',
                  color: recording ? '#AEAEB2' : '#1C1C1E',
                }}>+{n}</button>
            ))}
          </div>
          {todayTotal > 0 && (
            <div className="text-[10px] mt-1" style={{ color: '#8E8E93' }}>{todaySets}组 · {pct}%</div>
          )}
        </div>
      </div>

      {weekData.length > 0 && (
        <div className="mt-3 pt-2.5" style={{ borderTop: '1px solid #E5E5EA' }}>
          <div className="flex items-end gap-1 h-7">
            {weekData.map((val, i) => {
              const h = maxWeek > 0 ? Math.max(2, (val / maxWeek) * 28) : 2;
              const isToday = i === todayIdx;
              return (
                <div key={i} className="flex-1 rounded-sm transition-all"
                  style={{ height: `${h}px`, background: isToday ? '#30D158' : val > 0 ? 'rgba(48,209,88,0.3)' : '#E5E5EA' }} />
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

      {showDetail && records.length > 0 && (
        <div className="mt-2.5 pt-2.5 space-y-1" style={{ borderTop: '1px solid #E5E5EA' }}>
          {records.map((r, i) => (
            <div key={r.id} className="flex items-center justify-between text-xs">
              <span style={{ color: '#8E8E93' }}>第{i + 1}组</span>
              <span className="font-bold" style={{ color: '#1C1C1E' }}>{r.reps} 个</span>
              <span style={{ color: '#AEAEB2' }}>{new Date(r.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
```

注意：StrengthCard 的 props 中 `colorLight`, `colorText`, `colorBorder`, `colorBar`, `colorBarLight` 不再需要（样式硬编码为 Apple Health 风格），但 **保留 props 接口不变**，避免改调用方。这些 props 在新版中直接不使用。

**Step 2: 验证构建**

Run: `cd frontend && npm run build 2>&1 | tail -20`

**Step 3: Commit**

```bash
git add frontend/src/components/assistant/StrengthCard.tsx
git commit -m "refactor: StrengthCard 改为 Apple Health 白底样式"
```

---

### Task 4: WorkoutCard + SupplementCheckin — 白底样式

**Files:**
- Modify: `frontend/src/components/assistant/WorkoutCard.tsx`
- Modify: `frontend/src/components/assistant/SupplementCheckin.tsx`

**Step 1: 更新 WorkoutCard 样式**

保留全部逻辑，只改 JSX 样式。关键变更：

- 外层：`bg-white rounded-2xl p-4` + cardStyle
- 标题前加运动色点 `#30D158`
- 数据文字 `#1C1C1E`，副文字 `#8E8E93`/`#AEAEB2`
- 最近运动条：从 `bg-emerald-50` 改为 `bg-[#F2F2F7]`，文字颜色用 `#1C1C1E` 和 `#8E8E93`
- Sparkline：今日 `#30D158`，其他天 `rgba(48,209,88,0.3)`，无数据 `#E5E5EA`

对照原始 WorkoutCard.tsx (行 109-188)，替换所有 tailwind 颜色类：
- `text-gray-800` → `style={{ color: '#1C1C1E' }}`
- `text-gray-400` / `text-gray-500` → `style={{ color: '#8E8E93' }}`
- `text-orange-500` → `style={{ color: '#FF9500' }}`
- `bg-emerald-50` → `style={{ background: '#F2F2F7' }}`
- `text-emerald-700` / `text-emerald-600` → `style={{ color: '#30D158' }}`
- `bg-emerald-500` → `#30D158`，`bg-emerald-200` → `rgba(48,209,88,0.3)`，`bg-gray-100` → `#E5E5EA`
- `border-gray-100` → 移除或改为 `border: none`
- 添加 `active:scale-[0.98] transition-all duration-150` 到外层

**Step 2: 更新 SupplementCheckin 样式**

保留全部逻辑。关键变更：

- 外层：`bg-white rounded-2xl p-4` + cardStyle
- 标题前加补剂色点 `#FF6482`
- checkbox 已选：从 `bg-emerald-500` → `background: '#FF6482'`
- checkbox 未选：`border: 2px solid #AEAEB2`
- 文字颜色统一用设计规范
- 时段标签颜色 `#8E8E93`
- 展开按钮：从 `text-emerald-600` → `color: '#007AFF'`

**Step 3: 验证构建**

Run: `cd frontend && npm run build 2>&1 | tail -20`

**Step 4: Commit**

```bash
git add frontend/src/components/assistant/WorkoutCard.tsx frontend/src/components/assistant/SupplementCheckin.tsx
git commit -m "refactor: WorkoutCard + SupplementCheckin 改为 Apple Health 白底样式"
```

---

### Task 5: QuickRecordBar — 简化为纯 pill 横排

**Files:**
- Modify: `frontend/src/components/assistant/QuickRecordBar.tsx`

**Step 1: 简化 QuickRecordBar**

移除 `navItems` 数组和展开入口功能（这部分已在顶部导航的"功能"菜单中存在）。保留 `quickActions` 数组。

新的 return JSX：

```tsx
  return (
    <div className="flex items-center gap-2">
      <span className="text-[10px] font-medium shrink-0" style={{ color: '#8E8E93' }}>快速记录</span>
      <div className="flex-1 flex gap-1.5 overflow-x-auto">
        {quickActions.map((a, i) => (
          <button key={i} onClick={async () => { try { await a.action(); } catch (e) { console.error(e); } }}
            className="shrink-0 flex items-center gap-1 px-3 py-1.5 rounded-full text-[11px] font-medium transition-all active:scale-95"
            style={{ background: '#F2F2F7', color: '#1C1C1E' }}>
            <span className="text-sm">{a.icon}</span>
            <span>{a.label}</span>
          </button>
        ))}
      </div>
      {quickToast && (
        <div className="fixed top-16 left-1/2 -translate-x-1/2 z-50 px-4 py-2 rounded-full bg-white text-xs font-medium animate-in fade-in slide-in-from-top duration-200"
          style={{ boxShadow: '0 4px 12px rgba(0,0,0,0.12)', color: '#1C1C1E' }}>
          {quickToast}
        </div>
      )}
    </div>
  );
```

同时移除 `navExpanded` state 和 `navItems` 数组（不再需要）。移除 `useRouter` import（不再用到）。

**Step 2: 验证构建**

Run: `cd frontend && npm run build 2>&1 | tail -20`

**Step 3: Commit**

```bash
git add frontend/src/components/assistant/QuickRecordBar.tsx
git commit -m "refactor: QuickRecordBar 简化为纯 pill 横排，移除导航展开"
```

---

### Task 6: AlertsBanner — 白底卡片样式

**Files:**
- Modify: `frontend/src/components/assistant/AlertsBanner.tsx`

**Step 1: 更新 AlertsBanner 样式**

保留全部逻辑。只改 JSX 样式：

```tsx
  return (
    <div className="space-y-2">
      {alerts.map((a, i) => (
        <div key={i} className="rounded-2xl bg-white px-4 py-3 flex items-center gap-3 active:scale-[0.98] transition-all duration-150"
          style={{ boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
          <span className="text-base shrink-0">{a.icon}</span>
          <span className="flex-1 text-sm font-medium" style={{ color: a.color }}>{a.text}</span>
          <button onClick={a.onAction} className="shrink-0 px-3 py-1 rounded-full text-xs font-semibold text-white active:scale-95 transition-all" style={{ background: a.color }}>{a.actionLabel}</button>
        </div>
      ))}
    </div>
  );
```

**Step 2: 验证构建**

Run: `cd frontend && npm run build 2>&1 | tail -20`

**Step 3: Commit**

```bash
git add frontend/src/components/assistant/AlertsBanner.tsx
git commit -m "refactor: AlertsBanner 改为 Apple Health 白底卡片"
```

---

### Task 7: InlineResponse — 白底卡片样式

**Files:**
- Modify: `frontend/src/components/assistant/InlineResponse.tsx`

**Step 1: 更新 InlineResponse 样式**

将绿色渐变背景改为白底卡片：

```tsx
const InlineResponse = forwardRef<HTMLDivElement, InlineResponseProps>(
  ({ question, answer, loading, onClose }, ref) => (
    <div ref={ref} className="rounded-2xl bg-white overflow-hidden" style={{ boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
      <div className="px-4 pt-4 pb-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 rounded-lg flex items-center justify-center" style={{ background: '#007AFF' }}>
            <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" /></svg>
          </div>
          <span className="text-xs rounded-full px-2.5 py-0.5 font-medium" style={{ color: '#007AFF', background: '#F2F2F7' }}>{question}</span>
        </div>
        <button onClick={onClose}
          className="w-6 h-6 rounded-full flex items-center justify-center hover:bg-gray-100 transition-all text-sm"
          style={{ color: '#AEAEB2' }}>×</button>
      </div>
      <div className="px-4 pb-4 text-sm leading-relaxed max-h-[50vh] overflow-y-auto" style={{ color: '#1C1C1E' }}>
        {answer ? (
          <MarkdownRenderer content={answer} variant="light" />
        ) : loading ? (
          <div className="flex items-center gap-2 py-2" style={{ color: '#007AFF' }}>
            <div className="flex gap-1">
              <div className="w-1.5 h-1.5 rounded-full animate-bounce" style={{ background: '#007AFF', animationDelay: '0ms' }} />
              <div className="w-1.5 h-1.5 rounded-full animate-bounce" style={{ background: '#007AFF', animationDelay: '150ms' }} />
              <div className="w-1.5 h-1.5 rounded-full animate-bounce" style={{ background: '#007AFF', animationDelay: '300ms' }} />
            </div>
            <span className="text-xs">思考中...</span>
          </div>
        ) : null}
      </div>
      {loading && answer && (
        <div className="px-4 pb-3 flex items-center gap-1.5">
          <div className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: '#007AFF' }} />
          <span className="text-[11px]" style={{ color: '#007AFF' }}>生成中...</span>
        </div>
      )}
    </div>
  )
);
```

**Step 2: 验证构建**

Run: `cd frontend && npm run build 2>&1 | tail -20`

**Step 3: Commit**

```bash
git add frontend/src/components/assistant/InlineResponse.tsx
git commit -m "refactor: InlineResponse 改为 Apple Health 白底卡片"
```

---

### Task 8: page.tsx — 页面布局、背景、底部固定区域

**Files:**
- Modify: `frontend/src/app/ai-assistant/page.tsx`

这是最大的改动。保留全部业务逻辑（state、handlers、effects），只改布局和样式。

**Step 1: 更新 Toast 组件样式**

将 Toast 组件（行 49-62）改为白底卡片风格：

替换 Toast 的 return JSX：
```tsx
function Toast({ color, title, subtitle, onClose, action }: { color: string; title: string; subtitle: string; onClose: () => void; action?: { label: string; onClick: () => void } }) {
  const dotColors: Record<string, string> = { emerald: '#30D158', cyan: '#00C7BE', blue: '#007AFF' };
  return (
    <div className="fixed left-1/2 top-5 z-[60] w-[min(92vw,420px)] -translate-x-1/2 animate-in fade-in slide-in-from-top duration-300">
      <div className="rounded-2xl bg-white px-5 py-4 shadow-lg" style={{ boxShadow: '0 4px 20px rgba(0,0,0,0.12)' }}>
        <div className="flex items-start gap-3">
          <div className="w-2 h-2 rounded-full mt-1.5 shrink-0" style={{ background: dotColors[color] || dotColors.emerald }} />
          <div className="flex-1 min-w-0">
            <div className="text-sm font-semibold" style={{ color: '#1C1C1E' }}>{title}</div>
            <div className="mt-0.5 text-xs" style={{ color: '#8E8E93' }}>{subtitle}</div>
          </div>
          <button onClick={onClose} className="text-gray-300 hover:text-gray-500 text-lg leading-none">×</button>
        </div>
        {action && <button onClick={action.onClick} className="mt-3 w-full rounded-xl px-3 py-2 text-sm font-medium transition-colors" style={{ background: '#F2F2F7', color: '#007AFF' }}>{action.label}</button>}
      </div>
    </div>
  );
}
```

**Step 2: 更新页面背景和布局**

找到行 422 `return (` 开始的 JSX。需要改以下部分：

**2a. 顶部 header（行 425-475）：**
保持结构不变，只改细节：
- `bg-white/80` → `bg-white/85 backdrop-blur-xl`（已有 backdrop-blur-md，改为 xl）
- 绿色 logo 圆形保留
- 头像按钮颜色保留

**2b. 页面背景（行 477-486）：**
欢迎页（isWelcome）背景改为：
```tsx
<div className="absolute inset-0" style={{ background: '#F2F2F7' }} />
```
聊天模式背景保持不变（暗色）。

**2c. 滚动内容区域（行 500-566）：**
- 将 `max-w-5xl mx-auto space-y-3` 改为 `max-w-2xl mx-auto space-y-3 pb-40`（pb-40 为底部固定区域留空间）
- 在力量训练卡片前面不需要额外改动

**2d. 底部输入区域（行 588-621）：**
这是最关键的改动。isWelcome 模式下，底部变为固定区域：

替换行 588-621 的整个输入栏 JSX：

```tsx
{/* Bottom fixed area */}
<div className={`${isWelcome ? 'absolute bottom-0 left-0 right-0 z-30' : 'border-t border-white/10 bg-slate-950/55 backdrop-blur-2xl'}`}>
  {/* Quick record bar (welcome mode only) */}
  {isWelcome && (
    <div className="px-4 pt-3 pb-2" style={{ background: 'rgba(255,255,255,0.85)', backdropFilter: 'blur(20px)', borderTop: '1px solid #E5E5EA' }}>
      <QuickRecordBar rhinitisToday={dashboard.rhinitisToday} onWaterRecord={handleWaterRecord} onRhinitisUpdate={dashboard.setRhinitisToday} />
    </div>
  )}
  {/* Input */}
  <div className="px-4 py-3" style={isWelcome ? { background: 'rgba(255,255,255,0.85)', backdropFilter: 'blur(20px)' } : undefined}>
    <div className={`mx-auto max-w-2xl ${isWelcome ? 'rounded-[24px] border border-gray-200 bg-[#F2F2F7]' : 'rounded-[30px] border border-white/10 bg-white/[0.04] shadow-[0_20px_60px_rgba(2,6,23,0.35)]'}`}>
      <div className="flex items-center gap-3 px-4 py-2.5 pb-[max(0.625rem,env(safe-area-inset-bottom))]">
        {/* 保持原有的 file input, attach button, voice button, text input, new chat button, send button 不变，只改颜色 */}
        <input ref={fileInputRef} type="file" accept="image/*,.pdf,.txt,.md,.csv,.json,.py,.js,.ts,.html,.xml,.log,.yaml,.yml" className="hidden" onChange={handleImageUpload} />
        <button onClick={() => fileInputRef.current?.click()} disabled={imageUploading}
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-all"
          style={isWelcome ? { color: '#AEAEB2' } : { color: imageUploading ? '#fff' : '#94a3b8' }} title="上传图片或文件">
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M18.375 12.739l-7.693 7.693a4.5 4.5 0 01-6.364-6.364l10.94-10.94A3 3 0 1119.5 7.372L8.552 18.32m.009-.01l-.01.01m5.699-9.941l-7.81 7.81a1.5 1.5 0 002.112 2.13" /></svg>
        </button>
        <button onClick={handleVoiceToggle}
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-all"
          style={isWelcome ? { color: isRecording ? '#FF3B30' : '#AEAEB2' } : { color: isRecording ? '#fff' : '#94a3b8', background: isRecording ? '#FF3B30' : undefined }} title={isRecording ? '停止录音' : '语音输入'}>
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            {isRecording ? <rect x="6" y="6" width="12" height="12" rx="2" /> : <path strokeLinecap="round" strokeLinejoin="round" d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 116 0v8.25a3 3 0 01-3 3z" />}
          </svg>
        </button>
        <input type="text" value={inputText} onChange={(e) => setInputText(e.target.value)} onKeyDown={handleKeyDown} onPaste={handlePaste}
          placeholder={isRecording ? '正在录音...' : (pendingImage || pendingFile) ? '输入描述或问题（可直接发送）' : '用一句完整目标开始...'}
          className="flex-1 bg-transparent text-sm outline-none"
          style={isWelcome ? { color: '#1C1C1E' } : { color: '#fff' }}
          disabled={isRecording} />
        {inlineMode && (
          <button onClick={() => { setInlineMode(false); setInlineResponse(null); setMessages([]); setConversationId(undefined); }}
            className="shrink-0 px-2.5 py-1.5 rounded-lg text-[11px] font-medium border transition-all"
            style={{ color: '#007AFF', borderColor: '#007AFF40' }}>新开对话</button>
        )}
        {!inlineMode && hasMessages && (
          <button onClick={() => { setInlineMode(true); setMessages([]); setConversationId(undefined); }}
            className="shrink-0 px-2.5 py-1.5 rounded-lg text-[11px] font-medium border transition-all"
            style={{ color: '#8E8E93', borderColor: '#E5E5EA' }}>首页</button>
        )}
        <button onClick={() => handleSend()} disabled={!inputText.trim() && !pendingImage && !pendingFile}
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-all active:scale-95"
          style={{ background: (inputText.trim() || pendingImage || pendingFile) ? '#007AFF' : (isWelcome ? '#E5E5EA' : 'rgba(255,255,255,0.08)'), color: (inputText.trim() || pendingImage || pendingFile) ? '#fff' : '#AEAEB2' }}>
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M4.5 10.5L12 3m0 0l7.5 7.5M12 3v18" /></svg>
        </button>
      </div>
    </div>
  </div>
</div>
```

**Step 3: 移动 QuickRecordBar 到底部固定区域**

在 isWelcome 的 dashboard 内容中，移除 QuickRecordBar 的调用（行 519）。它现在渲染在底部固定区域中。

同时从 dashboard 卡片流中 `space-y-3` 的内容里删除 `<QuickRecordBar ... />` 那行。

**Step 4: 更新 max-width**

将 `max-w-5xl` 改为 `max-w-2xl`（让卡片流更紧凑，更像手机端体验）。

在行 502-503:
```
<div className="mx-auto max-w-6xl">  →  <div className="mx-auto max-w-2xl">
```

在行 504:
```
<div className="max-w-5xl mx-auto space-y-3">  →  <div className="space-y-3 pb-44">
```

**Step 5: 验证构建**

Run: `cd frontend && npm run build 2>&1 | tail -20`
Expected: 编译通过

**Step 6: Commit**

```bash
git add frontend/src/app/ai-assistant/page.tsx
git commit -m "refactor: AI Assistant 页面改为 Apple Health 风格布局"
```

---

### Task 9: 视觉验证 + 微调

**Files:**
- 可能修改上述任何文件

**Step 1: 启动 dev server 并检查**

Run: `cd frontend && npm run dev`

检查项：
1. 页面背景是否为 `#F2F2F7` 浅灰
2. 所有卡片是否白底圆角
3. HeroCard 三层结构是否正确显示
4. 数据卡片网格是否 2/3 + 1/3 分割
5. 力量训练卡片样式是否一致
6. 底部快速记录 + AI 输入是否固定
7. 发送消息后是否正常进入聊天模式
8. 移动端响应式是否正常

**Step 2: 修复发现的问题**

根据实际渲染效果微调间距、字号、颜色。

**Step 3: 最终构建验证**

Run: `cd frontend && npm run build 2>&1 | tail -20`
Expected: 编译通过，无警告

**Step 4: Commit**

```bash
git add -A
git commit -m "fix: AI Assistant 重设计视觉微调"
```
