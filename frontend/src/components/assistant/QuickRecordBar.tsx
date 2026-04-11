'use client';
import { useRef } from 'react';
import { api } from '@/services/api';
import { useToast } from '@/contexts/ToastContext';

interface QuickRecordBarProps {
  rhinitisToday: any;
  onWaterRecord: (amount: number) => void;
  onRhinitisUpdate: (fn: (prev: any) => any) => void;
}

type ActionKey = string;

export default function QuickRecordBar({ rhinitisToday, onWaterRecord, onRhinitisUpdate }: QuickRecordBarProps) {
  const { showToast } = useToast();
  const lockRef = useRef<Set<ActionKey>>(new Set());
  const today = new Date().toISOString().slice(0, 10);

  // --- helpers ------------------------------------------------------------
  const withLock = async (key: ActionKey, fn: () => Promise<void>) => {
    if (lockRef.current.has(key)) return; // 防重入（防双击）
    lockRef.current.add(key);
    try {
      await fn();
    } catch (e: any) {
      console.error(`[QuickRecord] ${key} 失败`, e);
      const msg = e?.response?.data?.detail || e?.message || '操作失败';
      showToast(`${key} 失败：${msg}`, 'error');
    } finally {
      lockRef.current.delete(key);
    }
  };

  const nowHHMM = () => {
    const n = new Date();
    return `${String(n.getHours()).padStart(2, '0')}:${String(n.getMinutes()).padStart(2, '0')}`;
  };

  // 查找或创建药品 — 返回 medication 对象
  const ensureMedication = async (
    aliases: string[],
    create: { name: string; dosage: string; frequency: string; category: string; purpose: string; notes?: string }
  ) => {
    const medsRes = await api.get('/medication/medications/me');
    const meds: any[] = medsRes.data || [];
    const found = meds.find((m) => aliases.includes(m.name));
    if (found) return found;
    const createRes = await api.post('/medication/medications', {
      times_per_day: 1,
      ...create,
    });
    return createRes.data;
  };

  // --- actions ------------------------------------------------------------
  const drinkWater = (amount: number) =>
    withLock(`water-${amount}`, async () => {
      const res = await api.post('/water/records', { record_date: today, amount, drink_type: '水', user_id: 0 });
      const newId = res.data?.id;
      onWaterRecord(amount);
      showToast(`已记录喝水 ${amount}ml`, {
        type: 'success',
        onUndo: async () => {
          if (newId) {
            try {
              await api.delete(`/water/records/${newId}`);
            } catch (e) {
              console.error('撤销失败', e);
            }
          }
          onWaterRecord(-amount);
        },
      });
    });

  const bumpRhinitis = (field: 'nasal_wash_count' | 'sneeze_count', label: string) =>
    withLock(`${field}`, async () => {
      const prevVal = rhinitisToday?.[field] || 0;
      const nextVal = prevVal + 1;
      await api.post('/checkin/', { checkin_date: today, [field]: nextVal });
      onRhinitisUpdate((prev: any) => ({ ...prev, [field]: nextVal }));
      showToast(`已记录${label} ${nextVal} 次`, {
        type: 'success',
        onUndo: async () => {
          // checkin 是 upsert — 回滚等价于写入前值
          try {
            await api.post('/checkin/', { checkin_date: today, [field]: prevVal });
          } catch (e) {
            console.error('撤销失败', e);
          }
          onRhinitisUpdate((prev: any) => ({ ...prev, [field]: prevVal }));
        },
      });
    });

  const logMedication = (
    key: string,
    aliases: string[],
    create: { name: string; dosage: string; frequency: string; category: string; purpose: string; notes?: string },
    actualDosage: string,
    toastLabel: string
  ) =>
    withLock(`med-${key}`, async () => {
      const med = await ensureMedication(aliases, create);
      const timeStr = nowHHMM();
      const res = await api.post('/medication/logs', {
        medication_id: med.id,
        taken_time: timeStr,
        status: 'taken',
        actual_dosage: actualDosage,
        notes: `${today} ${timeStr}`,
      });
      const logId = res.data?.id;
      showToast(`${toastLabel} (${timeStr})`, {
        type: 'success',
        onUndo: async () => {
          if (!logId) return;
          try {
            await api.delete(`/medication/logs/${logId}`);
          } catch (e) {
            console.error('撤销失败', e);
          }
        },
      });
    });

  const quickActions = [
    { icon: '💧', label: '300ml', onClick: () => drinkWater(300) },
    { icon: '💧', label: '500ml', onClick: () => drinkWater(500) },
    { icon: '👃', label: '洗鼻+1', onClick: () => bumpRhinitis('nasal_wash_count', '洗鼻') },
    { icon: '🤧', label: '喷嚏+1', onClick: () => bumpRhinitis('sneeze_count', '喷嚏') },
    {
      icon: '🌿',
      label: '莫米松+1',
      onClick: () =>
        logMedication(
          'mometasone',
          ['糠酸莫米松鼻喷雾剂', '莫米松', 'Mometasone Furoate Nasal Spray'],
          {
            name: '糠酸莫米松鼻喷雾剂',
            dosage: '每侧2喷',
            frequency: '每日1-2次',
            category: 'prescription',
            purpose: '过敏性鼻炎',
            notes: '内舒拿；每侧鼻孔各 2 喷',
          },
          '每侧2喷',
          '已记录莫米松鼻喷'
        ),
    },
    {
      icon: '💊',
      label: '西替利嗪+1',
      onClick: () =>
        logMedication(
          'cetirizine',
          ['盐酸西替利嗪片', '西替利嗪', 'Cetirizine Hydrochloride'],
          {
            name: '盐酸西替利嗪片',
            dosage: '10mg',
            frequency: '每日1次',
            category: 'otc',
            purpose: '过敏性鼻炎/抗组胺',
            notes: '口服抗组胺药，通常睡前服用',
          },
          '10mg',
          '已记录西替利嗪 10mg'
        ),
    },
    {
      icon: '💉',
      label: '替尔泊肽',
      onClick: () =>
        logMedication(
          'tirzepatide',
          ['替尔泊肽', 'Tirzepatide'],
          {
            name: '替尔泊肽',
            dosage: '2.4ml',
            frequency: '每周1次',
            category: 'prescription',
            purpose: '体重管理/GLP-1',
            notes: '皮下注射，每周固定时间',
          },
          '2.4ml',
          '已记录注射替尔泊肽 2.4ml'
        ),
    },
  ];

  return (
    <div className="flex items-center gap-2">
      <span className="text-[10px] font-medium shrink-0" style={{ color: '#8E8E93' }}>
        快速记录
      </span>
      <div className="flex-1 flex gap-1.5 overflow-x-auto">
        {quickActions.map((a, i) => (
          <button
            key={i}
            onClick={a.onClick}
            className="shrink-0 flex items-center gap-1 px-3 py-1.5 rounded-full text-[11px] font-medium transition-all active:scale-95"
            style={{ background: '#F2F2F7', color: '#1C1C1E' }}
          >
            <span className="text-sm">{a.icon}</span>
            <span>{a.label}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
