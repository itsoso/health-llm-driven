'use client';
import { useRouter } from 'next/navigation';
import { api } from '@/services/api';

interface AlertsBannerProps {
  waterToday: { total_ml: number; goal_ml: number; count: number };
  todayGarmin: any;
  onWaterRecord: (amount: number) => void;
  onAskAI: (text: string) => void;
}

export default function AlertsBanner({ waterToday, todayGarmin, onWaterRecord, onAskAI }: AlertsBannerProps) {
  const router = useRouter();
  const hour = new Date().getHours();
  const today = new Date().toISOString().slice(0, 10);

  const quickDrinkWater = async (amount: number) => {
    try {
      await api.post('/water/records', { record_date: today, amount, drink_type: '水', user_id: 0 });
      onWaterRecord(amount);
    } catch (e) { console.error('记录饮水失败', e); }
  };

  const alerts: { icon: string; text: string; actionLabel: string; onAction: () => void; color: string; bg: string }[] = [];

  if (hour >= 7) {
    const waterExpected = hour >= 18 ? 1500 : hour >= 12 ? 800 : 300;
    if (waterToday.total_ml < waterExpected * 0.3) {
      alerts.push({ icon: '💧', text: `已${hour}点，饮水仅 ${waterToday.total_ml}ml，需要补充`, actionLabel: '+500ml', onAction: () => quickDrinkWater(500), color: '#ef4444', bg: '#fef2f2' });
    } else if (waterToday.total_ml < waterExpected * 0.6) {
      alerts.push({ icon: '💧', text: `今日饮水 ${waterToday.total_ml}ml，建议多喝水`, actionLabel: '+300ml', onAction: () => quickDrinkWater(300), color: '#f59e0b', bg: '#fffbeb' });
    }
  }

  if (todayGarmin?.spo2_avg && todayGarmin.spo2_avg < 90) {
    alerts.push({ icon: '🫁', text: `血氧 ${todayGarmin.spo2_avg}% 低于90%，注意休息`, actionLabel: '查看', onAction: () => router.push('/garmin'), color: '#ef4444', bg: '#fef2f2' });
  }

  if (todayGarmin?.hrv && todayGarmin.hrv < 40) {
    alerts.push({ icon: '💓', text: `HRV ${todayGarmin.hrv}ms 偏低，身体恢复不足`, actionLabel: '分析', onAction: () => onAskAI('分析我最近的HRV趋势，给出恢复建议'), color: '#ef4444', bg: '#fef2f2' });
  }

  if (alerts.length === 0) return null;

  return (
    <div className="space-y-2">
      {alerts.map((a, i) => (
        <div key={i} className="rounded-xl px-4 py-2.5 flex items-center gap-3" style={{ background: a.bg, border: `1px solid ${a.color}20` }}>
          <span className="text-base shrink-0">{a.icon}</span>
          <span className="flex-1 text-sm font-medium" style={{ color: a.color }}>{a.text}</span>
          <button onClick={a.onAction} className="shrink-0 px-3 py-1 rounded-lg text-xs font-semibold text-white active:scale-95" style={{ background: a.color }}>{a.actionLabel}</button>
        </div>
      ))}
    </div>
  );
}
