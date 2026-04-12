'use client';

import { useRouter } from 'next/navigation';
import type { ReactNode } from 'react';

interface DataGridProps {
  todayGarmin: any;
  dietToday: any;
  bpLatest: any;
  rhinitisToday: any;
  weightStats: any;
}

function BaseCard({
  children,
  onClick,
  background,
}: {
  children: ReactNode;
  onClick: () => void;
  background: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full rounded-[28px] p-4 text-left transition-all duration-200 active:scale-[0.985] hover:shadow-[0_14px_32px_rgba(15,23,42,0.06)]"
      style={{
        background,
        boxShadow: '0 8px 24px rgba(15, 23, 42, 0.04)',
      }}
    >
      {children}
    </button>
  );
}

function TinyBadge({ label, tone }: { label: string; tone: 'green' | 'orange' | 'red' | 'blue' }) {
  const styles = {
    green: { background: 'rgba(52, 199, 89, 0.12)', color: '#16A34A' },
    orange: { background: 'rgba(255, 149, 0, 0.12)', color: '#D97706' },
    red: { background: 'rgba(255, 59, 48, 0.12)', color: '#DC2626' },
    blue: { background: 'rgba(0, 122, 255, 0.10)', color: '#2563EB' },
  }[tone];

  return (
    <span
      className="rounded-full px-2 py-1 text-[10px] font-semibold tracking-[0.02em]"
      style={styles}
    >
      {label}
    </span>
  );
}

function MetricPill({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent: string;
}) {
  return (
    <div
      className="rounded-2xl px-3 py-2"
      style={{ background: '#FFFFFF', boxShadow: 'inset 0 0 0 1px rgba(15,23,42,0.04)' }}
    >
      <div className="text-[10px] font-medium uppercase tracking-[0.08em]" style={{ color: '#94A3B8' }}>
        {label}
      </div>
      <div className="mt-1 text-sm font-semibold" style={{ color: accent }}>
        {value}
      </div>
    </div>
  );
}

function NutritionBar({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color: string;
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-[11px]">
        <span style={{ color: '#64748B' }}>{label}</span>
        <span className="font-semibold" style={{ color: '#0F172A' }}>{value}g</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-white/80">
        <div className="h-full rounded-full" style={{ width: '100%', background: color }} />
      </div>
    </div>
  );
}

