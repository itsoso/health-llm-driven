'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import ProtectedRoute from '@/components/ProtectedRoute';
import { familyApi } from '@/services/api/family';

interface ReviewItem {
  id: number;
  item_name: string;
  category: string | null;
  department: string | null;
  hospital: string | null;
  last_check_date: string | null;
  next_due_date: string;
  days_until_due: number;
  status: string;
  priority: string;
  notes: string | null;
  interval_months: number | null;
}

const STATUS_STYLES: Record<string, { bg: string; text: string; icon: string }> = {
  overdue: { bg: 'bg-red-50 border-red-200', text: 'text-red-700', icon: '🔴' },
  pending: { bg: 'bg-white border-gray-200', text: 'text-gray-700', icon: '🟡' },
  completed: { bg: 'bg-green-50 border-green-200', text: 'text-green-700', icon: '✅' },
};

export default function CalendarPage() {
  return <ProtectedRoute><CalendarContent /></ProtectedRoute>;
}

function CalendarContent() {
  const router = useRouter();
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [summary, setSummary] = useState({ total: 0, overdue: 0, upcoming_30_days: 0 });
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [addForm, setAddForm] = useState({ item_name: '', next_due_date: '', department: '', hospital: '', interval_months: '', category: 'blood', notes: '' });

  useEffect(() => { loadCalendar(); }, []);

  const loadCalendar = async () => {
    setLoading(true);
    try {
      const res = await familyApi.getReviewCalendar();
      setItems(res.data.schedules || []);
      setSummary(res.data.summary || { total: 0, overdue: 0, upcoming_30_days: 0 });
    } catch { } finally { setLoading(false); }
  };

  const addReview = async () => {
    if (!addForm.item_name.trim() || !addForm.next_due_date) return;
    try {
      await familyApi.addReview({
        item_name: addForm.item_name,
        next_due_date: addForm.next_due_date,
        department: addForm.department || undefined,
        hospital: addForm.hospital || undefined,
        interval_months: addForm.interval_months ? parseInt(addForm.interval_months) : undefined,
        category: addForm.category || undefined,
        notes: addForm.notes || undefined,
      });
      setShowAdd(false);
      setAddForm({ item_name: '', next_due_date: '', department: '', hospital: '', interval_months: '', category: 'blood', notes: '' });
      await loadCalendar();
    } catch (e: any) {
      alert(e.response?.data?.detail || '添加失败');
    }
  };

  const completeReview = async (id: number) => {
    try {
      const res = await familyApi.completeReview(id);
      alert(res.data.message + (res.data.next_due ? `\n下次复查: ${res.data.next_due}` : ''));
      await loadCalendar();
    } catch (e: any) {
      alert(e.response?.data?.detail || '操作失败');
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="bg-white border-b px-4 py-3 flex items-center gap-3">
        <button onClick={() => router.push('/family')} className="text-gray-500">←</button>
        <h1 className="font-bold text-lg">📅 复查日历</h1>
      </div>

      {/* 汇总卡片 */}
      <div className="flex gap-2 p-4">
        <div className={`flex-1 rounded-xl p-3 text-center ${summary.overdue > 0 ? 'bg-red-50' : 'bg-green-50'}`}>
          <div className="text-2xl font-bold">{summary.overdue}</div>
          <div className="text-xs text-gray-500">已过期</div>
        </div>
        <div className="flex-1 rounded-xl p-3 text-center bg-amber-50">
          <div className="text-2xl font-bold">{summary.upcoming_30_days}</div>
          <div className="text-xs text-gray-500">30天内到期</div>
        </div>
        <div className="flex-1 rounded-xl p-3 text-center bg-blue-50">
          <div className="text-2xl font-bold">{summary.total}</div>
          <div className="text-xs text-gray-500">总计划</div>
        </div>
      </div>

      <div className="px-4 space-y-3">
        <button onClick={() => setShowAdd(true)} className="w-full bg-blue-500 text-white rounded-xl py-3 text-sm font-medium">
          + 添加复查计划
        </button>

        {/* 添加表单 */}
        {showAdd && (
          <div className="bg-white rounded-xl p-4 shadow-sm border space-y-2">
            <input className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="检查项目 *（如：空腹血糖）" value={addForm.item_name} onChange={e => setAddForm({ ...addForm, item_name: e.target.value })} />
            <div className="flex gap-2">
              <div className="flex-1">
                <label className="text-xs text-gray-400">下次复查日期 *</label>
                <input type="date" className="w-full border rounded-lg px-3 py-2 text-sm" value={addForm.next_due_date} onChange={e => setAddForm({ ...addForm, next_due_date: e.target.value })} />
              </div>
              <div className="w-24">
                <label className="text-xs text-gray-400">间隔(月)</label>
                <input type="number" className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="如 6" value={addForm.interval_months} onChange={e => setAddForm({ ...addForm, interval_months: e.target.value })} />
              </div>
            </div>
            <div className="flex gap-2">
              <input className="flex-1 border rounded-lg px-3 py-2 text-sm" placeholder="科室" value={addForm.department} onChange={e => setAddForm({ ...addForm, department: e.target.value })} />
              <input className="flex-1 border rounded-lg px-3 py-2 text-sm" placeholder="医院" value={addForm.hospital} onChange={e => setAddForm({ ...addForm, hospital: e.target.value })} />
            </div>
            <input className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="备注" value={addForm.notes} onChange={e => setAddForm({ ...addForm, notes: e.target.value })} />
            <div className="flex gap-2">
              <button onClick={() => setShowAdd(false)} className="flex-1 border rounded-lg py-2 text-sm">取消</button>
              <button onClick={addReview} className="flex-1 bg-blue-500 text-white rounded-lg py-2 text-sm">添加</button>
            </div>
          </div>
        )}

        {/* 复查列表 */}
        {loading ? (
          <div className="text-center py-8 text-gray-400">加载中...</div>
        ) : items.length === 0 ? (
          <div className="text-center py-12 text-gray-400">
            <div className="text-4xl mb-2">📅</div>
            <p>暂无复查计划</p>
          </div>
        ) : (
          items.map(item => {
            const style = STATUS_STYLES[item.status] || STATUS_STYLES.pending;
            return (
              <div key={item.id} className={`rounded-xl p-4 shadow-sm border ${style.bg}`}>
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className={`font-medium ${style.text}`}>
                      {style.icon} {item.item_name}
                    </h3>
                    <div className="text-xs text-gray-400 mt-1 space-y-0.5">
                      {item.department && <div>🏥 {item.department} {item.hospital && `· ${item.hospital}`}</div>}
                      <div>📅 到期: {item.next_due_date} ({item.days_until_due > 0 ? `${item.days_until_due}天后` : item.days_until_due === 0 ? '今天' : `过期${-item.days_until_due}天`})</div>
                      {item.last_check_date && <div>上次: {item.last_check_date}</div>}
                      {item.interval_months && <div>间隔: {item.interval_months}个月</div>}
                      {item.notes && <div>📝 {item.notes}</div>}
                    </div>
                  </div>
                  {item.status !== 'completed' && (
                    <button
                      onClick={() => completeReview(item.id)}
                      className="text-xs bg-green-500 text-white px-3 py-1.5 rounded-lg whitespace-nowrap"
                    >
                      已完成
                    </button>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
