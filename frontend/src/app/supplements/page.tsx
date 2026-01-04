'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { supplementApi } from '@/services/api';
import { format } from 'date-fns';
import { useAuth } from '@/contexts/AuthContext';
import ProtectedRoute from '@/components/ProtectedRoute';

const TIMING_OPTIONS = [
  { value: 'morning', label: '🌅 早晨', color: 'bg-orange-100 border-orange-300' },
  { value: 'noon', label: '☀️ 中午', color: 'bg-yellow-100 border-yellow-300' },
  { value: 'evening', label: '🌆 晚上', color: 'bg-purple-100 border-purple-300' },
  { value: 'bedtime', label: '🌙 睡前', color: 'bg-indigo-100 border-indigo-300' },
];

const CATEGORY_OPTIONS = [
  { value: 'vitamin', label: '维生素' },
  { value: 'mineral', label: '矿物质' },
  { value: 'antioxidant', label: '抗氧化' },
  { value: 'amino', label: '氨基酸' },
  { value: 'herb', label: '草药/中药' },
  { value: 'other', label: '其他' },
];

function SupplementsContent() {
  const { user, isAuthenticated } = useAuth();
  const userId = user?.id;
  const [selectedDate, setSelectedDate] = useState(format(new Date(), 'yyyy-MM-dd'));
  const [showAddForm, setShowAddForm] = useState(false);
  const queryClient = useQueryClient();

  // 获取补剂列表和打卡状态
  const { data: supplementsData, isLoading } = useQuery({
    queryKey: ['supplements-with-records', userId, selectedDate],
    queryFn: () => supplementApi.getUserRecordsWithStatus(userId!, selectedDate),
    enabled: !!userId,
  });

  // 获取统计数据
  const { data: statsData } = useQuery({
    queryKey: ['supplements-stats', userId],
    queryFn: () => supplementApi.getStats(userId!, 7),
    enabled: !!userId,
  });

  // 创建补剂
  const createMutation = useMutation({
    mutationFn: (data: any) => supplementApi.createDefinition(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['supplements-with-records'] });
      setShowAddForm(false);
      setFormData({ name: '', dosage: '', timing: 'morning', category: 'vitamin', description: '' });
    },
  });

  // 批量打卡
  const checkinMutation = useMutation({
    mutationFn: (data: any) => supplementApi.batchCheckin(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['supplements-with-records'] });
      queryClient.invalidateQueries({ queryKey: ['supplements-stats'] });
    },
  });

  const [formData, setFormData] = useState({
    name: '',
    dosage: '',
    timing: 'morning',
    category: 'vitamin',
    description: '',
  });

  const supplements = supplementsData?.data || [];
  const stats = statsData?.data || [];

  // 按时间段分组
  const groupedSupplements = TIMING_OPTIONS.map((timing) => ({
    ...timing,
    items: supplements.filter((s: any) => s.supplement.timing === timing.value),
  }));

  const handleToggle = (supplementId: number, currentTaken: boolean) => {
    checkinMutation.mutate({
      user_id: userId,
      record_date: selectedDate,
      checkins: [{ supplement_id: supplementId, taken: !currentTaken }],
    });
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    createMutation.mutate({
      user_id: userId,
      ...formData,
    });
  };

  // 计算今日完成率
  const totalCount = supplements.length;
  const takenCount = supplements.filter((s: any) => s.record?.taken).length;
  const completionRate = totalCount > 0 ? Math.round((takenCount / totalCount) * 100) : 0;

  if (isLoading) {
    return (
      <main className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 pt-24 pb-8 px-8">
        <div className="max-w-4xl mx-auto text-center py-20">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto mb-4"></div>
          <p className="text-gray-700 font-medium">加载中...</p>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 pt-24 pb-8 px-8">
      <div className="max-w-4xl mx-auto">
        {/* 头部统计 */}
        <div className="bg-gradient-to-r from-green-500 to-teal-600 rounded-2xl shadow-xl p-6 mb-6 text-white">
          <div className="flex justify-between items-center">
            <div>
              <h2 className="text-2xl font-bold mb-1">💊 今日补剂打卡</h2>
              <p className="text-green-100">日期: {selectedDate}</p>
            </div>
            <div className="text-right">
              <div className="text-4xl font-bold">{takenCount}/{totalCount}</div>
              <div className="text-green-100">完成率 {completionRate}%</div>
            </div>
          </div>
          <div className="mt-4 bg-white/20 rounded-full h-3">
            <div
              className="bg-white h-3 rounded-full transition-all duration-500"
              style={{ width: `${completionRate}%` }}
            ></div>
          </div>
        </div>

        {/* 日期选择和操作按钮 */}
        <div className="flex justify-between items-center mb-6">
          <input
            type="date"
            value={selectedDate}
            onChange={(e) => setSelectedDate(e.target.value)}
            className="px-4 py-2 border border-gray-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-indigo-500"
          />
          <button
            onClick={() => setShowAddForm(!showAddForm)}
            className="px-4 py-2 bg-gradient-to-r from-indigo-600 to-purple-600 text-white font-semibold rounded-lg hover:from-indigo-700 hover:to-purple-700 shadow-md transition-all"
          >
            {showAddForm ? '取消' : '+ 添加补剂'}
          </button>
        </div>

        {/* 添加补剂表单 */}
        {showAddForm && (
          <div className="bg-white rounded-xl shadow-lg p-6 mb-6 border border-gray-200">
            <h3 className="text-lg font-bold text-gray-900 mb-4">添加新补剂</h3>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-semibold text-gray-800 mb-2">补剂名称 *</label>
                  <input
                    type="text"
                    required
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    className="w-full p-2 border border-gray-300 rounded-md text-gray-900 focus:ring-2 focus:ring-indigo-500"
                    placeholder="例如：维生素D3"
                  />
                </div>
                <div>
                  <label className="block text-sm font-semibold text-gray-800 mb-2">剂量</label>
                  <input
                    type="text"
                    value={formData.dosage}
                    onChange={(e) => setFormData({ ...formData, dosage: e.target.value })}
                    className="w-full p-2 border border-gray-300 rounded-md text-gray-900 focus:ring-2 focus:ring-indigo-500"
                    placeholder="例如：5000IU"
                  />
                </div>
                <div>
                  <label className="block text-sm font-semibold text-gray-800 mb-2">服用时间</label>
                  <select
                    value={formData.timing}
                    onChange={(e) => setFormData({ ...formData, timing: e.target.value })}
                    className="w-full p-2 border border-gray-300 rounded-md text-gray-900 focus:ring-2 focus:ring-indigo-500"
                  >
                    {TIMING_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>{opt.label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-semibold text-gray-800 mb-2">分类</label>
                  <select
                    value={formData.category}
                    onChange={(e) => setFormData({ ...formData, category: e.target.value })}
                    className="w-full p-2 border border-gray-300 rounded-md text-gray-900 focus:ring-2 focus:ring-indigo-500"
                  >
                    {CATEGORY_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>{opt.label}</option>
                    ))}
                  </select>
                </div>
              </div>
              <button
                type="submit"
                disabled={createMutation.isPending}
                className="w-full bg-gradient-to-r from-indigo-600 to-purple-600 text-white py-3 rounded-lg font-semibold hover:from-indigo-700 hover:to-purple-700 disabled:opacity-50 shadow-md transition-all"
              >
                {createMutation.isPending ? '添加中...' : '添加补剂'}
              </button>
            </form>
          </div>
        )}

        {/* 补剂列表（按时间段分组） */}
        {supplements.length === 0 ? (
          <div className="text-center py-16 bg-white rounded-xl shadow-md">
            <div className="text-6xl mb-4">💊</div>
            <h3 className="text-xl font-bold text-gray-800 mb-2">还没有添加补剂</h3>
            <p className="text-gray-600 mb-4">点击上方"添加补剂"按钮开始记录</p>
          </div>
        ) : (
          <div className="space-y-6">
            {groupedSupplements.map((group) => (
              group.items.length > 0 && (
                <div key={group.value} className={`bg-white rounded-xl shadow-md p-4 border-2 ${group.color}`}>
                  <h3 className="text-lg font-bold text-gray-900 mb-3">{group.label}</h3>
                  <div className="space-y-2">
                    {group.items.map((item: any) => (
                      <div
                        key={item.supplement.id}
                        className={`flex items-center justify-between p-3 rounded-lg cursor-pointer transition-all ${
                          item.record?.taken
                            ? 'bg-green-50 border-2 border-green-300'
                            : 'bg-gray-50 border-2 border-gray-200 hover:border-gray-300'
                        }`}
                        onClick={() => handleToggle(item.supplement.id, item.record?.taken || false)}
                      >
                        <div className="flex items-center gap-3">
                          <div className={`w-6 h-6 rounded-full flex items-center justify-center ${
                            item.record?.taken ? 'bg-green-500 text-white' : 'bg-gray-300'
                          }`}>
                            {item.record?.taken && '✓'}
                          </div>
                          <div>
                            <div className="font-semibold text-gray-900">{item.supplement.name}</div>
                            {item.supplement.dosage && (
                              <div className="text-sm text-gray-600">{item.supplement.dosage}</div>
                            )}
                          </div>
                        </div>
                        <div className={`text-sm font-medium ${
                          item.record?.taken ? 'text-green-600' : 'text-gray-500'
                        }`}>
                          {item.record?.taken ? '已服用 ✓' : '未服用'}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )
            ))}
          </div>
        )}

        {/* 最近7天统计 */}
        {stats.length > 0 && (
          <div className="mt-8 bg-white rounded-xl shadow-md p-6 border border-gray-200">
            <h3 className="text-lg font-bold text-gray-900 mb-4">📊 最近7天统计</h3>
            <div className="space-y-3">
              {stats.map((stat: any) => (
                <div key={stat.supplement_id} className="flex items-center justify-between">
                  <div className="flex-1">
                    <div className="flex justify-between mb-1">
                      <span className="text-sm font-medium text-gray-800">{stat.supplement_name}</span>
                      <span className="text-sm text-gray-600">{stat.taken_days}/7天</span>
                    </div>
                    <div className="bg-gray-200 rounded-full h-2">
                      <div
                        className={`h-2 rounded-full transition-all ${
                          stat.completion_rate >= 80 ? 'bg-green-500' :
                          stat.completion_rate >= 50 ? 'bg-yellow-500' : 'bg-red-500'
                        }`}
                        style={{ width: `${stat.completion_rate}%` }}
                      ></div>
                    </div>
                  </div>
                  <div className="ml-4 text-sm font-semibold text-gray-700 w-12 text-right">
                    {stat.completion_rate}%
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </main>
  );
}

// 导出受保护的页面
export default function SupplementsPage() {
  return (
    <ProtectedRoute>
      <SupplementsContent />
    </ProtectedRoute>
  );
}

