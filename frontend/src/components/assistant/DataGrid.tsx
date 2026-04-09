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
        {/* Sleep - indigo tint */}
        {sleepTotal > 0 && (
          <div className={`col-span-2 rounded-2xl p-4 ${pressStyle}`}
            style={{ background: 'linear-gradient(135deg, #f0f0ff 0%, #f8f7ff 100%)', boxShadow: '0 1px 3px rgba(94,92,230,0.08)' }}
            onClick={() => router.push('/garmin')}>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold" style={{ color: '#5E5CE6' }}>😴 睡眠分析</span>
              <span className="text-xs" style={{ color: '#8E8E93' }}>{sleepH}h{sleepM > 0 ? `${sleepM}m` : ''}</span>
            </div>
            <div className="flex items-end gap-4">
              <div>
                <span className="text-4xl font-extrabold" style={{ color: '#3634A3' }}>{todayGarmin?.sleep_score || '--'}</span>
                <span className="text-sm ml-1" style={{ color: '#8E8E93' }}>分</span>
              </div>
              <div className="flex-1 space-y-1.5">
                <div className="flex h-2.5 rounded-full overflow-hidden">
                  {sleepDeep > 0 && <div style={{ width: `${(sleepDeep / sleepTotal) * 100}%`, background: '#3634A3' }} className="rounded-l-full" />}
                  {sleepRem > 0 && <div style={{ width: `${(sleepRem / sleepTotal) * 100}%`, background: '#5E5CE6' }} />}
                  {sleepLight > 0 && <div style={{ width: `${(sleepLight / sleepTotal) * 100}%`, background: '#B4B3F1' }} className="rounded-r-full" />}
                </div>
                <div className="flex items-center gap-3 text-[10px]" style={{ color: '#6E6DAA' }}>
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

        {/* Diet - warm orange tint */}
        <div className={`rounded-2xl p-4 ${pressStyle}`}
          style={{ background: 'linear-gradient(135deg, #fff8f0 0%, #fffcf8 100%)', boxShadow: '0 1px 3px rgba(255,149,0,0.08)' }}
          onClick={() => router.push('/diet')}>
          <span className="text-xs font-semibold" style={{ color: '#FF9500' }}>🍽️ 饮食</span>
          <div className="mt-2">
            <div className="text-3xl font-extrabold" style={{ color: '#1C1C1E' }}>
              {dietToday?.total_calories ? Math.round(dietToday.total_calories) : 0}
              <span className="text-[10px] font-normal ml-0.5" style={{ color: '#AEAEB2' }}>kcal</span>
            </div>
            {dietToday?.meals_count > 0 && <div className="text-[10px] mb-1" style={{ color: '#AEAEB2' }}>{dietToday.meals_count}餐</div>}
          </div>
          <div className="flex gap-2 mt-2">
            {[
              { label: '蛋白', val: Math.round(dietToday?.total_protein || 0), color: '#FF6B6B' },
              { label: '碳水', val: Math.round(dietToday?.total_carbs || 0), color: '#FF9500' },
              { label: '脂肪', val: Math.round(dietToday?.total_fat || 0), color: '#FFD60A' },
            ].map(m => (
              <div key={m.label} className="flex-1 text-center">
                <div className="text-xs font-bold" style={{ color: '#1C1C1E' }}>{m.val}g</div>
                <div className="h-1 rounded-full mt-0.5" style={{ background: m.color, opacity: 0.7 }} />
                <div className="text-[9px] mt-0.5" style={{ color: '#AEAEB2' }}>{m.label}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Row 2: BP + Weight */}
      <div className="grid grid-cols-2 gap-3">
        {/* Blood Pressure - subtle red tint */}
        {bpLatest && bpLatest.total_records > 0 && (
          <div className={`rounded-2xl p-4 ${pressStyle}`}
            style={{ background: 'linear-gradient(135deg, #fff5f5 0%, #fffbfb 100%)', boxShadow: '0 1px 3px rgba(255,59,48,0.06)' }}
            onClick={() => router.push('/blood-pressure')}>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold" style={{ color: '#FF3B30' }}>🩺 血压</span>
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

        {/* Weight - blue tint */}
        <div className="rounded-2xl p-4 cursor-pointer hover:shadow-md transition-shadow"
          style={{ background: 'linear-gradient(135deg, #f0f5ff 0%, #f8faff 100%)', boxShadow: '0 1px 3px rgba(0,122,255,0.06)' }}
          onClick={() => router.push('/weight')}>
          <span className="text-xs font-semibold" style={{ color: '#007AFF' }}>⚖️ 体重</span>
          <div className="mt-2 text-3xl font-extrabold" style={{ color: '#1C1C1E' }}>
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
