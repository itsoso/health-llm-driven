'use client';
import { useState } from 'react';
import { supplementApi } from '@/services/api/records';

const timingLabels: Record<string, string> = { morning: '早晨', noon: '中午', evening: '晚上', bedtime: '睡前' };
const SUPP_PAGE_SIZE = 6;

interface SupplementCheckinProps {
  supplementStatus: any[];
  onStatusChange: (fn: (prev: any[]) => any[]) => void;
}

export default function SupplementCheckin({ supplementStatus, onStatusChange }: SupplementCheckinProps) {
  const [expanded, setExpanded] = useState(false);

  // Dedupe
  const seen = new Set<string>();
  const deduped = supplementStatus.filter((s: any) => {
    const name = s.supplement?.name || s.supplement_name || s.name;
    const timing = s.supplement?.timing || s.timing || 'morning';
    const key = `${name}_${timing}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });

  const checked = deduped.filter((s: any) => s.record?.taken || s.is_taken || s.checked).length;
  const total = deduped.length;

  if (total === 0) return null;

  // Group by timing
  const grouped: Record<string, any[]> = {};
  for (const s of deduped) {
    const timing = s.supplement?.timing || s.timing || 'morning';
    if (!grouped[timing]) grouped[timing] = [];
    grouped[timing].push(s);
  }
  for (const key of Object.keys(grouped)) {
    grouped[key].sort((a: any, b: any) => {
      const at = a.record?.taken || a.is_taken || a.checked ? 1 : 0;
      const bt = b.record?.taken || b.is_taken || b.checked ? 1 : 0;
      return bt - at;
    });
  }

  const flat = ['morning', 'noon', 'evening', 'bedtime'].flatMap(t =>
    (grouped[t] || []).map((s: any) => ({ ...s, _timing: t }))
  );
  const visible = expanded ? flat : flat.slice(0, SUPP_PAGE_SIZE);
  const hasMore = flat.length > SUPP_PAGE_SIZE;

  const today = new Date().toISOString().slice(0, 10);
  const toggleSupp = async (suppId: number, currentTaken: boolean) => {
    const newTaken = !currentTaken;
    onStatusChange(prev => prev.map((s: any) => {
      const sid = s.supplement?.id || s.supplement_id || s.id;
      if (sid === suppId) return { ...s, record: { ...(s.record || {}), taken: newTaken }, is_taken: newTaken, checked: newTaken };
      return s;
    }));
    try {
      await supplementApi.batchCheckin({ record_date: today, checkins: [{ supplement_id: suppId, taken: newTaken }] });
    } catch (e) {
      console.error('补剂打卡失败', e);
      onStatusChange(prev => prev.map((s: any) => {
        const sid = s.supplement?.id || s.supplement_id || s.id;
        if (sid === suppId) return { ...s, record: { ...(s.record || {}), taken: currentTaken }, is_taken: currentTaken, checked: currentTaken };
        return s;
      }));
    }
  };

  let lastTiming = '';

  return (
    <div className="rounded-2xl p-4" style={{ background: 'linear-gradient(135deg, #fff5f7 0%, #ffffff 100%)', boxShadow: '0 1px 3px rgba(255,100,130,0.08)' }}>
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold" style={{ color: '#1C1C1E' }}>💊 补剂打卡</span>
        </div>
        <span className="text-[11px]" style={{ color: '#8E8E93' }}>{checked}/{total}</span>
      </div>
      {visible.map((s: any, i: number) => {
        const taken = s.record?.taken || s.is_taken || s.checked;
        const name = s.supplement?.name || s.supplement_name || s.name;
        const dosage = s.supplement?.dosage || s.dosage || s.dose;
        const suppId = s.supplement?.id || s.supplement_id || s.id;
        const showHeader = s._timing !== lastTiming;
        lastTiming = s._timing;
        return (
          <div key={i}>
            {showHeader && <p className="text-[10px] font-medium mt-2 mb-0.5 first:mt-0" style={{ color: '#8E8E93' }}>{timingLabels[s._timing]}</p>}
            <div className="flex items-center gap-2 py-1 cursor-pointer group" onClick={() => toggleSupp(suppId, !!taken)}>
              <div className="w-4.5 h-4.5 rounded flex items-center justify-center shrink-0 transition-all" style={{ width: 18, height: 18, ...(taken ? { background: '#FF6482' } : { border: '2px solid #AEAEB2' }) }}>
                {taken && <svg className="w-2.5 h-2.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" /></svg>}
              </div>
              <span className={`flex-1 text-sm ${taken ? 'line-through' : ''}`} style={{ color: taken ? '#AEAEB2' : '#1C1C1E' }}>{name}</span>
              {dosage && <span className="text-[10px]" style={{ color: '#AEAEB2' }}>{dosage}</span>}
            </div>
          </div>
        );
      })}
      {hasMore && (
        <button onClick={() => setExpanded(!expanded)} className="w-full mt-1.5 py-1 text-xs" style={{ color: '#007AFF' }}>
          {expanded ? '收起' : `展开全部 (${flat.length})`}
        </button>
      )}
    </div>
  );
}
