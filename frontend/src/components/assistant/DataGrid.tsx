'use client';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/services/api/client';

interface DataGridProps {
  todayGarmin: any;
  dietToday: any;
  bpLatest: any;
  rhinitisToday: any;
  weightStats: any;
  medToday?: any[];
}

export default function DataGrid({ todayGarmin, dietToday, bpLatest, rhinitisToday, weightStats, medToday }: DataGridProps) {
  const router = useRouter();
  const pressStyle = 'active:scale-[0.98] transition-all duration-150 cursor-pointer';

  // 鼻炎趋势数据
  const [rhinitisTrend, setRhinitisTrend] = useState<any>(null);
  const [showTrend, setShowTrend] = useState(false);
  useEffect(() => {
    api.get('/rhinitis-trend/me?days=7').then(r => setRhinitisTrend(r.data)).catch(() => {});
  }, []);

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
      {/* Row 1: 睡眠（整行） */}
      {sleepTotal > 0 && (
        <div className={`rounded-2xl p-4 ${pressStyle}`}
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

      {/* Row 2: 饮食 + 鼻炎 */}
      <div className="grid grid-cols-2 gap-3">
        {/* 饮食 */}
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

        {/* 鼻炎管理（症状 + 用药） */}
        {(() => {
          // 从 medToday 提取鼻炎相关药物
          const rhinitisMeds = (medToday || []).filter((m: any) =>
            ['莫米松', '西替利嗪', '氯雷他定', 'mometasone', 'cetirizine'].some(k =>
              (m.name || '').toLowerCase().includes(k.toLowerCase())
            )
          );
          return (
            <div className={`rounded-2xl p-4 ${pressStyle}`}
              style={{ background: 'linear-gradient(135deg, #f0fdf4 0%, #fffbf0 100%)', boxShadow: '0 1px 3px rgba(52,199,89,0.08)' }}
              onClick={() => router.push('/rhinitis')}>
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-semibold" style={{ color: '#30D158' }}>👃 鼻炎</span>
                <span className="text-[10px] px-2 py-0.5 rounded-full font-medium"
                  style={{
                    background: (rhinitisToday?.sneeze_count ?? 0) >= 10 ? '#FEF2F2' : '#F0FDF4',
                    color: (rhinitisToday?.sneeze_count ?? 0) >= 10 ? '#FF3B30' : '#30D158',
                  }}>
                  {(rhinitisToday?.sneeze_count ?? 0) >= 10 ? '活跃' : '稳定'}
                </span>
              </div>
              {/* 症状 */}
              <div className="flex items-end gap-5">
                <div>
                  <div className="text-[10px]" style={{ color: '#AEAEB2' }}>洗鼻</div>
                  <div className="text-2xl font-extrabold" style={{ color: '#1C1C1E' }}>
                    {rhinitisToday?.nasal_wash_count ?? 0}<span className="text-[10px] font-normal ml-0.5" style={{ color: '#AEAEB2' }}>次</span>
                  </div>
                </div>
                <div>
                  <div className="text-[10px]" style={{ color: '#AEAEB2' }}>喷嚏</div>
                  <div className="text-2xl font-extrabold" style={{ color: (rhinitisToday?.sneeze_count ?? 0) >= 10 ? '#FF9500' : '#1C1C1E' }}>
                    {rhinitisToday?.sneeze_count ?? 0}<span className="text-[10px] font-normal ml-0.5" style={{ color: '#AEAEB2' }}>次</span>
                  </div>
                </div>
              </div>
              {/* 用药 */}
              {rhinitisMeds.length > 0 && (
                <div className="mt-2 pt-2 space-y-1" style={{ borderTop: '1px solid rgba(52,199,89,0.15)' }}>
                  {rhinitisMeds.map((med: any) => {
                    const taken = (med.taken_count || 0) > 0;
                    const lastLog = med.logs?.[0];
                    const shortName = (med.name || '').includes('莫米松') ? '莫米松' : (med.name || '').includes('西替利嗪') ? '西替利嗪' : med.name?.split(' ')[0] || med.name;
                    return (
                      <div key={med.medication_id} className="flex items-center justify-between">
                        <div className="flex items-center gap-1.5">
                          <span className="text-[10px]">{taken ? '✅' : '⬜'}</span>
                          <span className="text-[11px] font-medium" style={{ color: taken ? '#1C1C1E' : '#AEAEB2' }}>{shortName}</span>
                          <span className="text-[10px]" style={{ color: '#AEAEB2' }}>{med.dosage}</span>
                        </div>
                        {lastLog ? (
                          <span className="text-[10px] font-medium" style={{ color: '#30D158' }}>{lastLog.time}</span>
                        ) : (
                          <span className="text-[10px]" style={{ color: '#AEAEB2' }}>未服</span>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })()}
      </div>

      {/* 鼻炎 7 天趋势（折叠） */}
      {rhinitisTrend && rhinitisTrend.daily && rhinitisTrend.daily.length > 0 && (
        <div className="rounded-2xl px-4 py-3" style={{ background: '#fafff8', border: '1px solid #d9f2d0' }}>
          <button
            onClick={() => setShowTrend(!showTrend)}
            className="w-full flex items-center justify-between text-[10px] font-medium"
            style={{ color: '#30D158' }}
          >
            <span>📊 7 天趋势 · 喷嚏 {rhinitisTrend.summary?.total_sneeze}次 · 洗鼻 {rhinitisTrend.summary?.total_wash}次 · 用药 {rhinitisTrend.summary?.med_adherence_pct}%</span>
            <span style={{ color: '#AEAEB2' }}>{showTrend ? '收起' : '展开'}</span>
          </button>
          {showTrend && (
            <div className="mt-2 space-y-1">
              {/* 柱状图 */}
              <div className="flex items-end gap-1 h-10">
                {rhinitisTrend.daily.map((d: any, i: number) => {
                  const maxVal = Math.max(...rhinitisTrend.daily.map((x: any) => x.sneeze || 0), 1);
                  const h = Math.max(2, ((d.sneeze || 0) / maxVal) * 40);
                  const isToday = d.date === new Date().toISOString().slice(0, 10);
                  return (
                    <div key={i} className="flex-1 flex flex-col items-center gap-0.5">
                      {(d.sneeze || 0) > 0 && <span className="text-[7px]" style={{ color: isToday ? '#FF9500' : '#AEAEB2' }}>{d.sneeze}</span>}
                      <div className="w-full rounded-sm" style={{ height: `${h}px`, background: isToday ? '#FF9500' : (d.sneeze || 0) > 0 ? '#FFD9A8' : '#E5E5EA' }} />
                    </div>
                  );
                })}
              </div>
              <div className="flex gap-1">
                {rhinitisTrend.daily.map((d: any, i: number) => (
                  <div key={i} className="flex-1 text-center text-[7px]" style={{ color: '#AEAEB2' }}>
                    {d.date.slice(5)}
                  </div>
                ))}
              </div>
              {/* 每天明细 */}
              <div className="mt-1.5 space-y-0.5">
                {rhinitisTrend.daily.map((d: any) => (
                  <div key={d.date} className="flex items-center text-[10px] gap-2">
                    <span className="w-12 shrink-0" style={{ color: '#8E8E93' }}>{d.date.slice(5)}</span>
                    <span style={{ color: (d.sneeze || 0) >= 5 ? '#FF9500' : '#1C1C1E' }}>🤧{d.sneeze || 0}</span>
                    <span style={{ color: '#30D158' }}>👃{d.wash || 0}</span>
                    {d.meds && d.meds.length > 0 && d.meds.map((m: any, mi: number) => (
                      <span key={mi} className="text-[9px]" style={{ color: m.taken ? '#30D158' : '#AEAEB2' }}>
                        {m.taken ? '✅' : '⬜'}{m.name}{m.time ? ` ${m.time}` : ''}
                      </span>
                    ))}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Row 3: 血压 + 体重 */}
      <div className="grid grid-cols-2 gap-3">
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

        <div className="rounded-2xl p-4 cursor-pointer hover:shadow-md transition-shadow"
          style={{ background: 'linear-gradient(135deg, #f0f5ff 0%, #f8faff 100%)', boxShadow: '0 1px 3px rgba(0,122,255,0.06)' }}
          onClick={() => router.push('/weight')}>
          <span className="text-xs font-semibold" style={{ color: '#007AFF' }}>⚖️ 体重</span>
          <div className="mt-2 text-3xl font-extrabold" style={{ color: '#1C1C1E' }}>
            {weightStats?.current_weight || '--'}
            <span className="text-[10px] font-normal ml-0.5" style={{ color: '#AEAEB2' }}>kg</span>
          </div>
          <div className="flex items-center gap-3 mt-1">
            {weightStats?.weight_change_7d != null && (
              <span className="text-[10px] font-semibold"
                style={{ color: weightStats.weight_change_7d > 0 ? '#FF3B30' : weightStats.weight_change_7d < 0 ? '#30D158' : '#8E8E93' }}>
                7天 {weightStats.weight_change_7d > 0 ? '+' : ''}{weightStats.weight_change_7d}kg
              </span>
            )}
            {weightStats?.weight_change_30d != null && (
              <span className="text-[10px] font-semibold"
                style={{ color: weightStats.weight_change_30d > 0 ? '#FF3B30' : weightStats.weight_change_30d < 0 ? '#30D158' : '#8E8E93' }}>
                30天 {weightStats.weight_change_30d > 0 ? '+' : ''}{weightStats.weight_change_30d}kg
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
