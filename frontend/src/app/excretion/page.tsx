'use client';

import { useState, useEffect, useCallback } from 'react';
import ProtectedRoute from '@/components/ProtectedRoute';
import { excretionApi, ExcretionRecord, ExcretionStats } from '@/services/api';
import { format } from 'date-fns';

const BRISTOL_SCALE = [
  { value: 1, label: '硬球状', desc: '分离的硬块', color: 'bg-red-100 text-red-700' },
  { value: 2, label: '腊肠硬便', desc: '腊肠状但有硬块', color: 'bg-orange-100 text-orange-700' },
  { value: 3, label: '有裂纹', desc: '腊肠状表面有裂纹', color: 'bg-yellow-100 text-yellow-700' },
  { value: 4, label: '光滑软便', desc: '光滑柔软（正常）', color: 'bg-green-100 text-green-700' },
  { value: 5, label: '软块状', desc: '柔软块状', color: 'bg-blue-100 text-blue-700' },
  { value: 6, label: '糊状', desc: '蓬松糊状', color: 'bg-purple-100 text-purple-700' },
  { value: 7, label: '水样便', desc: '完全液状', color: 'bg-red-100 text-red-700' },
];

const STOOL_COLORS = [
  { value: 'brown', label: '棕色', dot: 'bg-amber-700' },
  { value: 'yellow', label: '黄色', dot: 'bg-yellow-500' },
  { value: 'green', label: '绿色', dot: 'bg-green-600' },
  { value: 'black', label: '黑色', dot: 'bg-gray-900' },
  { value: 'red', label: '红色', dot: 'bg-red-600' },
  { value: 'pale', label: '白色/淡色', dot: 'bg-gray-200' },
];

const URINE_COLORS = [
  { value: 'transparent', label: '透明', dot: 'bg-gray-100 border border-gray-300' },
  { value: 'light_yellow', label: '浅黄', dot: 'bg-yellow-200' },
  { value: 'yellow', label: '黄色', dot: 'bg-yellow-400' },
  { value: 'dark_yellow', label: '深黄', dot: 'bg-yellow-600' },
  { value: 'amber', label: '琥珀色', dot: 'bg-amber-600' },
  { value: 'brown', label: '褐色', dot: 'bg-amber-800' },
  { value: 'red', label: '红色', dot: 'bg-red-500' },
];

const AMOUNTS = [
  { value: 'small', label: '少' },
  { value: 'medium', label: '中' },
  { value: 'large', label: '多' },
];

interface FormData {
  type: 'bowel' | 'urine';
  record_date: string;
  record_time: string;
  stool_type: number | null;
  color: string;
  amount: string;
  duration_minutes: number | null;
  blood_present: boolean;
  urine_color: string;
  urine_amount: string;
  urgency: number | null;
  pain_level: number | null;
  notes: string;
}

