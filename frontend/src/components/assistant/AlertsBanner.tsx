'use client';
import { useRef } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/services/api/client';
import { useToast } from '@/contexts/ToastContext';
import { getLocalDateStr } from '@/utils/timezone';

interface AlertsBannerProps {
  waterToday: { total_ml: number; goal_ml: number; count: number };
  todayGarmin: any;
  onWaterRecord: (amount: number) => void;
  onAskAI: (text: string) => void;
}

export default function AlertsBanner({ waterToday, todayGarmin, onWaterRecord, onAskAI }: AlertsBannerProps) {
  const router = useRouter();
  const { showToast } = useToast();
  const lockRef = useRef<Set<string>>(new Set());
  const hour = new Date().getHours();
  const today = getLocalDateStr();

  const quickDrinkWater = async (amount: number) => {
    const key = `alert-water-${amount}`;
    if (lockRef.current.has(key)) return;
    lockRef.current.add(key);
    try {
      const res = await api.post('/water/records', { record_date: today, amount, drink_type: '水', user_id: 0 });
      const newId = res.data?.id;
      onWaterRecord(amount);
      showToast(`已记录喝水 ${amount}ml`, {
        type: 'success',
        onUndo: async () => {
          if (newId) {
            try { await api.delete(`/water/records/${newId}`); } catch (e) { console.error('撤销失败', e); }
          }
          onWaterRecord(-amount);
        },
      });
    } catch (e: any) {
      console.error('记录饮水失败', e);
      const msg = e?.response?.data?.detail || e?.message || '操作失败';
      showToast(`记录饮水失败：${msg}`, 'error');
    } finally {
      lockRef.current.delete(key);
    }
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
    alerts.push({ icon: '🫁', text: `血氧 ${todayGarmin.spo2_avg}% 低于90%，注意休息`, actionLabel: '查看', onAction: () => router.push('/settings'), color: '#ef4444', bg: '#fef2f2' });
  }

  if (todayGarmin?.hrv && todayGarmin.hrv < 40) {
    alerts.push({ icon: '💓', text: `HRV ${todayGarmin.hrv}ms 偏低，身体恢复不足`, actionLabel: '分析', onAction: () => onAskAI('分析我最近的HRV趋势，给出恢复建议'), color: '#ef4444', bg: '#fef2f2' });
  }

  if (alerts.length === 0) return null;

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
}
