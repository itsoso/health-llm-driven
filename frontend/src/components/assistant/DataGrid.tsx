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
