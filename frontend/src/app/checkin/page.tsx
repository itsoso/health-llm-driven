'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { checkinApi, healthAnalysisApi } from '@/services/api';
import { format } from 'date-fns';
import { useAuth } from '@/contexts/AuthContext';
import ProtectedRoute from '@/components/ProtectedRoute';

function CheckinContent() {
  const { user } = useAuth();
  const userId = user?.id || 1;
  const today = format(new Date(), 'yyyy-MM-dd');
  const queryClient = useQueryClient();

  const { data: todayCheckinResponse, isLoading } = useQuery({
    queryKey: ['checkin', userId, today],
    queryFn: () => checkinApi.getToday(userId),
    retry: false,
  });
  
  // axios返回的是response对象，需要取.data
  const todayCheckin = todayCheckinResponse?.data;

  const { data: adviceResponse } = useQuery({
    queryKey: ['advice', userId, today],
    queryFn: () => healthAnalysisApi.getAdvice(userId, today),
    enabled: !!todayCheckin,
  });
  
  const advice = adviceResponse?.data;

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
    // 鼻炎管理
    sneeze_count: '',
    sneeze_time: '',
    nasal_wash_count: '',
    nasal_wash_time: '',
    nasal_wash_type: 'wash', // wash=洗鼻, soak=泡鼻
    notes: '',
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    
    // 构建鼻炎管理数据
    const sneeze_times = formData.sneeze_time ? [{ time: formData.sneeze_time, count: parseInt(formData.sneeze_count) || 1 }] : null;
    const nasal_wash_times = formData.nasal_wash_time ? [{ time: formData.nasal_wash_time, type: formData.nasal_wash_type }] : null;
    
    mutation.mutate({
      user_id: userId,
      checkin_date: today,
      running_distance: formData.running_distance || null,
      running_duration: formData.running_duration || null,
      squats_count: formData.squats_count || null,
      tai_chi_duration: formData.tai_chi_duration || null,
      ba_duan_jin_duration: formData.ba_duan_jin_duration || null,
      sneeze_count: formData.sneeze_count ? parseInt(formData.sneeze_count) : null,
      sneeze_times: sneeze_times,
      nasal_wash_count: formData.nasal_wash_count ? parseInt(formData.nasal_wash_count) : null,
      nasal_wash_times: nasal_wash_times,
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

          {/* 鼻炎管理 */}
          <div className="bg-white p-6 rounded-lg shadow-md border border-gray-200">
            <h2 className="text-xl font-bold text-gray-900 mb-4">🤧 鼻炎管理</h2>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-semibold text-gray-800 mb-2">打喷嚏次数</label>
                <input
                  type="number"
                  value={formData.sneeze_count}
                  onChange={(e) =>
                    setFormData({ ...formData, sneeze_count: e.target.value })
                  }
                  className="w-full p-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-orange-500 focus:border-orange-500"
                  placeholder="今日打喷嚏总次数"
                />
              </div>

              <div>
                <label className="block text-sm font-semibold text-gray-800 mb-2">打喷嚏时间</label>
                <input
                  type="time"
                  value={formData.sneeze_time}
                  onChange={(e) =>
                    setFormData({ ...formData, sneeze_time: e.target.value })
                  }
                  className="w-full p-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-orange-500 focus:border-orange-500"
                />
              </div>

              <div>
                <label className="block text-sm font-semibold text-gray-800 mb-2">洗鼻/泡鼻次数</label>
                <input
                  type="number"
                  value={formData.nasal_wash_count}
                  onChange={(e) =>
                    setFormData({ ...formData, nasal_wash_count: e.target.value })
                  }
                  className="w-full p-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  placeholder="今日洗鼻泡鼻总次数"
                />
              </div>

              <div>
                <label className="block text-sm font-semibold text-gray-800 mb-2">洗鼻/泡鼻时间</label>
                <input
                  type="time"
                  value={formData.nasal_wash_time}
                  onChange={(e) =>
                    setFormData({ ...formData, nasal_wash_time: e.target.value })
                  }
                  className="w-full p-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
              </div>

              <div className="md:col-span-2">
                <label className="block text-sm font-semibold text-gray-800 mb-2">护理类型</label>
                <div className="flex gap-4">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      name="nasal_wash_type"
                      value="wash"
                      checked={formData.nasal_wash_type === 'wash'}
                      onChange={(e) => setFormData({ ...formData, nasal_wash_type: e.target.value })}
                      className="w-4 h-4 text-blue-600"
                    />
                    <span className="text-gray-800">💧 洗鼻</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      name="nasal_wash_type"
                      value="soak"
                      checked={formData.nasal_wash_type === 'soak'}
                      onChange={(e) => setFormData({ ...formData, nasal_wash_type: e.target.value })}
                      className="w-4 h-4 text-blue-600"
                    />
                    <span className="text-gray-800">🫧 泡鼻</span>
                  </label>
                </div>
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

              {todayCheckin.sneeze_count && (
                <div className="bg-white p-4 rounded-lg border border-orange-200">
                  <div className="flex items-center gap-2">
                    <span className="text-2xl">🤧</span>
                    <div>
                      <div className="text-sm text-gray-600">打喷嚏</div>
                      <div className="text-lg font-bold text-gray-900">{todayCheckin.sneeze_count} 次</div>
                      {todayCheckin.sneeze_times && todayCheckin.sneeze_times.length > 0 && (
                        <div className="text-xs text-gray-500 mt-1">
                          时间: {todayCheckin.sneeze_times.map((t: any) => t.time).join(', ')}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {todayCheckin.nasal_wash_count && (
                <div className="bg-white p-4 rounded-lg border border-blue-200">
                  <div className="flex items-center gap-2">
                    <span className="text-2xl">💧</span>
                    <div>
                      <div className="text-sm text-gray-600">洗鼻/泡鼻</div>
                      <div className="text-lg font-bold text-gray-900">{todayCheckin.nasal_wash_count} 次</div>
                      {todayCheckin.nasal_wash_times && todayCheckin.nasal_wash_times.length > 0 && (
                        <div className="text-xs text-gray-500 mt-1">
                          {todayCheckin.nasal_wash_times.map((t: any, i: number) => (
                            <span key={i}>
                              {t.time} ({t.type === 'wash' ? '洗鼻' : '泡鼻'})
                              {i < todayCheckin.nasal_wash_times.length - 1 && ', '}
                            </span>
                          ))}
                        </div>
                      )}
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

