'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { format } from 'date-fns';
import ProtectedRoute from '@/components/ProtectedRoute';
import { medicationApi, MedicationItem, MedicationTodayStatus } from '@/services/api';

function MedicationContent() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState({
    name: '', dosage: '', frequency: '', times_per_day: '1',
    reminder_times: '', category: '', purpose: '', notes: '',
  });

  const { data: todayStatus, isLoading: statusLoading } = useQuery({
    queryKey: ['medication-today'],
    queryFn: async () => { const r = await medicationApi.getTodayStatus(); return r.data; },
  });

  const { data: medications, isLoading: medsLoading } = useQuery({
    queryKey: ['medications'],
    queryFn: async () => { const r = await medicationApi.listMyMedications(false); return r.data; },
  });

  const { data: adherence } = useQuery({
    queryKey: ['medication-adherence'],
    queryFn: async () => { const r = await medicationApi.getAdherence(7); return r.data; },
  });

  const addMutation = useMutation({
    mutationFn: async (data: any) => {
      const res = await medicationApi.addMedication(data);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['medications'] });
      queryClient.invalidateQueries({ queryKey: ['medication-today'] });
      setShowForm(false);
      setFormData({ name: '', dosage: '', frequency: '', times_per_day: '1', reminder_times: '', category: '', purpose: '', notes: '' });
    },
  });

  const logMutation = useMutation({
    mutationFn: async (data: { medication_id: number; taken_time: string; status: string }) => {
      return medicationApi.logMedication(data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['medication-today'] });
      queryClient.invalidateQueries({ queryKey: ['medication-adherence'] });
    },
  });

  const deactivateMutation = useMutation({
    mutationFn: (id: number) => medicationApi.deactivateMedication(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['medications'] });
      queryClient.invalidateQueries({ queryKey: ['medication-today'] });
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.name) return;
    addMutation.mutate({
      name: formData.name,
      dosage: formData.dosage || undefined,
      frequency: formData.frequency || undefined,
      times_per_day: parseInt(formData.times_per_day) || 1,
      reminder_times: formData.reminder_times ? formData.reminder_times.split(',').map(t => t.trim()) : undefined,
      category: formData.category || undefined,
      purpose: formData.purpose || undefined,
      notes: formData.notes || undefined,
    });
  };

  const handleTake = (medId: number, time: string) => {
    logMutation.mutate({ medication_id: medId, taken_time: time, status: 'taken' });
  };

  const handleSkip = (medId: number, time: string) => {
    logMutation.mutate({ medication_id: medId, taken_time: time, status: 'skipped' });
  };

  const isLoading = statusLoading || medsLoading;

  if (isLoading) {
    return (
      <main className="min-h-screen bg-gradient-to-br from-sky-50 via-white to-rose-50 pt-4 pb-8 px-8">
        <div className="max-w-6xl mx-auto text-center py-20">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-sky-600 mx-auto mb-4" />
          <p className="text-gray-800 text-lg">加载中...</p>
        </div>
      </main>
    );
  }

  const todayList = Array.isArray(todayStatus) ? todayStatus : [];
  const medsList = Array.isArray(medications) ? medications : [];
  const now = format(new Date(), 'HH:mm');

  return (
    <main className="min-h-screen bg-gradient-to-br from-sky-50 via-white to-rose-50 pt-4 pb-8 px-8">
      <div className="max-w-6xl mx-auto">
        {/* 头部 */}
        <div className="flex justify-between items-center mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">用药管理</h1>
            <p className="text-gray-500 mt-1">记录用药、追踪依从性</p>
          </div>
          <button
            onClick={() => setShowForm(!showForm)}
            className="px-4 py-2 bg-sky-600 text-white rounded-lg hover:bg-sky-700 transition-colors"
          >
            {showForm ? '取消' : '+ 添加药品'}
          </button>
        </div>

        {/* 依从性概览 */}
        {adherence && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <div className="bg-white p-4 rounded-xl shadow-sm border">
              <p className="text-sm text-gray-500 mb-1">7日依从率</p>
              <p className={`text-2xl font-bold ${adherence.adherence_rate >= 80 ? 'text-green-600' : adherence.adherence_rate >= 50 ? 'text-yellow-600' : 'text-red-600'}`}>
                {adherence.adherence_rate}%
              </p>
            </div>
            <div className="bg-white p-4 rounded-xl shadow-sm border">
              <p className="text-sm text-gray-500 mb-1">已服用</p>
              <p className="text-2xl font-bold text-sky-600">{adherence.total_taken}</p>
            </div>
            <div className="bg-white p-4 rounded-xl shadow-sm border">
              <p className="text-sm text-gray-500 mb-1">跳过</p>
              <p className="text-2xl font-bold text-orange-600">{adherence.total_skipped}</p>
            </div>
            <div className="bg-white p-4 rounded-xl shadow-sm border">
              <p className="text-sm text-gray-500 mb-1">预期总次</p>
              <p className="text-2xl font-bold text-gray-700">{adherence.total_expected}</p>
            </div>
          </div>
        )}

        {/* 添加表单 */}
        {showForm && (
          <div className="bg-white rounded-xl shadow-sm border p-6 mb-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">添加药品</h3>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">药品名称 *</label>
                  <input type="text" required value={formData.name} onChange={e => setFormData({ ...formData, name: e.target.value })}
                    className="w-full p-2 border rounded-lg text-gray-900" placeholder="如：布洛芬" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">用量</label>
                  <input type="text" value={formData.dosage} onChange={e => setFormData({ ...formData, dosage: e.target.value })}
                    className="w-full p-2 border rounded-lg text-gray-900" placeholder="如：400mg" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">频率</label>
                  <input type="text" value={formData.frequency} onChange={e => setFormData({ ...formData, frequency: e.target.value })}
                    className="w-full p-2 border rounded-lg text-gray-900" placeholder="如：每日2次" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">每日次数</label>
                  <input type="number" min="1" max="10" value={formData.times_per_day} onChange={e => setFormData({ ...formData, times_per_day: e.target.value })}
                    className="w-full p-2 border rounded-lg text-gray-900" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">提醒时间（逗号分隔）</label>
                  <input type="text" value={formData.reminder_times} onChange={e => setFormData({ ...formData, reminder_times: e.target.value })}
                    className="w-full p-2 border rounded-lg text-gray-900" placeholder="08:00, 20:00" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">用途</label>
                  <input type="text" value={formData.purpose} onChange={e => setFormData({ ...formData, purpose: e.target.value })}
                    className="w-full p-2 border rounded-lg text-gray-900" placeholder="如：止痛" />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">备注</label>
                <input type="text" value={formData.notes} onChange={e => setFormData({ ...formData, notes: e.target.value })}
                  className="w-full p-2 border rounded-lg text-gray-900" placeholder="如：饭后服用" />
              </div>
              <button type="submit" disabled={addMutation.isPending}
                className="w-full bg-sky-600 text-white py-2 rounded-lg hover:bg-sky-700 disabled:opacity-50">
                {addMutation.isPending ? '添加中...' : '添加药品'}
              </button>
            </form>
          </div>
        )}

        {/* 今日服药状态 */}
        <div className="bg-white rounded-xl shadow-sm border p-6 mb-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">今日用药</h3>
          {todayList.length === 0 ? (
            <p className="text-gray-400 text-center py-8">暂无在服药品，点击上方按钮添加</p>
          ) : (
            <div className="space-y-4">
              {todayList.map((med: MedicationTodayStatus) => (
                <div key={med.medication_id} className="border rounded-lg p-4">
                  <div className="flex justify-between items-center mb-2">
                    <div>
                      <h4 className="font-medium text-gray-900">{med.name}</h4>
                      {med.dosage && <span className="text-sm text-gray-500">{med.dosage}</span>}
                    </div>
                    <span className={`text-sm font-medium ${med.taken_count >= med.total_count ? 'text-green-600' : 'text-orange-600'}`}>
                      {med.taken_count}/{med.total_count}
                    </span>
                  </div>
                  <div className="flex gap-2 flex-wrap">
                    {med.reminder_times.map((time, i) => {
                      const logged = med.logs.find(l => l.time === time);
                      return (
                        <div key={i} className="flex items-center gap-1">
                          {logged ? (
                            <span className={`px-3 py-1 rounded-full text-xs ${logged.status === 'taken' ? 'bg-green-100 text-green-700' : 'bg-orange-100 text-orange-700'}`}>
                              {time} {logged.status === 'taken' ? '已服' : '跳过'}
                            </span>
                          ) : (
                            <>
                              <button onClick={() => handleTake(med.medication_id, time)}
                                className="px-3 py-1 bg-green-500 text-white rounded-full text-xs hover:bg-green-600">
                                {time} 服用
                              </button>
                              <button onClick={() => handleSkip(med.medication_id, time)}
                                className="px-2 py-1 bg-gray-200 text-gray-600 rounded-full text-xs hover:bg-gray-300">
                                跳过
                              </button>
                            </>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 药品列表 */}
        <div className="bg-white rounded-xl shadow-sm border p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">药品列表</h3>
          {medsList.length === 0 ? (
            <p className="text-gray-400 text-center py-4">暂无药品</p>
          ) : (
            <div className="space-y-3">
              {medsList.map((med: MedicationItem) => (
                <div key={med.id} className={`flex justify-between items-center p-3 rounded-lg ${med.is_active ? 'bg-gray-50' : 'bg-gray-100 opacity-60'}`}>
                  <div>
                    <span className="font-medium text-gray-900">{med.name}</span>
                    {med.dosage && <span className="text-sm text-gray-500 ml-2">{med.dosage}</span>}
                    {med.frequency && <span className="text-sm text-gray-400 ml-2">{med.frequency}</span>}
                    {!med.is_active && <span className="text-xs bg-gray-200 text-gray-500 rounded px-1 ml-2">已停用</span>}
                  </div>
                  {med.is_active && (
                    <button
                      onClick={() => { if (confirm('确定停用该药品？')) deactivateMutation.mutate(med.id); }}
                      className="text-sm text-gray-400 hover:text-red-600"
                    >
                      停用
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </main>
  );
}

export default function MedicationPage() {
  return <ProtectedRoute><MedicationContent /></ProtectedRoute>;
}