export default function DataGrid({ todayGarmin, dietToday, bpLatest, rhinitisToday, weightStats }: DataGridProps) {
  const router = useRouter();

  const sleepDeep = todayGarmin?.deep_sleep_duration || 0;
  const sleepRem = todayGarmin?.rem_sleep_duration || 0;
  const sleepLight = todayGarmin?.light_sleep_duration || 0;
  const sleepTotal = todayGarmin?.total_sleep_duration || 0;
  const sleepH = Math.floor(sleepTotal / 60);
  const sleepM = sleepTotal % 60;
  const spo2 = todayGarmin?.spo2_avg;

  const fmtMin = (m: number) => (m >= 60 ? `${Math.floor(m / 60)}h${m % 60}m` : `${m}m`);
  const sleepStatusTone = (todayGarmin?.sleep_score || 0) >= 85 ? 'green' : (todayGarmin?.sleep_score || 0) >= 75 ? 'blue' : 'orange';
  const rhinitisStable = (rhinitisToday?.sneeze_count ?? 0) < 10;
  const bpNormal = bpLatest && bpLatest.total_records > 0
    ? bpLatest.normal_count >= bpLatest.total_records * 0.8
    : true;

  return (
    <div className="space-y-3.5">
      {sleepTotal > 0 && (
        <BaseCard
          onClick={() => router.push('/garmin')}
          background="linear-gradient(180deg, rgba(245,247,255,0.98) 0%, rgba(238,242,255,0.96) 100%)"
        >
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="text-[11px] font-semibold tracking-[0.08em]" style={{ color: '#6366F1' }}>
                睡眠
              </div>
              <div className="mt-2 flex items-end gap-2">
                <span className="text-5xl font-semibold tracking-[-0.04em]" style={{ color: '#312E81' }}>
                  {todayGarmin?.sleep_score || '--'}
                </span>
                <span className="pb-2 text-sm" style={{ color: '#7C83A3' }}>分</span>
              </div>
            </div>
            <div className="flex flex-col items-end gap-2">
              <TinyBadge label={sleepStatusTone === 'green' ? '恢复良好' : sleepStatusTone === 'blue' ? '状态平稳' : '建议早睡'} tone={sleepStatusTone} />
              <div className="text-sm font-medium" style={{ color: '#7C83A3' }}>
                {sleepH}h{sleepM > 0 ? `${sleepM}m` : ''}
              </div>
            </div>
          </div>

          <div className="mt-4 h-2 overflow-hidden rounded-full bg-white/70">
            {sleepDeep > 0 && <div className="h-full float-left" style={{ width: `${(sleepDeep / sleepTotal) * 100}%`, background: '#3730A3' }} />}
            {sleepRem > 0 && <div className="h-full float-left" style={{ width: `${(sleepRem / sleepTotal) * 100}%`, background: '#6366F1' }} />}
            {sleepLight > 0 && <div className="h-full float-left" style={{ width: `${(sleepLight / sleepTotal) * 100}%`, background: '#C7D2FE' }} />}
          </div>

          <div className="mt-4 grid grid-cols-2 gap-2 md:grid-cols-5">
            <MetricPill label="深睡" value={fmtMin(sleepDeep)} accent="#3730A3" />
            <MetricPill label="REM" value={fmtMin(sleepRem)} accent="#6366F1" />
            <MetricPill label="浅睡" value={fmtMin(sleepLight)} accent="#7C83A3" />
            <MetricPill label="HRV" value={`${todayGarmin?.hrv || '--'}ms`} accent={todayGarmin?.hrv && todayGarmin.hrv < 40 ? '#DC2626' : '#4F46E5'} />
            {spo2 && <MetricPill label="SpO2" value={`${spo2}%`} accent={spo2 < 92 ? '#DC2626' : '#4F46E5'} />}
          </div>
        </BaseCard>
      )}

      <div className="grid grid-cols-1 gap-3.5 md:grid-cols-2">
        <BaseCard
          onClick={() => router.push('/diet')}
          background="linear-gradient(180deg, rgba(255,250,245,0.98) 0%, rgba(255,247,237,0.96) 100%)"
        >
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="text-[11px] font-semibold tracking-[0.08em]" style={{ color: '#F97316' }}>
                饮食
              </div>
              <div className="mt-3 flex items-end gap-1.5">
                <span className="text-4xl font-semibold tracking-[-0.04em]" style={{ color: '#0F172A' }}>
                  {dietToday?.total_calories ? Math.round(dietToday.total_calories) : 0}
                </span>
                <span className="pb-1 text-xs" style={{ color: '#94A3B8' }}>kcal</span>
              </div>
            </div>
            <div className="text-right">
              <TinyBadge label={`${dietToday?.meals_count || 0} 餐`} tone="orange" />
            </div>
          </div>

          <div className="mt-5 space-y-3">
            <NutritionBar label="蛋白质" value={Math.round(dietToday?.total_protein || 0)} color="#FB7185" />
            <NutritionBar label="碳水" value={Math.round(dietToday?.total_carbs || 0)} color="#FB923C" />
            <NutritionBar label="脂肪" value={Math.round(dietToday?.total_fat || 0)} color="#FACC15" />
          </div>
        </BaseCard>

        <BaseCard
          onClick={() => router.push('/rhinitis')}
          background="linear-gradient(180deg, rgba(243,252,247,0.98) 0%, rgba(249,250,239,0.96) 100%)"
        >
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="text-[11px] font-semibold tracking-[0.08em]" style={{ color: '#10B981' }}>
                鼻炎
              </div>
              <div className="mt-2 text-sm" style={{ color: '#64748B' }}>
                今日护理与症状
              </div>
            </div>
            <TinyBadge label={rhinitisStable ? '稳定' : '活跃'} tone={rhinitisStable ? 'green' : 'orange'} />
          </div>

          <div className="mt-5 grid grid-cols-2 gap-3">
            <div className="rounded-2xl bg-white/80 px-4 py-3">
              <div className="text-[11px] font-medium" style={{ color: '#94A3B8' }}>洗鼻</div>
              <div className="mt-2 flex items-end gap-1">
                <span className="text-4xl font-semibold tracking-[-0.04em]" style={{ color: '#111827' }}>{rhinitisToday?.nasal_wash_count ?? 0}</span>
                <span className="pb-1 text-xs" style={{ color: '#94A3B8' }}>次</span>
              </div>
            </div>
            <div className="rounded-2xl bg-white/80 px-4 py-3">
              <div className="text-[11px] font-medium" style={{ color: '#94A3B8' }}>喷嚏</div>
              <div className="mt-2 flex items-end gap-1">
                <span className="text-4xl font-semibold tracking-[-0.04em]" style={{ color: rhinitisStable ? '#111827' : '#F97316' }}>{rhinitisToday?.sneeze_count ?? 0}</span>
                <span className="pb-1 text-xs" style={{ color: '#94A3B8' }}>次</span>
              </div>
            </div>
          </div>
        </BaseCard>
      </div>

      <div className="grid grid-cols-1 gap-3.5 md:grid-cols-2">
        {bpLatest && bpLatest.total_records > 0 && (
          <BaseCard
            onClick={() => router.push('/blood-pressure')}
            background="linear-gradient(180deg, rgba(255,247,247,0.98) 0%, rgba(255,250,250,0.96) 100%)"
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="text-[11px] font-semibold tracking-[0.08em]" style={{ color: '#EF4444' }}>
                  血压
                </div>
                <div className="mt-3 flex items-end gap-1.5">
                  <span className="text-4xl font-semibold tracking-[-0.04em]" style={{ color: '#111827' }}>
                    {Math.round(bpLatest.average_systolic)}/{Math.round(bpLatest.average_diastolic)}
                  </span>
                  <span className="pb-1 text-xs" style={{ color: '#94A3B8' }}>mmHg</span>
                </div>
              </div>
              <TinyBadge label={bpNormal ? '正常' : '偏高'} tone={bpNormal ? 'green' : 'red'} />
            </div>

            <div className="mt-4 flex items-center gap-5 text-sm" style={{ color: '#64748B' }}>
              <span>脉搏 {bpLatest.average_pulse ? Math.round(bpLatest.average_pulse) : '--'}</span>
              <span>{bpLatest.total_records} 次记录</span>
            </div>
          </BaseCard>
        )}

        <BaseCard
          onClick={() => router.push('/weight')}
          background="linear-gradient(180deg, rgba(243,247,255,0.98) 0%, rgba(248,250,255,0.96) 100%)"
        >
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="text-[11px] font-semibold tracking-[0.08em]" style={{ color: '#3B82F6' }}>
                体重
              </div>
              <div className="mt-3 flex items-end gap-1.5">
                <span className="text-4xl font-semibold tracking-[-0.04em]" style={{ color: '#111827' }}>
                  {weightStats?.current_weight || '--'}
                </span>
                <span className="pb-1 text-xs" style={{ color: '#94A3B8' }}>kg</span>
              </div>
            </div>
            {weightStats?.weight_change_30d != null && (
              <TinyBadge
                label={`30天 ${weightStats.weight_change_30d > 0 ? '+' : ''}${weightStats.weight_change_30d}kg`}
                tone={weightStats.weight_change_30d > 0 ? 'red' : 'green'}
              />
            )}
          </div>

          <div className="mt-4 text-sm" style={{ color: '#64748B' }}>
            {weightStats?.weight_change_30d != null
              ? `近 30 天${weightStats.weight_change_30d <= 0 ? '稳步下降' : '略有上升'}`
              : '记录你的长期体重趋势'}
          </div>
        </BaseCard>
      </div>
    </div>
  );
}
