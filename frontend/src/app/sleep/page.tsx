'use client';

import { useState, useEffect, useCallback } from 'react';
import ProtectedRoute from '@/components/ProtectedRoute';
import { sleepApi, SleepRecordData, SleepStats } from '@/services/api';
import { format } from 'date-fns';

const QUALITY_LABELS = ['', '很差', '较差', '一般', '较好', '很好'];
const DIFFICULTY_LABELS = ['', '很容易', '较容易', '一般', '较难', '很难'];
const FEELING_LABELS = ['', '很疲惫', '疲惫', '一般', '精神', '很精神'];

interface FormData {
  record_date: string;
  bedtime_date: string;
  bedtime_time: string;
  wake_date: string;
  wake_time: string;
  sleep_quality: number;
  wake_count: number;
  had_dream: boolean;
  dream_description: string;
  fall_asleep_difficulty: number | null;
  morning_feeling: number | null;
  notes: string;
}

function SleepContent() {
  const [records, setRecords] = useState<SleepRecordData[]>([]);
  const [stats, setStats] = useState<SleepStats | null>(null);
  const [tab, setTab] = useState<'list' | 'stats'>('list');
  const [showForm, setShowForm] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);

  const now = new Date();
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);

  const [form, setForm] = useState<FormData>({
    record_date: format(now, 'yyyy-MM-dd'),
    bedtime_date: format(yesterday, 'yyyy-MM-dd'),
    bedtime_time: '23:00',
    wake_date: format(now, 'yyyy-MM-dd'),
    wake_time: '07:00',
    sleep_quality: 3,
    wake_count: 0,
    had_dream: false,
    dream_description: '',
    fall_asleep_difficulty: null,
    morning_feeling: null,
    notes: '',
  });

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [recRes, statsRes] = await Promise.allSettled([
        sleepApi.getMyRecords({ limit: 50 }),
        sleepApi.getStats(7),
      ]);
      if (recRes.status === 'fulfilled') setRecords(recRes.value.data);
      if (statsRes.status === 'fulfilled') setStats(statsRes.value.data);
    } catch { /* ignore */ }
    setLoading(false);
  }, []);

  useEffect(() => { void loadData(); }, [loadData]);

  const resetForm = () => {
    const n = new Date();
    const y = new Date(n);
    y.setDate(y.getDate() - 1);
    setForm({
      record_date: format(n, 'yyyy-MM-dd'),
      bedtime_date: format(y, 'yyyy-MM-dd'),
      bedtime_time: '23:00',
      wake_date: format(n, 'yyyy-MM-dd'),
      wake_time: '07:00',
      sleep_quality: 3,
      wake_count: 0,
      had_dream: false,
      dream_description: '',
      fall_asleep_difficulty: null,
      morning_feeling: null,
      notes: '',
    });
    setEditingId(null);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const bedtime = `${form.bedtime_date}T${form.bedtime_time}:00`;
      const wake_time = `${form.wake_date}T${form.wake_time}:00`;

      const payload: any = {
        record_date: form.record_date,
        bedtime,
        wake_time,
        sleep_quality: form.sleep_quality,
        wake_count: form.wake_count,
        had_dream: form.had_dream,
        dream_description: form.dream_description || null,
        fall_asleep_difficulty: form.fall_asleep_difficulty,
        morning_feeling: form.morning_feeling,
        notes: form.notes || null,
      };

      if (editingId) {
        await sleepApi.updateRecord(editingId, payload);
      } else {
        await sleepApi.createRecord(payload);
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
      await sleepApi.deleteRecord(id);
      await loadData();
    } catch { /* ignore */ }
  };

  const openEdit = (r: SleepRecordData) => {
    const bt = new Date(r.bedtime);
    const wt = new Date(r.wake_time);
    setForm({
      record_date: r.record_date,
      bedtime_date: format(bt, 'yyyy-MM-dd'),
      bedtime_time: format(bt, 'HH:mm'),
      wake_date: format(wt, 'yyyy-MM-dd'),
      wake_time: format(wt, 'HH:mm'),
      sleep_quality: r.sleep_quality,
      wake_count: r.wake_count || 0,
      had_dream: r.had_dream || false,
      dream_description: r.dream_description || '',
      fall_asleep_difficulty: r.fall_asleep_difficulty,
      morning_feeling: r.morning_feeling,
      notes: r.notes || '',
    });
    setEditingId(r.id);
    setShowForm(true);
  };

  const formatDuration = (minutes: number | null) => {
    if (!minutes) return '-';
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return `${h}h${m > 0 ? `${m}m` : ''}`;
  };

  const formatTime = (dt: string) => {
    try {
      return format(new Date(dt), 'HH:mm');
    } catch { return '-'; }
  };

  const qualityColor = (q: number) => {
    if (q >= 4) return 'text-green-600';
    if (q >= 3) return 'text-yellow-600';
    return 'text-red-600';
  };

  const qualityBg = (q: number) => {
    if (q >= 4) return 'bg-green-100 text-green-700';
    if (q >= 3) return 'bg-yellow-100 text-yellow-700';
    return 'bg-red-100 text-red-700';
  };

  return (
    <main className="min-h-screen pt-4 pb-8 px-4 sm:px-8">
      <div className="max-w-3xl mx-auto">
        {/* Header */}
        <div className="flex justify-between items-center mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">睡眠记录</h1>
            <p className="text-sm text-gray-500 mt-1">
              {stats ? `近7天平均: ${stats.avg_duration_hours ? stats.avg_duration_hours.toFixed(1) + 'h' : '-'} / 质量 ${stats.avg_sleep_quality?.toFixed(1) ?? '-'}/5` : '加载中...'}
            </p>
          </div>
          <button onClick={() => { resetForm(); setShowForm(true); }}
            className="bg-indigo-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-indigo-700">
            + 记录
          </button>
        </div>

        {/* Tabs */}
        <div className="flex gap-2 mb-4">
          {(['list', 'stats'] as const).map(t => (
            <button key={t} onClick={() => setTab(t)}
              className={`px-4 py-2 rounded-lg text-sm font-medium ${tab === t ? 'bg-indigo-100 text-indigo-800' : 'bg-gray-100 text-gray-600'}`}>
              {t === 'list' ? '记录列表' : '统计分析'}
            </button>
          ))}
        </div>

        {loading ? (
          <div className="text-center py-12 text-gray-400">加载中...</div>
        ) : tab === 'list' ? (
          <div className="space-y-3">
            {records.length === 0 && <div className="text-center py-12 text-gray-400">暂无记录</div>}
            {records.map(r => (
              <div key={r.id} className="bg-white rounded-xl p-4 shadow-sm border border-gray-100">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-2xl">🌙</span>
                    <div>
                      <div className="font-medium text-gray-800">
                        {r.record_date}
                      </div>
                      <div className="text-xs text-gray-400">
                        {formatTime(r.bedtime)} → {formatTime(r.wake_time)}
                      </div>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button onClick={() => openEdit(r)} className="text-xs text-blue-500 hover:text-blue-700">编辑</button>
                    <button onClick={() => void handleDelete(r.id)} className="text-xs text-red-400 hover:text-red-600">删除</button>
                  </div>
                </div>
                <div className="flex flex-wrap gap-2 mt-2">
                  <span className={`text-xs px-2 py-0.5 rounded-full ${qualityBg(r.sleep_quality)}`}>
                    质量: {QUALITY_LABELS[r.sleep_quality]}
                  </span>
                  <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-100 text-indigo-700">
                    时长: {formatDuration(r.total_duration_minutes)}
                  </span>
                  {(r.wake_count || 0) > 0 && (
                    <span className="text-xs px-2 py-0.5 rounded-full bg-orange-100 text-orange-600">
                      夜醒 {r.wake_count}次
                    </span>
                  )}
                  {r.had_dream && (
                    <span className="text-xs px-2 py-0.5 rounded-full bg-purple-100 text-purple-600">做梦</span>
                  )}
                  {r.morning_feeling && (
                    <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-600">
                      醒后: {FEELING_LABELS[r.morning_feeling]}
                    </span>
                  )}
                </div>
                {r.notes && <p className="text-xs text-gray-500 mt-2">{r.notes}</p>}
              </div>
            ))}
          </div>
        ) : (
          /* Stats */
          stats && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="bg-white rounded-xl p-4 text-center shadow-sm">
                  <div className={`text-2xl font-bold ${qualityColor(stats.avg_sleep_quality ?? 0)}`}>
                    {stats.avg_sleep_quality?.toFixed(1) ?? '-'}
                  </div>
                  <div className="text-xs text-gray-500 mt-1">平均睡眠质量</div>
                </div>
                <div className="bg-white rounded-xl p-4 text-center shadow-sm">
                  <div className="text-2xl font-bold text-indigo-600">
                    {stats.avg_duration_hours?.toFixed(1) ?? '-'}h
                  </div>
                  <div className="text-xs text-gray-500 mt-1">平均睡眠时长</div>
                </div>
                <div className="bg-white rounded-xl p-4 text-center shadow-sm">
                  <div className="text-2xl font-bold text-orange-600">
                    {stats.avg_wake_count?.toFixed(1) ?? '-'}
                  </div>
                  <div className="text-xs text-gray-500 mt-1">平均夜醒次数</div>
                </div>
                <div className="bg-white rounded-xl p-4 text-center shadow-sm">
                  <div className="text-2xl font-bold text-purple-600">
                    {stats.dream_frequency != null ? `${(stats.dream_frequency * 100).toFixed(0)}%` : '-'}
                  </div>
                  <div className="text-xs text-gray-500 mt-1">做梦频率</div>
                </div>
              </div>

              {/* Extra stats row */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="bg-white rounded-xl p-4 text-center shadow-sm">
                  <div className="text-lg font-bold text-gray-700">
                    {stats.avg_bedtime ?? '-'}
                  </div>
                  <div className="text-xs text-gray-500 mt-1">平均入睡时间</div>
                </div>
                <div className="bg-white rounded-xl p-4 text-center shadow-sm">
                  <div className="text-lg font-bold text-gray-700">
                    {stats.avg_wake_time ?? '-'}
                  </div>
                  <div className="text-xs text-gray-500 mt-1">平均醒来时间</div>
                </div>
                <div className="bg-white rounded-xl p-4 text-center shadow-sm">
                  <div className="text-lg font-bold text-gray-700">
                    {stats.avg_fall_asleep_difficulty?.toFixed(1) ?? '-'}
                  </div>
                  <div className="text-xs text-gray-500 mt-1">入睡难度</div>
                </div>
                <div className="bg-white rounded-xl p-4 text-center shadow-sm">
                  <div className="text-lg font-bold text-gray-700">
                    {stats.avg_morning_feeling?.toFixed(1) ?? '-'}
                  </div>
                  <div className="text-xs text-gray-500 mt-1">平均醒后状态</div>
                </div>
              </div>

              {/* Quality distribution */}
              {Object.keys(stats.quality_distribution).length > 0 && (
                <div className="bg-white rounded-xl p-4 shadow-sm">
                  <h3 className="text-sm font-medium text-gray-700 mb-3">睡眠质量分布</h3>
                  <div className="space-y-2">
                    {[1, 2, 3, 4, 5].map(q => {
                      const count = stats.quality_distribution[q] || 0;
                      const pct = stats.total_records > 0 ? (count / stats.total_records * 100) : 0;
                      return (
                        <div key={q} className="flex items-center gap-2">
                          <span className="text-xs w-16 text-gray-500">{q}. {QUALITY_LABELS[q]}</span>
                          <div className="flex-1 h-4 bg-gray-100 rounded-full overflow-hidden">
                            <div className={`h-full rounded-full ${q >= 4 ? 'bg-green-400' : q >= 3 ? 'bg-yellow-400' : 'bg-red-400'}`}
                              style={{ width: `${pct}%` }} />
                          </div>
                          <span className="text-xs text-gray-400 w-8">{count}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Daily trend */}
              {stats.daily_trend.length > 0 && (
                <div className="bg-white rounded-xl p-4 shadow-sm">
                  <h3 className="text-sm font-medium text-gray-700 mb-3">每日趋势</h3>
                  <div className="space-y-2">
                    {stats.daily_trend.map(d => (
                      <div key={d.date} className="flex items-center justify-between text-sm">
                        <span className="text-gray-500">{d.date}</span>
                        <div className="flex gap-3 items-center">
                          <span className={qualityColor(d.sleep_quality)}>质量 {d.sleep_quality}</span>
                          <span className="text-indigo-600">{d.duration_hours ? `${d.duration_hours.toFixed(1)}h` : '-'}</span>
                          {(d.wake_count || 0) > 0 && <span className="text-orange-500">醒{d.wake_count}次</span>}
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
                <h3 className="text-lg font-semibold">{editingId ? '编辑记录' : '新增睡眠记录'}</h3>
                <button onClick={() => { setShowForm(false); resetForm(); }} className="text-gray-400 text-xl">X</button>
              </div>

              {/* Record date */}
              <div className="mb-4">
                <label className="text-xs text-gray-500 block mb-1">记录日期（醒来日期）</label>
                <input type="date" value={form.record_date} onChange={e => setForm(f => ({ ...f, record_date: e.target.value }))}
                  className="w-full px-3 py-2 border rounded-lg text-sm" />
              </div>

              {/* Bedtime */}
              <div className="grid grid-cols-2 gap-3 mb-4">
                <div>
                  <label className="text-xs text-gray-500 block mb-1">入睡日期</label>
                  <input type="date" value={form.bedtime_date} onChange={e => setForm(f => ({ ...f, bedtime_date: e.target.value }))}
                    className="w-full px-3 py-2 border rounded-lg text-sm" />
                </div>
                <div>
                  <label className="text-xs text-gray-500 block mb-1">入睡时间</label>
                  <input type="time" value={form.bedtime_time} onChange={e => setForm(f => ({ ...f, bedtime_time: e.target.value }))}
                    className="w-full px-3 py-2 border rounded-lg text-sm" />
                </div>
              </div>

              {/* Wake time */}
              <div className="grid grid-cols-2 gap-3 mb-4">
                <div>
                  <label className="text-xs text-gray-500 block mb-1">醒来日期</label>
                  <input type="date" value={form.wake_date} onChange={e => setForm(f => ({ ...f, wake_date: e.target.value }))}
                    className="w-full px-3 py-2 border rounded-lg text-sm" />
                </div>
                <div>
                  <label className="text-xs text-gray-500 block mb-1">醒来时间</label>
                  <input type="time" value={form.wake_time} onChange={e => setForm(f => ({ ...f, wake_time: e.target.value }))}
                    className="w-full px-3 py-2 border rounded-lg text-sm" />
                </div>
              </div>

              {/* Sleep quality */}
              <div className="mb-4">
                <label className="text-xs text-gray-500 block mb-2">睡眠质量</label>
                <div className="flex gap-2">
                  {[1, 2, 3, 4, 5].map(v => (
                    <button key={v} onClick={() => setForm(f => ({ ...f, sleep_quality: v }))}
                      className={`flex-1 py-2.5 rounded-lg text-center text-sm font-medium transition-all ${
                        form.sleep_quality === v
                          ? v >= 4 ? 'bg-green-100 text-green-800 ring-2 ring-green-300'
                            : v >= 3 ? 'bg-yellow-100 text-yellow-800 ring-2 ring-yellow-300'
                            : 'bg-red-100 text-red-800 ring-2 ring-red-300'
                          : 'bg-gray-100 text-gray-500'
                      }`}>
                      <div className="text-base">{['😫', '😟', '😐', '😊', '😴'][v - 1]}</div>
                      <div className="text-[10px] mt-0.5">{QUALITY_LABELS[v]}</div>
                    </button>
                  ))}
                </div>
              </div>

              {/* Wake count */}
              <div className="mb-4">
                <label className="text-xs text-gray-500 block mb-1">夜醒次数</label>
                <div className="flex gap-2">
                  {[0, 1, 2, 3, 4, 5].map(v => (
                    <button key={v} onClick={() => setForm(f => ({ ...f, wake_count: v }))}
                      className={`flex-1 py-2 rounded-lg text-sm font-medium ${form.wake_count === v ? 'bg-indigo-100 text-indigo-800 ring-2 ring-indigo-300' : 'bg-gray-100 text-gray-500'}`}>
                      {v === 5 ? '5+' : v}
                    </button>
                  ))}
                </div>
              </div>

              {/* Fall asleep difficulty */}
              <div className="mb-4">
                <label className="text-xs text-gray-500 block mb-2">入睡难度</label>
                <div className="flex gap-2">
                  {[1, 2, 3, 4, 5].map(v => (
                    <button key={v} onClick={() => setForm(f => ({ ...f, fall_asleep_difficulty: v }))}
                      className={`flex-1 py-1.5 rounded-lg text-xs font-medium ${form.fall_asleep_difficulty === v ? 'bg-orange-100 text-orange-800 ring-2 ring-orange-300' : 'bg-gray-100 text-gray-500'}`}>
                      <div>{v}</div>
                      <div className="text-[10px]">{DIFFICULTY_LABELS[v]}</div>
                    </button>
                  ))}
                </div>
              </div>

              {/* Morning feeling */}
              <div className="mb-4">
                <label className="text-xs text-gray-500 block mb-2">醒后感觉</label>
                <div className="flex gap-2">
                  {[1, 2, 3, 4, 5].map(v => (
                    <button key={v} onClick={() => setForm(f => ({ ...f, morning_feeling: v }))}
                      className={`flex-1 py-1.5 rounded-lg text-xs font-medium ${form.morning_feeling === v ? 'bg-teal-100 text-teal-800 ring-2 ring-teal-300' : 'bg-gray-100 text-gray-500'}`}>
                      <div>{v}</div>
                      <div className="text-[10px]">{FEELING_LABELS[v]}</div>
                    </button>
                  ))}
                </div>
              </div>

              {/* Dream */}
              <label className="flex items-center gap-2 mb-3 cursor-pointer">
                <input type="checkbox" checked={form.had_dream} onChange={e => setForm(f => ({ ...f, had_dream: e.target.checked }))}
                  className="w-4 h-4 text-purple-500 rounded" />
                <span className="text-sm text-gray-700">做梦了</span>
              </label>
              {form.had_dream && (
                <div className="mb-4">
                  <label className="text-xs text-gray-500 block mb-1">梦境描述</label>
                  <textarea value={form.dream_description} onChange={e => setForm(f => ({ ...f, dream_description: e.target.value }))}
                    placeholder="简单描述梦的内容..." rows={2} className="w-full px-3 py-2 border rounded-lg text-sm resize-none" />
                </div>
              )}

              {/* Notes */}
              <div className="mb-6">
                <label className="text-xs text-gray-500 block mb-1">备注</label>
                <textarea value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
                  placeholder="可选备注..." rows={2} className="w-full px-3 py-2 border rounded-lg text-sm resize-none" />
              </div>

              <button onClick={() => void handleSave()} disabled={saving}
                className="w-full py-3 rounded-xl bg-indigo-600 text-white font-medium disabled:opacity-50">
                {saving ? '保存中...' : '保存'}
              </button>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}

export default function SleepPage() {
  return <ProtectedRoute><SleepContent /></ProtectedRoute>;
}
