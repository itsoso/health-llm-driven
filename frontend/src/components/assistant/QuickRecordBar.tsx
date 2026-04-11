'use client';
import { useState } from 'react';
import { api } from '@/services/api';

interface QuickRecordBarProps {
  rhinitisToday: any;
  onWaterRecord: (amount: number) => void;
  onRhinitisUpdate: (fn: (prev: any) => any) => void;
}

export default function QuickRecordBar({ rhinitisToday, onWaterRecord, onRhinitisUpdate }: QuickRecordBarProps) {
  const [quickToast, setQuickToast] = useState<string | null>(null);
  const today = new Date().toISOString().slice(0, 10);

  const showToast = (msg: string) => { setQuickToast(msg); setTimeout(() => setQuickToast(null), 1500); };

  const quickActions = [
    { icon: '💧', label: '300ml', action: async () => {
      await api.post('/water/records', { record_date: today, amount: 300, drink_type: '水', user_id: 0 });
      onWaterRecord(300);
      showToast('已记录喝水 300ml');
    }},
    { icon: '💧', label: '500ml', action: async () => {
      await api.post('/water/records', { record_date: today, amount: 500, drink_type: '水', user_id: 0 });
      onWaterRecord(500);
      showToast('已记录喝水 500ml');
    }},
    { icon: '👃', label: '洗鼻+1', action: async () => {
      const cur = rhinitisToday?.nasal_wash_count || 0;
      await api.post('/checkin/', { checkin_date: today, nasal_wash_count: cur + 1 });
      onRhinitisUpdate((prev: any) => ({ ...prev, nasal_wash_count: cur + 1 }));
      showToast(`已记录洗鼻 ${cur + 1} 次`);
    }},
    { icon: '🤧', label: '喷嚏+1', action: async () => {
      const cur = rhinitisToday?.sneeze_count || 0;
      await api.post('/checkin/', { checkin_date: today, sneeze_count: cur + 1 });
      onRhinitisUpdate((prev: any) => ({ ...prev, sneeze_count: cur + 1 }));
      showToast(`已记录喷嚏 ${cur + 1} 次`);
    }},
    { icon: '🌿', label: '莫米松+1', action: async () => {
      const medsRes = await api.get('/medication/medications/me');
      const meds = medsRes.data || [];
      let med = meds.find((m: any) => m.name === '糠酸莫米松鼻喷雾剂' || m.name === '莫米松' || m.name === 'Mometasone Furoate Nasal Spray');
      if (!med) {
        const createRes = await api.post('/medication/medications', {
          name: '糠酸莫米松鼻喷雾剂', dosage: '每侧2喷', frequency: '每日1-2次',
          times_per_day: 1, category: 'prescription', purpose: '过敏性鼻炎',
          notes: '内舒拿；每侧鼻孔各 2 喷'
        });
        med = createRes.data;
      }
      const now = new Date();
      const timeStr = `${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}`;
      await api.post('/medication/logs', {
        medication_id: med.id, taken_time: timeStr, status: 'taken',
        actual_dosage: '每侧2喷', notes: `${today} ${timeStr} 鼻喷`
      });
      showToast(`已记录莫米松鼻喷 (${timeStr})`);
    }},
    { icon: '💉', label: '替尔泊肽', action: async () => {
      const medsRes = await api.get('/medication/medications/me');
      const meds = medsRes.data || [];
      let med = meds.find((m: any) => m.name === '替尔泊肽' || m.name === 'Tirzepatide');
      if (!med) {
        const createRes = await api.post('/medication/medications', {
          name: '替尔泊肽', dosage: '2.4ml', frequency: '每周1次',
          times_per_day: 1, category: 'prescription', purpose: '体重管理/GLP-1',
          notes: '皮下注射，每周固定时间'
        });
        med = createRes.data;
      }
      const now = new Date();
      const timeStr = `${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}`;
      await api.post('/medication/logs', {
        medication_id: med.id, taken_time: timeStr, status: 'taken',
        actual_dosage: '2.4ml', notes: `${today} ${timeStr} 注射`
      });
      showToast(`已记录注射替尔泊肽 2.4ml (${timeStr})`);
    }},
  ];

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
}
