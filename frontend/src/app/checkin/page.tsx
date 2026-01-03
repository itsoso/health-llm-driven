'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { checkinApi, healthAnalysisApi } from '@/services/api';
import { format } from 'date-fns';

export default function CheckinPage() {
  const [userId] = useState(1); // 临时使用固定用户ID
  const today = format(new Date(), 'yyyy-MM-dd');
  const queryClient = useQueryClient();

  const { data: todayCheckin, isLoading } = useQuery({
    queryKey: ['checkin', userId, today],
    queryFn: () => checkinApi.getToday(userId),
    retry: false,
  });

  const { data: advice } = useQuery({
    queryKey: ['advice', userId, today],
    queryFn: () => healthAnalysisApi.getAdvice(userId, today),
    enabled: !!todayCheckin,
  });

  const mutation = useMutation({
    mutationFn: (data: any) => checkinApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['checkin', userId] });
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
      user_id: userId,
      checkin_date: today,
      ...formData,
    });
  };

  if (isLoading) {
    return <div className="p-8">加载中...</div>;
  }

  return (
    <main className="min-h-screen p-8">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-3xl font-bold mb-6">每日健康打卡</h1>
        <p className="text-gray-600 mb-8">日期: {today}</p>

        {advice && (
          <div className="mb-6 p-4 bg-blue-50 rounded-lg">
            <h2 className="font-semibold mb-2">今日个性化建议</h2>
            <p className="text-sm text-gray-700">{advice.advice}</p>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="bg-white p-6 rounded-lg shadow-md">
            <h2 className="text-xl font-semibold mb-4">专项锻炼</h2>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium mb-2">跑步距离 (km)</label>
                <input
                  type="number"
                  step="0.1"
                  value={formData.running_distance}
                  onChange={(e) =>
                    setFormData({ ...formData, running_distance: e.target.value })
                  }
                  className="w-full p-2 border rounded-md"
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">跑步时长 (分钟)</label>
                <input
                  type="number"
                  value={formData.running_duration}
                  onChange={(e) =>
                    setFormData({ ...formData, running_duration: e.target.value })
                  }
                  className="w-full p-2 border rounded-md"
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">深蹲次数</label>
                <input
                  type="number"
                  value={formData.squats_count}
                  onChange={(e) =>
                    setFormData({ ...formData, squats_count: e.target.value })
                  }
                  className="w-full p-2 border rounded-md"
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">太极拳时长 (分钟)</label>
                <input
                  type="number"
                  value={formData.tai_chi_duration}
                  onChange={(e) =>
                    setFormData({ ...formData, tai_chi_duration: e.target.value })
                  }
                  className="w-full p-2 border rounded-md"
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">八段锦时长 (分钟)</label>
                <input
                  type="number"
                  value={formData.ba_duan_jin_duration}
                  onChange={(e) =>
                    setFormData({ ...formData, ba_duan_jin_duration: e.target.value })
                  }
                  className="w-full p-2 border rounded-md"
                />
              </div>
            </div>
          </div>

          <div className="bg-white p-6 rounded-lg shadow-md">
            <label className="block text-sm font-medium mb-2">备注</label>
            <textarea
              value={formData.notes}
              onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
              className="w-full p-2 border rounded-md"
              rows={4}
            />
          </div>

          <button
            type="submit"
            className="w-full bg-primary-600 text-white py-3 rounded-md hover:bg-primary-700 transition-colors"
            disabled={mutation.isPending}
          >
            {mutation.isPending ? '提交中...' : '提交打卡'}
          </button>
        </form>

        {todayCheckin && (
          <div className="mt-6 p-4 bg-gray-50 rounded-lg">
            <h3 className="font-semibold mb-2">今日已打卡</h3>
            <pre className="text-sm overflow-auto">
              {JSON.stringify(todayCheckin, null, 2)}
            </pre>
          </div>
        )}

        {mutation.isSuccess && (
          <div className="mt-4 p-4 bg-green-100 rounded-lg text-green-800">
            打卡成功！
          </div>
        )}

        {mutation.isError && (
          <div className="mt-4 p-4 bg-red-100 rounded-lg text-red-800">
            打卡失败，请重试
          </div>
        )}
      </div>
    </main>
  );
}

