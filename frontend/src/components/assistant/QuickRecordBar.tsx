'use client';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/services/api';

interface QuickRecordBarProps {
  rhinitisToday: any;
  onWaterRecord: (amount: number) => void;
  onRhinitisUpdate: (fn: (prev: any) => any) => void;
}

export default function QuickRecordBar({ rhinitisToday, onWaterRecord, onRhinitisUpdate }: QuickRecordBarProps) {
  const router = useRouter();
  const [quickToast, setQuickToast] = useState<string | null>(null);
  const [navExpanded, setNavExpanded] = useState(false);
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

  const navItems = [
    { href: '/supplements', icon: '💊', name: '补剂' },
    { href: '/diet', icon: '🍽️', name: '饮食' },
    { href: '/water', icon: '💧', name: '饮水' },
    { href: '/rhinitis', icon: '👃', name: '鼻炎' },
    { href: '/mood', icon: '😊', name: '情绪' },
    { href: '/workout', icon: '🏋️', name: '运动' },
    { href: '/supplement-products', icon: '📦', name: '产品库' },
    { href: '/sleep', icon: '🌙', name: '睡眠' },
    { href: '/weight', icon: '⚖️', name: '体重' },
    { href: '/heart-rate', icon: '❤️', name: '心率' },
    { href: '/blood-pressure', icon: '🩺', name: '血压' },
    { href: '/garmin', icon: '⌚', name: 'Garmin' },
    { href: '/genetic', icon: '🧬', name: '基因' },
    { href: '/massage', icon: '💆', name: '按摩' },
    { href: '/medical-exams', icon: '📋', name: '体检' },
    { href: '/settings', icon: '⚙️', name: '设置' },
  ];

  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-3">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">快速记录</span>
        <div className="flex-1 flex gap-1.5 overflow-x-auto">
          {quickActions.map((a, i) => (
            <button key={i} onClick={async () => { try { await a.action(); } catch (e) { console.error(e); } }}
              className="shrink-0 flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-gray-100 bg-gray-50/80 text-[11px] text-gray-600 hover:bg-emerald-50 hover:border-emerald-300 hover:text-emerald-700 active:scale-95 transition-all">
              <span className="text-sm">{a.icon}</span>
              <span className="font-medium">{a.label}</span>
            </button>
          ))}
        </div>
      </div>
      {quickToast && (
        <div className="mb-2 px-3 py-1.5 rounded-lg bg-emerald-50 border border-emerald-200 text-xs text-emerald-700 font-medium text-center">
          {quickToast}
        </div>
      )}
      <button onClick={() => setNavExpanded(!navExpanded)} className="w-full flex items-center justify-center gap-1 py-1 text-[10px] text-gray-400 hover:text-gray-600 transition">
        <span>{navExpanded ? '收起快捷入口' : '展开快捷入口'}</span>
        <span className={`transition-transform ${navExpanded ? 'rotate-180' : ''}`}>▾</span>
      </button>
      {navExpanded && (
        <div className="grid grid-cols-7 gap-1 mt-1">
          {navItems.map(item => (
            <button key={item.href} onClick={() => router.push(item.href)} className="flex flex-col items-center gap-0.5 py-1.5 rounded-lg hover:bg-gray-50 active:scale-95 transition-all">
              <span className="text-lg">{item.icon}</span>
              <span className="text-[10px] text-gray-500 font-medium">{item.name}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