function ExcretionContent() {
  const [records, setRecords] = useState<ExcretionRecord[]>([]);
  const [stats, setStats] = useState<ExcretionStats | null>(null);
  const [tab, setTab] = useState<'list' | 'stats'>('list');
  const [showForm, setShowForm] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);

  const now = new Date();
  const [form, setForm] = useState<FormData>({
    type: 'bowel',
    record_date: format(now, 'yyyy-MM-dd'),
    record_time: format(now, 'HH:mm'),
    stool_type: null,
    color: '',
    amount: '',
    duration_minutes: null,
    blood_present: false,
    urine_color: '',
    urine_amount: '',
    urgency: null,
    pain_level: null,
    notes: '',
  });

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [recRes, statsRes] = await Promise.allSettled([
        excretionApi.getMyRecords({ limit: 50 }),
        excretionApi.getStats(7),
      ]);
      if (recRes.status === 'fulfilled') setRecords(recRes.value.data);
      if (statsRes.status === 'fulfilled') setStats(statsRes.value.data);
    } catch { /* ignore */ }
    setLoading(false);
  }, []);

  useEffect(() => { void loadData(); }, [loadData]);

  const resetForm = () => {
    const n = new Date();
    setForm({
      type: 'bowel', record_date: format(n, 'yyyy-MM-dd'), record_time: format(n, 'HH:mm'),
      stool_type: null, color: '', amount: '', duration_minutes: null, blood_present: false,
      urine_color: '', urine_amount: '', urgency: null, pain_level: null, notes: '',
    });
    setEditingId(null);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const payload: any = {
        record_date: form.record_date,
        record_time: form.record_time + ':00',
        type: form.type,
        urgency: form.urgency,
        pain_level: form.pain_level,
        notes: form.notes || null,
      };
      if (form.type === 'bowel') {
        payload.stool_type = form.stool_type;
        payload.color = form.color || null;
        payload.amount = form.amount || null;
        payload.duration_minutes = form.duration_minutes;
        payload.blood_present = form.blood_present;
      } else {
        payload.urine_color = form.urine_color || null;
        payload.urine_amount = form.urine_amount || null;
      }

      if (editingId) {
        await excretionApi.updateRecord(editingId, payload);
      } else {
        await excretionApi.createRecord(payload);
      }
      setShowForm(false);
      resetForm();
      await loadData();
    } catch { /* ignore */ }
    setSaving(false);
  };

  const handleDelete = async (id: number) => {
    if (!confirm('确定删除这条记录？')) return;
    try {
      await excretionApi.deleteRecord(id);
      await loadData();
    } catch { /* ignore */ }
  };

  const openEdit = (r: ExcretionRecord) => {
    setForm({
      type: r.type,
      record_date: r.record_date,
      record_time: r.record_time ? r.record_time.slice(0, 5) : format(new Date(), 'HH:mm'),
      stool_type: r.stool_type,
      color: r.color || '',
      amount: r.amount || '',
      duration_minutes: r.duration_minutes,
      blood_present: r.blood_present || false,
      urine_color: r.urine_color || '',
      urine_amount: r.urine_amount || '',
      urgency: r.urgency,
      pain_level: r.pain_level,
      notes: r.notes || '',
    });
    setEditingId(r.id);
    setShowForm(true);
  };

  const bristolInfo = (v: number | null) => BRISTOL_SCALE.find(b => b.value === v);
  const todayBowel = records.filter(r => r.record_date === format(new Date(), 'yyyy-MM-dd') && r.type === 'bowel').length;
  const todayUrine = records.filter(r => r.record_date === format(new Date(), 'yyyy-MM-dd') && r.type === 'urine').length;

  return (
    <main className="min-h-screen pt-4 pb-8 px-4 sm:px-8">
      <div className="max-w-3xl mx-auto">
        {/* Header */}
        <div className="flex justify-between items-center mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">排泄记录</h1>
            <p className="text-sm text-gray-500 mt-1">今日: 大便{todayBowel}次 / 小便{todayUrine}次</p>
          </div>
          <button onClick={() => { resetForm(); setShowForm(true); }}
            className="bg-amber-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-amber-700">
            + 记录
          </button>
        </div>

        {/* Tabs */}
        <div className="flex gap-2 mb-4">
          {(['list', 'stats'] as const).map(t => (
            <button key={t} onClick={() => setTab(t)}
              className={`px-4 py-2 rounded-lg text-sm font-medium ${tab === t ? 'bg-amber-100 text-amber-800' : 'bg-gray-100 text-gray-600'}`}>
              {t === 'list' ? '记录列表' : '统计分析'}
            </button>
          ))}
        </div>

        {loading ? (
          <div className="text-center py-12 text-gray-400">加载中...</div>
        ) : tab === 'list' ? (
          <div className="space-y-3">
            {records.length === 0 && <div className="text-center py-12 text-gray-400">暂无记录</div>}
            {records.map(r => {
              const bristol = bristolInfo(r.stool_type);
              return (
                <div key={r.id} className="bg-white rounded-xl p-4 shadow-sm border border-gray-100">
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-2">
                      <span className="text-2xl">{r.type === 'bowel' ? '💩' : '🚿'}</span>
                      <div>
                        <div className="font-medium text-gray-800">
                          {r.type === 'bowel' ? '大便' : '小便'}
                          {r.record_time && <span className="text-gray-400 text-sm ml-2">{r.record_time.slice(0, 5)}</span>}
                        </div>
                        <div className="text-xs text-gray-400">{r.record_date}</div>
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <button onClick={() => openEdit(r)} className="text-xs text-blue-500 hover:text-blue-700">编辑</button>
                      <button onClick={() => void handleDelete(r.id)} className="text-xs text-red-400 hover:text-red-600">删除</button>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2 mt-2">
                    {r.type === 'bowel' && bristol && (
                      <span className={`text-xs px-2 py-0.5 rounded-full ${bristol.color}`}>Bristol {bristol.value}: {bristol.label}</span>
                    )}
                    {r.type === 'bowel' && r.color && (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-600">
                        {STOOL_COLORS.find(c => c.value === r.color)?.label || r.color}
                      </span>
                    )}
                    {r.type === 'urine' && r.urine_color && (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-600">
                        {URINE_COLORS.find(c => c.value === r.urine_color)?.label || r.urine_color}
                      </span>
                    )}
                    {(r.amount || r.urine_amount) && (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-600">
                        量: {AMOUNTS.find(a => a.value === (r.amount || r.urine_amount))?.label}
                      </span>
                    )}
                    {r.blood_present && <span className="text-xs px-2 py-0.5 rounded-full bg-red-100 text-red-600">有血</span>}
                    {(r.pain_level || 0) > 0 && <span className="text-xs px-2 py-0.5 rounded-full bg-orange-100 text-orange-600">疼痛 {r.pain_level}/5</span>}
                  </div>
                  {r.notes && <p className="text-xs text-gray-500 mt-2">{r.notes}</p>}
                </div>
              );
            })}
          </div>
        ) : (
          /* Stats */
          stats && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="bg-white rounded-xl p-4 text-center shadow-sm">
                  <div className="text-2xl font-bold text-amber-600">{stats.avg_bowel_per_day ?? '-'}</div>
                  <div className="text-xs text-gray-500 mt-1">日均大便次数</div>
                </div>
                <div className="bg-white rounded-xl p-4 text-center shadow-sm">
                  <div className="text-2xl font-bold text-blue-600">{stats.avg_urine_per_day ?? '-'}</div>
                  <div className="text-xs text-gray-500 mt-1">日均小便次数</div>
                </div>
                <div className="bg-white rounded-xl p-4 text-center shadow-sm">
                  <div className="text-2xl font-bold text-green-600">{stats.avg_stool_type ?? '-'}</div>
                  <div className="text-xs text-gray-500 mt-1">平均Bristol</div>
                </div>
                <div className="bg-white rounded-xl p-4 text-center shadow-sm">
                  <div className={`text-2xl font-bold ${stats.blood_count > 0 ? 'text-red-600' : 'text-gray-400'}`}>{stats.blood_count}</div>
                  <div className="text-xs text-gray-500 mt-1">便血次数</div>
                </div>
              </div>

              {/* Bristol distribution */}
              {Object.keys(stats.stool_type_distribution).length > 0 && (
                <div className="bg-white rounded-xl p-4 shadow-sm">
                  <h3 className="text-sm font-medium text-gray-700 mb-3">Bristol 分布</h3>
                  <div className="space-y-2">
                    {BRISTOL_SCALE.map(b => {
                      const count = stats.stool_type_distribution[b.value] || 0;
                      const pct = stats.bowel_count > 0 ? (count / stats.bowel_count * 100) : 0;
                      return (
                        <div key={b.value} className="flex items-center gap-2">
                          <span className="text-xs w-16 text-gray-500">{b.value}. {b.label}</span>
                          <div className="flex-1 h-4 bg-gray-100 rounded-full overflow-hidden">
                            <div className={`h-full rounded-full ${b.value === 4 ? 'bg-green-400' : b.value <= 2 || b.value >= 6 ? 'bg-red-400' : 'bg-yellow-400'}`}
                              style={{ width: `${pct}%` }} />
                          </div>
                          <span className="text-xs text-gray-400 w-8">{count}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Daily summary */}
              {stats.daily_summary.length > 0 && (
                <div className="bg-white rounded-xl p-4 shadow-sm">
                  <h3 className="text-sm font-medium text-gray-700 mb-3">每日记录</h3>
                  <div className="space-y-2">
                    {stats.daily_summary.map(d => (
                      <div key={d.date} className="flex items-center justify-between text-sm">
                        <span className="text-gray-500">{d.date}</span>
                        <div className="flex gap-3">
                          <span>💩 {d.bowel_count}</span>
                          <span>🚿 {d.urine_count}</span>
                          {d.has_blood && <span className="text-red-500">🩸</span>}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )
        )}

        {/* Form Modal */}
        {showForm && (
          <div className="fixed inset-0 bg-black/50 z-50 flex items-end sm:items-center justify-center">
            <div className="bg-white rounded-t-2xl sm:rounded-2xl w-full sm:max-w-lg max-h-[85vh] overflow-y-auto p-6">
              <div className="flex justify-between items-center mb-4">
                <h3 className="text-lg font-semibold">{editingId ? '编辑记录' : '新增记录'}</h3>
                <button onClick={() => { setShowForm(false); resetForm(); }} className="text-gray-400 text-xl">X</button>
              </div>

              {/* Type selector */}
              <div className="flex gap-2 mb-4">
                <button onClick={() => setForm(f => ({ ...f, type: 'bowel' }))}
                  className={`flex-1 py-3 rounded-xl text-center font-medium ${form.type === 'bowel' ? 'bg-amber-100 text-amber-800 ring-2 ring-amber-300' : 'bg-gray-100 text-gray-500'}`}>
                  💩 大便
                </button>
                <button onClick={() => setForm(f => ({ ...f, type: 'urine' }))}
                  className={`flex-1 py-3 rounded-xl text-center font-medium ${form.type === 'urine' ? 'bg-blue-100 text-blue-800 ring-2 ring-blue-300' : 'bg-gray-100 text-gray-500'}`}>
                  🚿 小便
                </button>
              </div>

              {/* Date & Time */}
              <div className="grid grid-cols-2 gap-3 mb-4">
                <div>
                  <label className="text-xs text-gray-500 block mb-1">日期</label>
                  <input type="date" value={form.record_date} onChange={e => setForm(f => ({ ...f, record_date: e.target.value }))}
                    className="w-full px-3 py-2 border rounded-lg text-sm" />
                </div>
                <div>
                  <label className="text-xs text-gray-500 block mb-1">时间</label>
                  <input type="time" value={form.record_time} onChange={e => setForm(f => ({ ...f, record_time: e.target.value }))}
                    className="w-full px-3 py-2 border rounded-lg text-sm" />
                </div>
              </div>

              {form.type === 'bowel' ? (
                <>
                  {/* Bristol Scale */}
                  <div className="mb-4">
                    <label className="text-xs text-gray-500 block mb-2">Bristol 量表 (形状)</label>
                    <div className="grid grid-cols-4 sm:grid-cols-7 gap-2">
                      {BRISTOL_SCALE.map(b => (
                        <button key={b.value} onClick={() => setForm(f => ({ ...f, stool_type: b.value }))}
                          className={`p-2 rounded-lg text-center text-xs ${form.stool_type === b.value ? `${b.color} ring-2 ring-offset-1` : 'bg-gray-50 text-gray-500'}`}>
                          <div className="font-bold">{b.value}</div>
                          <div className="text-[10px] leading-tight">{b.label}</div>
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Color */}
                  <div className="mb-4">
                    <label className="text-xs text-gray-500 block mb-2">颜色</label>
                    <div className="flex flex-wrap gap-2">
                      {STOOL_COLORS.map(c => (
                        <button key={c.value} onClick={() => setForm(f => ({ ...f, color: c.value }))}
                          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs ${form.color === c.value ? 'ring-2 ring-amber-400 bg-amber-50' : 'bg-gray-50'}`}>
                          <span className={`w-3 h-3 rounded-full ${c.dot}`} />
                          {c.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Amount */}
                  <div className="mb-4">
                    <label className="text-xs text-gray-500 block mb-2">量</label>
                    <div className="flex gap-2">
                      {AMOUNTS.map(a => (
                        <button key={a.value} onClick={() => setForm(f => ({ ...f, amount: a.value }))}
                          className={`flex-1 py-2 rounded-lg text-sm font-medium ${form.amount === a.value ? 'bg-amber-100 text-amber-800' : 'bg-gray-100 text-gray-500'}`}>
                          {a.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Duration */}
                  <div className="mb-4">
                    <label className="text-xs text-gray-500 block mb-1">用时（分钟）</label>
                    <input type="number" min="0" max="60" value={form.duration_minutes ?? ''} placeholder="可选"
                      onChange={e => setForm(f => ({ ...f, duration_minutes: e.target.value ? Number(e.target.value) : null }))}
                      className="w-full px-3 py-2 border rounded-lg text-sm" />
                  </div>

                  {/* Blood */}
                  <label className="flex items-center gap-2 mb-4 cursor-pointer">
                    <input type="checkbox" checked={form.blood_present} onChange={e => setForm(f => ({ ...f, blood_present: e.target.checked }))}
                      className="w-4 h-4 text-red-500 rounded" />
                    <span className="text-sm text-gray-700">有血迹</span>
                  </label>
                </>
              ) : (
                <>
                  {/* Urine Color */}
                  <div className="mb-4">
                    <label className="text-xs text-gray-500 block mb-2">尿液颜色</label>
                    <div className="flex flex-wrap gap-2">
                      {URINE_COLORS.map(c => (
                        <button key={c.value} onClick={() => setForm(f => ({ ...f, urine_color: c.value }))}
                          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs ${form.urine_color === c.value ? 'ring-2 ring-blue-400 bg-blue-50' : 'bg-gray-50'}`}>
                          <span className={`w-3 h-3 rounded-full ${c.dot}`} />
                          {c.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Urine Amount */}
                  <div className="mb-4">
                    <label className="text-xs text-gray-500 block mb-2">尿量</label>
                    <div className="flex gap-2">
                      {AMOUNTS.map(a => (
                        <button key={a.value} onClick={() => setForm(f => ({ ...f, urine_amount: a.value }))}
                          className={`flex-1 py-2 rounded-lg text-sm font-medium ${form.urine_amount === a.value ? 'bg-blue-100 text-blue-800' : 'bg-gray-100 text-gray-500'}`}>
                          {a.label}
                        </button>
                      ))}
                    </div>
                  </div>
                </>
              )}

              {/* Shared fields: Urgency & Pain */}
              <div className="grid grid-cols-2 gap-3 mb-4">
                <div>
                  <label className="text-xs text-gray-500 block mb-1">紧迫感 (1-5)</label>
                  <div className="flex gap-1">
                    {[1, 2, 3, 4, 5].map(v => (
                      <button key={v} onClick={() => setForm(f => ({ ...f, urgency: v }))}
                        className={`flex-1 py-1.5 rounded text-xs font-medium ${form.urgency === v ? 'bg-orange-200 text-orange-800' : 'bg-gray-100 text-gray-400'}`}>
                        {v}
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <label className="text-xs text-gray-500 block mb-1">疼痛 (0-5)</label>
                  <div className="flex gap-1">
                    {[0, 1, 2, 3, 4, 5].map(v => (
                      <button key={v} onClick={() => setForm(f => ({ ...f, pain_level: v }))}
                        className={`flex-1 py-1.5 rounded text-xs font-medium ${form.pain_level === v ? 'bg-red-200 text-red-800' : 'bg-gray-100 text-gray-400'}`}>
                        {v}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* Notes */}
              <div className="mb-6">
                <label className="text-xs text-gray-500 block mb-1">备注</label>
                <textarea value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
                  placeholder="可选备注..." rows={2} className="w-full px-3 py-2 border rounded-lg text-sm resize-none" />
              </div>

              <button onClick={() => void handleSave()} disabled={saving}
                className="w-full py-3 rounded-xl bg-amber-600 text-white font-medium disabled:opacity-50">
                {saving ? '保存中...' : '保存'}
              </button>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}

export default function ExcretionPage() {
  return <ProtectedRoute><ExcretionContent /></ProtectedRoute>;
}
