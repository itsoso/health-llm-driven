'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { format } from 'date-fns';
import { api } from '@/services/api/client';
import ProtectedRoute from '@/components/ProtectedRoute';
import { useToast } from '@/contexts/ToastContext';

interface MassageRecord {
  id: number;
  record_date: string;
  start_time?: string;
  duration_minutes?: number;
  location_name?: string;
  location_address?: string;
  massage_type: string;
  therapist?: string;
  body_parts?: string;
  price?: number;
  issues_before?: string;
  treatment_notes?: string;
  feeling_after?: string;
  rating?: number;
  notes?: string;
  created_at?: string;
}

interface MassageStats {
  total_sessions: number;
  total_duration_minutes: number;
  total_cost: number;
  avg_rating?: number;
  favorite_location?: string;
  favorite_therapist?: string;
  last_session_date?: string;
}

const MASSAGE_TYPES = ['盲人按摩', '推拿', '足疗', '正骨', '刮痧', '拔罐', '艾灸', 'SPA', '其他'];
const BODY_PARTS = ['颈椎', '肩部', '背部', '腰部', '腿部', '足部', '头部', '全身'];

function MassageContent() {
  const { showToast } = useToast();
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState({
    record_date: format(new Date(), 'yyyy-MM-dd'),
    start_time: '',
    duration_minutes: '',
    location_name: '',
    location_address: '',
    massage_type: '盲人按摩',
    therapist: '',
    body_parts: [] as string[],
    price: '',
    issues_before: '',
    treatment_notes: '',
    feeling_after: '',
    rating: 5,
    notes: '',
  });

  const { data: records = [], isLoading } = useQuery({
    queryKey: ['massage-records'],
    queryFn: async () => {
      const res = await api.get('/massage/records?limit=50');
      return res.data;
    },
  });

  const { data: stats } = useQuery<MassageStats>({
    queryKey: ['massage-stats'],
    queryFn: async () => {
      const res = await api.get('/massage/stats?days=365');
      return res.data;
    },
  });

  const createMutation = useMutation({
    mutationFn: async (data: any) => {
      const res = await api.post('/massage/records', data);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['massage-records'] });
      queryClient.invalidateQueries({ queryKey: ['massage-stats'] });
      setShowForm(false);
      showToast('记录已保存', 'success');
    },
    onError: () => showToast('保存失败', 'error'),
  });

  const deleteMutation = useMutation({
    mutationFn: async (id: number) => {
      await api.delete(`/massage/records/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['massage-records'] });
      queryClient.invalidateQueries({ queryKey: ['massage-stats'] });
      showToast('已删除', 'success');
    },
  });

  const handleSubmit = () => {
    createMutation.mutate({
      ...formData,
      duration_minutes: formData.duration_minutes ? Number(formData.duration_minutes) : null,
      price: formData.price ? Number(formData.price) : null,
      body_parts: formData.body_parts.join(','),
    });
  };

  const toggleBodyPart = (part: string) => {
    setFormData(prev => ({
      ...prev,
      body_parts: prev.body_parts.includes(part)
        ? prev.body_parts.filter(p => p !== part)
        : [...prev.body_parts, part],
    }));
  };

  return (
    <div className="min-h-screen bg-gray-50 pb-24">
      <div className="max-w-2xl mx-auto px-4 pt-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-xl font-bold text-gray-800">💆 按摩理疗</h1>
          <button onClick={() => setShowForm(!showForm)}
            className="px-4 py-2 bg-emerald-500 text-white text-sm rounded-xl font-medium hover:bg-emerald-600 active:scale-95 transition-all">
            {showForm ? '取消' : '+ 新记录'}
          </button>
        </div>

        {/* Stats */}
        {stats && stats.total_sessions > 0 && (
          <div className="grid grid-cols-4 gap-2 mb-4">
            <div className="bg-white rounded-xl p-3 border border-gray-100 text-center">
              <div className="text-lg font-bold text-gray-800">{stats.total_sessions}</div>
              <div className="text-[10px] text-gray-500">总次数</div>
            </div>
            <div className="bg-white rounded-xl p-3 border border-gray-100 text-center">
              <div className="text-lg font-bold text-gray-800">{Math.round(stats.total_duration_minutes / 60)}h</div>
              <div className="text-[10px] text-gray-500">总时长</div>
            </div>
            <div className="bg-white rounded-xl p-3 border border-gray-100 text-center">
              <div className="text-lg font-bold text-gray-800">¥{Math.round(stats.total_cost)}</div>
              <div className="text-[10px] text-gray-500">总花费</div>
            </div>
            <div className="bg-white rounded-xl p-3 border border-gray-100 text-center">
              <div className="text-lg font-bold text-amber-500">{'⭐'.repeat(Math.round(stats.avg_rating || 0))}</div>
              <div className="text-[10px] text-gray-500">平均评分</div>
            </div>
          </div>
        )}

        {/* Form */}
        {showForm && (
          <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-4 mb-4 space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-gray-500 mb-1 block">日期</label>
                <input type="date" value={formData.record_date} onChange={e => setFormData(p => ({ ...p, record_date: e.target.value }))}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" />
              </div>
              <div>
                <label className="text-xs text-gray-500 mb-1 block">开始时间</label>
                <input type="time" value={formData.start_time} onChange={e => setFormData(p => ({ ...p, start_time: e.target.value }))}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-gray-500 mb-1 block">时长（分钟）</label>
                <input type="number" placeholder="120" value={formData.duration_minutes} onChange={e => setFormData(p => ({ ...p, duration_minutes: e.target.value }))}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" />
              </div>
              <div>
                <label className="text-xs text-gray-500 mb-1 block">费用（元）</label>
                <input type="number" placeholder="200" value={formData.price} onChange={e => setFormData(p => ({ ...p, price: e.target.value }))}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" />
              </div>
            </div>

            <div>
              <label className="text-xs text-gray-500 mb-1 block">类型</label>
              <div className="flex flex-wrap gap-1.5">
                {MASSAGE_TYPES.map(t => (
                  <button key={t} onClick={() => setFormData(p => ({ ...p, massage_type: t }))}
                    className={`px-3 py-1 rounded-full text-xs font-medium transition-all ${formData.massage_type === t ? 'bg-emerald-500 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}>
                    {t}
                  </button>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-gray-500 mb-1 block">店名</label>
                <input type="text" placeholder="一指禅" value={formData.location_name} onChange={e => setFormData(p => ({ ...p, location_name: e.target.value }))}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" />
              </div>
              <div>
                <label className="text-xs text-gray-500 mb-1 block">师傅</label>
                <input type="text" placeholder="6号师傅" value={formData.therapist} onChange={e => setFormData(p => ({ ...p, therapist: e.target.value }))}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" />
              </div>
            </div>

            <div>
              <label className="text-xs text-gray-500 mb-1 block">地址</label>
              <input type="text" placeholder="文一西路xxx号" value={formData.location_address} onChange={e => setFormData(p => ({ ...p, location_address: e.target.value }))}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" />
            </div>

            <div>
              <label className="text-xs text-gray-500 mb-1 block">按摩部位</label>
              <div className="flex flex-wrap gap-1.5">
                {BODY_PARTS.map(p => (
                  <button key={p} onClick={() => toggleBodyPart(p)}
                    className={`px-3 py-1 rounded-full text-xs font-medium transition-all ${formData.body_parts.includes(p) ? 'bg-blue-500 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}>
                    {p}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="text-xs text-gray-500 mb-1 block">按摩前的问题</label>
              <textarea placeholder="左边睡觉压脖子，背部肌肉紧张" value={formData.issues_before} onChange={e => setFormData(p => ({ ...p, issues_before: e.target.value }))}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" rows={2} />
            </div>

            <div>
              <label className="text-xs text-gray-500 mb-1 block">治疗记录</label>
              <textarea placeholder="纠正了睡姿问题，背部肌肉放松" value={formData.treatment_notes} onChange={e => setFormData(p => ({ ...p, treatment_notes: e.target.value }))}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" rows={2} />
            </div>

            <div>
              <label className="text-xs text-gray-500 mb-1 block">按摩后感受</label>
              <textarea placeholder="全身轻松，非常有效果" value={formData.feeling_after} onChange={e => setFormData(p => ({ ...p, feeling_after: e.target.value }))}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" rows={2} />
            </div>

            <div>
              <label className="text-xs text-gray-500 mb-1 block">满意度</label>
              <div className="flex gap-2">
                {[1, 2, 3, 4, 5].map(r => (
                  <button key={r} onClick={() => setFormData(p => ({ ...p, rating: r }))}
                    className={`text-2xl transition-all ${r <= formData.rating ? 'opacity-100' : 'opacity-30'}`}>
                    ⭐
                  </button>
                ))}
              </div>
            </div>

            <button onClick={handleSubmit} disabled={createMutation.isPending}
              className="w-full py-2.5 bg-emerald-500 text-white rounded-xl font-medium hover:bg-emerald-600 active:scale-[0.98] transition-all disabled:opacity-50">
              {createMutation.isPending ? '保存中...' : '保存记录'}
            </button>
          </div>
        )}

        {/* Records */}
        {isLoading ? (
          <div className="text-center py-8 text-gray-400">加载中...</div>
        ) : records.length === 0 ? (
          <div className="text-center py-12 text-gray-400">
            <div className="text-4xl mb-2">💆</div>
            <p>还没有按摩记录</p>
            <p className="text-sm mt-1">点击「+ 新记录」开始记录</p>
          </div>
        ) : (
          <div className="space-y-3">
            {(records as MassageRecord[]).map(r => (
              <div key={r.id} className="bg-white rounded-2xl border border-gray-100 shadow-sm p-4">
                <div className="flex items-start justify-between mb-2">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-bold text-gray-800">{r.massage_type}</span>
                      {r.rating && <span className="text-xs">{'⭐'.repeat(r.rating)}</span>}
                    </div>
                    <div className="text-xs text-gray-400 mt-0.5">
                      {r.record_date} {r.start_time && `${r.start_time}`}
                      {r.duration_minutes && ` · ${r.duration_minutes}分钟`}
                      {r.price && ` · ¥${r.price}`}
                    </div>
                  </div>
                  <button onClick={() => { if (confirm('确认删除？')) deleteMutation.mutate(r.id); }}
                    className="text-xs text-gray-300 hover:text-red-400 transition-colors">删除</button>
                </div>

                {(r.location_name || r.therapist) && (
                  <div className="flex items-center gap-2 text-xs text-gray-500 mb-1.5">
                    {r.location_name && <span>📍 {r.location_name}</span>}
                    {r.location_address && <span className="text-gray-400">({r.location_address})</span>}
                    {r.therapist && <span>👤 {r.therapist}</span>}
                  </div>
                )}

                {r.body_parts && (
                  <div className="flex flex-wrap gap-1 mb-1.5">
                    {r.body_parts.split(',').map(p => (
                      <span key={p} className="text-[10px] px-2 py-0.5 bg-blue-50 text-blue-600 rounded-full">{p.trim()}</span>
                    ))}
                  </div>
                )}

                {r.issues_before && (
                  <div className="text-xs text-gray-600 mb-1">
                    <span className="text-gray-400">问题：</span>{r.issues_before}
                  </div>
                )}
                {r.treatment_notes && (
                  <div className="text-xs text-gray-600 mb-1">
                    <span className="text-gray-400">治疗：</span>{r.treatment_notes}
                  </div>
                )}
                {r.feeling_after && (
                  <div className="text-xs text-emerald-600">
                    <span className="text-gray-400">感受：</span>{r.feeling_after}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default function MassagePage() {
  return (
    <ProtectedRoute>
      <MassageContent />
    </ProtectedRoute>
  );
}
