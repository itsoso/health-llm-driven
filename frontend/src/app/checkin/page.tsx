'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { checkinApi, healthAnalysisApi } from '@/services/api';
import { format } from 'date-fns';
import { useAuth } from '@/contexts/AuthContext';
import ProtectedRoute from '@/components/ProtectedRoute';

function CheckinContent() {
  const { user, isAuthenticated } = useAuth();
  const userId = user?.id;
  const today = format(new Date(), 'yyyy-MM-dd');
  const queryClient = useQueryClient();

  const { data: todayCheckinResponse, isLoading } = useQuery({
    queryKey: ['checkin', 'today'],
    queryFn: () => checkinApi.getMyToday(),
    retry: false,
    enabled: isAuthenticated,
  });
  
  // axios返回的是response对象，需要取.data
  const todayCheckin = todayCheckinResponse?.data;

  const { data: adviceResponse } = useQuery({
    queryKey: ['advice', today],
    queryFn: () => healthAnalysisApi.getMyAdvice(today),
    enabled: isAuthenticated && !!todayCheckin,
  });
  
  const advice = adviceResponse?.data;

  const mutation = useMutation({
    mutationFn: (data: any) => checkinApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['checkin'] });
    },
  });

  const [formData, setFormData] = useState({
    running_distance: '',
    running_duration: '',
    squats_count: '',
    tai_chi_duration: '',
    ba_duan_jin_duration: '',
    notes: '',
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    
    mutation.mutate({
      checkin_date: today,
      running_distance: formData.running_distance || null,
      running_duration: formData.running_duration || null,
      squats_count: formData.squats_count || null,
      tai_chi_duration: formData.tai_chi_duration || null,
      ba_duan_jin_duration: formData.ba_duan_jin_duration || null,
      notes: formData.notes || null,
    });
  };

  if (isLoading) {
    return <div className="p-8">加载中...</div>;
  }

  return (
    <main className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 pt-24 pb-8 px-8">
      <div className="max-w-4xl mx-auto">
        <p className="text-gray-800 font-semibold mb-8 text-lg">日期: {today}</p>

        {advice && (
          <div className="mb-6 p-4 bg-blue-50 rounded-lg border border-blue-200">
            <h2 className="font-bold text-gray-900 mb-2">💡 今日个性化建议</h2>
            <p className="text-sm text-gray-800">{advice.advice}</p>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="bg-white p-6 rounded-lg shadow-md border border-gray-200">
            <h2 className="text-xl font-bold text-gray-900 mb-4">🏃 专项锻炼</h2>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-semibold text-gray-800 mb-2">跑步距离 (km)</label>
                <input
                  type="number"
                  step="0.1"
                  value={formData.running_distance}
                  onChange={(e) =>
                    setFormData({ ...formData, running_distance: e.target.value })
                  }
                  className="w-full p-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="block text-sm font-semibold text-gray-800 mb-2">跑步时长 (分钟)</label>
                <input
                  type="number"
                  value={formData.running_duration}
                  onChange={(e) =>
                    setFormData({ ...formData, running_duration: e.target.value })
                  }
                  className="w-full p-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="block text-sm font-semibold text-gray-800 mb-2">深蹲次数</label>
                <input
                  type="number"
                  value={formData.squats_count}
                  onChange={(e) =>
                    setFormData({ ...formData, squats_count: e.target.value })
                  }
                  className="w-full p-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="block text-sm font-semibold text-gray-800 mb-2">太极拳时长 (分钟)</label>
                <input
                  type="number"
                  value={formData.tai_chi_duration}
                  onChange={(e) =>
                    setFormData({ ...formData, tai_chi_duration: e.target.value })
                  }
                  className="w-full p-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="block text-sm font-semibold text-gray-800 mb-2">八段锦时长 (分钟)</label>
                <input
                  type="number"
                  value={formData.ba_duan_jin_duration}
                  onChange={(e) =>
                    setFormData({ ...formData, ba_duan_jin_duration: e.target.value })
                  }
                  className="w-full p-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                />
              </div>
            </div>
          </div>

          <div className="bg-white p-6 rounded-lg shadow-md border border-gray-200">
            <label className="block text-sm font-semibold text-gray-800 mb-2">📝 备注</label>
            <textarea
              value={formData.notes}
              onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
              className="w-full p-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-gray-900"
              rows={4}
            />
          </div>

          <button
            type="submit"
            className="w-full bg-gradient-to-r from-indigo-600 to-purple-600 text-white py-3 px-4 rounded-lg font-semibold hover:from-indigo-700 hover:to-purple-700 disabled:opacity-50 disabled:cursor-not-allowed shadow-md transition-all duration-200"
            disabled={mutation.isPending}
          >
            {mutation.isPending ? '提交中...' : '✓ 提交打卡'}
          </button>
        </form>

        {todayCheckin && (
          <div className="mt-6 p-6 bg-green-50 rounded-lg border border-green-200 shadow-sm">
            <h3 className="font-bold text-gray-900 mb-4 text-lg">✅ 今日已打卡</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {todayCheckin.running_distance && (
                <div className="bg-white p-4 rounded-lg border border-green-200">
                  <div className="flex items-center gap-2">
                    <span className="text-2xl">🏃</span>
                    <div>
                      <div className="text-sm text-gray-600">跑步距离</div>
                      <div className="text-lg font-bold text-gray-900">{todayCheckin.running_distance} km</div>
                    </div>
                  </div>
                </div>
              )}
              
              {todayCheckin.running_duration && (
                <div className="bg-white p-4 rounded-lg border border-green-200">
                  <div className="flex items-center gap-2">
                    <span className="text-2xl">⏱️</span>
                    <div>
                      <div className="text-sm text-gray-600">跑步时长</div>
                      <div className="text-lg font-bold text-gray-900">{todayCheckin.running_duration} 分钟</div>
                    </div>
                  </div>
                </div>
              )}
              
              {todayCheckin.squats_count && (
                <div className="bg-white p-4 rounded-lg border border-green-200">
                  <div className="flex items-center gap-2">
                    <span className="text-2xl">🏋️</span>
                    <div>
                      <div className="text-sm text-gray-600">深蹲</div>
                      <div className="text-lg font-bold text-gray-900">{todayCheckin.squats_count} 次</div>
                    </div>
                  </div>
                </div>
              )}
              
              {todayCheckin.tai_chi_duration && (
                <div className="bg-white p-4 rounded-lg border border-green-200">
                  <div className="flex items-center gap-2">
                    <span className="text-2xl">🥋</span>
                    <div>
                      <div className="text-sm text-gray-600">太极拳</div>
                      <div className="text-lg font-bold text-gray-900">{todayCheckin.tai_chi_duration} 分钟</div>
                    </div>
                  </div>
                </div>
              )}
              
              {todayCheckin.ba_duan_jin_duration && (
                <div className="bg-white p-4 rounded-lg border border-green-200">
                  <div className="flex items-center gap-2">
                    <span className="text-2xl">🧘</span>
                    <div>
                      <div className="text-sm text-gray-600">八段锦</div>
                      <div className="text-lg font-bold text-gray-900">{todayCheckin.ba_duan_jin_duration} 分钟</div>
                    </div>
                  </div>
                </div>
              )}

            </div>
            
            {todayCheckin.notes && (
              <div className="mt-4 p-4 bg-white rounded-lg border border-green-200">
                <div className="flex items-start gap-2">
                  <span className="text-xl">📝</span>
                  <div>
                    <div className="text-sm text-gray-600 font-semibold mb-1">备注</div>
                    <div className="text-gray-800">{todayCheckin.notes}</div>
                  </div>
                </div>
              </div>
            )}
            
            <div className="mt-4 text-xs text-gray-600">
              打卡时间: {todayCheckin.created_at 
                ? new Date(todayCheckin.created_at).toLocaleString('zh-CN')
                : todayCheckin.checkin_date 
                  ? todayCheckin.checkin_date 
                  : today}
            </div>
          </div>
        )}

        {mutation.isSuccess && (
          <div className="mt-4 p-4 bg-green-100 rounded-lg text-green-900 border border-green-300 font-semibold">
            ✓ 打卡成功！
          </div>
        )}

        {mutation.isError && (
          <div className="mt-4 p-4 bg-red-100 rounded-lg text-red-900 border border-red-300 font-semibold">
            ✗ 打卡失败，请重试
          </div>
        )}
      </div>
    </main>
  );
}

// 导出受保护的页面
export default function CheckinPage() {
  return (
    <ProtectedRoute>
      <CheckinContent />
    </ProtectedRoute>
  );
}

