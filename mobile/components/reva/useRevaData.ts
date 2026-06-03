/**
 * 复元 Reva — real-data hook. Maps existing mobile data sources onto the fields
 * the Reva screens need, with honest fallbacks where no source exists
 * (readiness has no standalone endpoint → body-battery/sleep proxy; fasting
 * glucose / reminders have no mobile source → omitted, not faked).
 *
 * React Query keys are stable so calling this from multiple Reva views dedupes.
 */
import { useQuery } from '@tanstack/react-query';
import { useDashboardData, useLatestGarmin } from '../../hooks/useDashboardData';
import { listMedicalExams, type MedicalExam } from '../../services/medicalExams';
import { getDailyOperatingPlan, type DailyPlanAction } from '../../services/dailyPlan';
import { getLatestBodyMeasurements } from '../../services/bodyMeasurements';
import { fetchHealthOperatingReview } from '../../services/healthOperatingReview';
import { useAuth } from '../../hooks/useAuth';
import type { RevaStatus } from '../../constants/revaTheme';

export interface RevaLabRow { id: string; name: string; sub: string; value: string; unit: string; status: RevaStatus }
export interface RevaPlanItem { id: string; icon: string; title: string; sub: string }
export interface RevaData {
  loading: boolean;
  readiness: number | null;
  readinessNote: string;
  today: { rhr: number | null; sleepMin: number | null; hrv: number | null; steps: number | null; activeCal: number | null; bp: string | null };
  rhrSeries: number[];
  abnormalLabs: RevaLabRow[];
  abnormalCount: number;
  examDate: string | null;
  dayInWindow: number | null;
  plan: RevaPlanItem[];
  profileName: string;
  profileMeta: string;
  hasGarmin: boolean;
}

const DOMAIN_ICON: Record<string, string> = {
  measurement: 'gauge', nutrition: 'utensils', movement: 'footprints',
  sleep: 'moon', intervention: 'pill', doctor: 'calendar-check',
};

function abnormalToStatus(flag: string | null | undefined): RevaStatus | null {
  if (flag === 'high') return 'risk';
  if (flag === 'low' || flag === 'abnormal') return 'caution';
  return null; // normal / null → not an abnormal item
}

function abnormalLabel(flag: string | null | undefined): string {
  if (flag === 'high') return '偏高 · 注意';
  if (flag === 'low') return '偏低 · 注意';
  return '异常 · 注意';
}

function extractBP(stats: any): string | null {
  if (!stats || typeof stats !== 'object') return null;
  const sys = stats.latest_systolic ?? stats.latest?.systolic ?? stats.systolic;
  const dia = stats.latest_diastolic ?? stats.latest?.diastolic ?? stats.diastolic;
  return sys != null && dia != null ? `${sys}/${dia}` : null;
}

export function useRevaData(): RevaData {
  const dash = useDashboardData();
  const latest = useLatestGarmin(dash.data);

  const examsQ = useQuery({ queryKey: ['reva', 'exams'], queryFn: () => listMedicalExams(50), staleTime: 5 * 60 * 1000 });
  const planQ = useQuery({ queryKey: ['reva', 'dailyPlan'], queryFn: getDailyOperatingPlan, staleTime: 60 * 1000 });
  const review90Q = useQuery({ queryKey: ['reva', 'review90'], queryFn: () => fetchHealthOperatingReview(90), staleTime: 10 * 60 * 1000 });
  const { user } = useAuth();

  const loading = dash.isLoading || examsQ.isLoading || planQ.isLoading;

  // RHR latest + 7-day series
  const garminDaily = dash.data?.garminDaily ?? [];
  const rhrSeries = garminDaily
    .map(r => r.resting_heart_rate)
    .filter((v): v is number => typeof v === 'number')
    .slice(-7);

  // Readiness: no standalone source — proxy from body battery, then sleep score.
  const readiness = latest?.body_battery_current ?? latest?.sleep_score ?? null;
  const readinessNote = latest
    ? [
        latest.resting_heart_rate != null ? `静息心率 ${latest.resting_heart_rate} bpm` : null,
        latest.total_sleep_duration != null ? `睡眠 ${Math.round(latest.total_sleep_duration / 60)}h${latest.total_sleep_duration % 60}m` : null,
      ].filter(Boolean).join(' · ') || '已接入手环数据'
    : '连接手环后，复元用真实数据校准就绪度';

  // Abnormal labs from the most recent exam.
  const exams: MedicalExam[] = examsQ.data ?? [];
  const latestExam = exams[0];
  const abnormalLabs: RevaLabRow[] = (latestExam?.items ?? [])
    .map(it => {
      const status = abnormalToStatus(it.is_abnormal);
      if (!status) return null;
      return {
        id: String(it.id),
        name: it.item_name,
        sub: abnormalLabel(it.is_abnormal),
        value: it.value_text ?? (it.value != null ? String(it.value) : '—'),
        unit: it.unit ?? '',
        status,
      } as RevaLabRow;
    })
    .filter((x): x is RevaLabRow => x !== null);

  // Day in 90-day window from review start_date.
  let dayInWindow: number | null = null;
  const start = review90Q.data?.start_date;
  if (start) {
    const d = Math.floor((Date.now() - new Date(start).getTime()) / 86400000) + 1;
    dayInWindow = Math.max(1, Math.min(90, d));
  }

  // Today's plan actions.
  const actions: DailyPlanAction[] = planQ.data?.actions ?? [];
  const plan: RevaPlanItem[] = actions.slice(0, 5).map((a, i) => ({
    id: a.action_key ?? `plan-${i}`,
    icon: DOMAIN_ICON[a.domain] ?? 'sparkles',
    title: a.title,
    sub: a.why ?? a.when ?? '',
  }));

  // Profile.
  const profile: any = dash.data?.profile ?? {};
  const profileName = user?.nickname || profile?.nickname || user?.username || '我';
  const metaBits = [profile?.gender, profile?.age != null ? `${profile.age} 岁` : null, '心代谢管理中'].filter(Boolean);
  const profileMeta = metaBits.join(' · ');

  return {
    loading,
    readiness,
    readinessNote,
    today: {
      rhr: latest?.resting_heart_rate ?? null,
      sleepMin: latest?.total_sleep_duration ?? null,
      hrv: latest?.hrv ?? null,
      steps: latest?.steps ?? null,
      activeCal: latest?.active_calories ?? null,
      bp: extractBP(dash.data?.bloodPressureStats),
    },
    rhrSeries,
    abnormalLabs,
    abnormalCount: abnormalLabs.length,
    examDate: latestExam?.exam_date ?? null,
    dayInWindow,
    plan,
    profileName,
    profileMeta,
    hasGarmin: !!latest,
  };
}
