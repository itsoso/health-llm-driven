'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { habitApi } from '@/services/api';
import { format } from 'date-fns';
import { useAuth } from '@/contexts/AuthContext';
import ProtectedRoute from '@/components/ProtectedRoute';

const CATEGORY_OPTIONS = [
  { value: 'health', label: '健康', icon: '💪' },
  { value: 'exercise', label: '运动', icon: '🏃' },
  { value: 'mindfulness', label: '身心', icon: '🧘' },
  { value: 'sleep', label: '睡眠', icon: '😴' },
  { value: 'learning', label: '学习', icon: '📚' },
  { value: 'life', label: '生活', icon: '🏠' },
  { value: 'other', label: '其他', icon: '📌' },
];

const ICON_OPTIONS = ['💪', '🏃', '🧘', '😴', '💧', '🌞', '📚', '🧠', '❤️', '🌿', '🔥', '⭐'];

function HabitsContent() {
  const { user, isAuthenticated } = useAuth();
  const userId = user?.id;
  const [selectedDate, setSelectedDate] = useState(format(new Date(), 'yyyy-MM-dd'));
  const [showAddForm, setShowAddForm] = useState(false);
  const [activeTab, setActiveTab] = useState<'checkin' | 'stats'>('checkin');
  const queryClient = useQueryClient();

  // 获取习惯列表和打卡状态
  const { data: habitsData, isLoading } = useQuery({
    queryKey: ['habits-with-records', userId, selectedDate],
    queryFn: () => habitApi.getUserRecordsWithStatus(userId!, selectedDate),
    enabled: !!userId,
  });

  // 获取统计数据
  const { data: statsData } = useQuery({
    queryKey: ['habits-stats', userId],
    queryFn: () => habitApi.getStats(userId!, 30),
    enabled: !!userId,
  });

  // 获取今日汇总
  const { data: todaySummary } = useQuery({
    queryKey: ['habits-today-summary', userId],
    queryFn: () => habitApi.getTodaySummary(userId!),
    enabled: !!userId,
  });

  // 创建习惯
  const createMutation = useMutation({
    mutationFn: (data: any) => habitApi.createDefinition(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['habits-with-records'] });
      setShowAddForm(false);
      setFormData({ name: '', category: 'health', icon: '💪', description: '' });
    },
  });

  // 批量打卡
  const checkinMutation = useMutation({
    mutationFn: (data: any) => habitApi.batchCheckin(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['habits-with-records'] });
      queryClient.invalidateQueries({ queryKey: ['habits-stats'] });
      queryClient.invalidateQueries({ queryKey: ['habits-today-summary'] });
    },
  });

  const [formData, setFormData] = useState({
    name: '',
    category: 'health',
    icon: '💪',
    description: '',
  });

  const habits = habitsData?.data || [];
  const stats = statsData?.data || [];
  const summary = todaySummary?.data;

  // 按分类分组
  const groupedHabits = CATEGORY_OPTIONS.map((cat) => ({
    ...cat,
    items: habits.filter((h: any) => h.habit.category === cat.value),
  })).filter((g) => g.items.length > 0);

  const handleToggle = (habitId: number, currentCompleted: boolean) => {
    checkinMutation.mutate({
      user_id: userId,
      record_date: selectedDate,
      checkins: [{ habit_id: habitId, completed: !currentCompleted }],
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
  const totalCount = habits.length;
  const completedCount = habits.filter((h: any) => h.record?.completed).length;
  const completionRate = totalCount > 0 ? Math.round((completedCount / totalCount) * 100) : 0;

  // 找到最长连续打卡
  const maxStreak = habits.reduce((max: number, h: any) => Math.max(max, h.streak || 0), 0);

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
        <div className="bg-gradient-to-r from-purple-500 to-pink-600 rounded-2xl shadow-xl p-6 mb-6 text-white">
          <div className="flex justify-between items-center">
            <div>
              <h2 className="text-2xl font-bold mb-1">✅ 每日习惯打卡</h2>
              <p className="text-purple-100">日期: {selectedDate}</p>
            </div>
            <div className="text-right">
              <div className="text-4xl font-bold">{completedCount}/{totalCount}</div>
              <div className="text-purple-100">完成率 {completionRate}%</div>
            </div>
          </div>
          <div className="mt-4 bg-white/20 rounded-full h-3">
            <div
              className="bg-white h-3 rounded-full transition-all duration-500"
              style={{ width: `${completionRate}%` }}
            ></div>
          </div>
          {maxStreak > 0 && (
            <div className="mt-3 text-purple-100 text-sm">
              🔥 最长连续打卡: {maxStreak} 天
            </div>
          )}
        </div>

        {/* 日期选择和操作按钮 */}
        <div className="flex justify-between items-center mb-6">
          <div className="flex items-center gap-4">
            <input
              type="date"
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
              className="px-4 py-2 border border-gray-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-indigo-500"
            />
            <div className="flex bg-gray-100 rounded-lg p-1">
              <button
                onClick={() => setActiveTab('checkin')}
                className={`px-4 py-2 rounded-md font-medium transition-all ${
                  activeTab === 'checkin'
                    ? 'bg-white shadow text-indigo-600'
                    : 'text-gray-600 hover:text-gray-900'
                }`}
              >
                打卡
              </button>
              <button
                onClick={() => setActiveTab('stats')}
                className={`px-4 py-2 rounded-md font-medium transition-all ${
                  activeTab === 'stats'
                    ? 'bg-white shadow text-indigo-600'
                    : 'text-gray-600 hover:text-gray-900'
                }`}
              >
                统计
              </button>
            </div>
          </div>
          <button
            onClick={() => setShowAddForm(!showAddForm)}
            className="px-4 py-2 bg-gradient-to-r from-indigo-600 to-purple-600 text-white font-semibold rounded-lg hover:from-indigo-700 hover:to-purple-700 shadow-md transition-all"
          >
            {showAddForm ? '取消' : '+ 添加习惯'}
          </button>
        </div>

        {/* 添加习惯表单 */}
        {showAddForm && (
          <div className="bg-white rounded-xl shadow-lg p-6 mb-6 border border-gray-200">
            <h3 className="text-lg font-bold text-gray-900 mb-4">添加新习惯</h3>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-semibold text-gray-800 mb-2">习惯名称 *</label>
                  <input
                    type="text"
                    required
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    className="w-full p-2 border border-gray-300 rounded-md text-gray-900 focus:ring-2 focus:ring-indigo-500"
                    placeholder="例如：晨起喝水"
                  />
                </div>
                <div>
                  <label className="block text-sm font-semibold text-gray-800 mb-2">分类</label>
                  <select
                    value={formData.category}
                    onChange={(e) => setFormData({ ...formData, category: e.target.value })}
                    className="w-full p-2 border border-gray-300 rounded-md text-gray-900 focus:ring-2 focus:ring-indigo-500"
                  >
                    {CATEGORY_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>{opt.icon} {opt.label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-semibold text-gray-800 mb-2">图标</label>
                  <div className="flex flex-wrap gap-2">
                    {ICON_OPTIONS.map((icon) => (
                      <button
                        key={icon}
                        type="button"
                        onClick={() => setFormData({ ...formData, icon })}
                        className={`w-10 h-10 text-xl rounded-lg transition-all ${
                          formData.icon === icon
                            ? 'bg-indigo-100 border-2 border-indigo-500'
                            : 'bg-gray-100 border-2 border-transparent hover:bg-gray-200'
                        }`}
                      >
                        {icon}
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-semibold text-gray-800 mb-2">描述（可选）</label>
                  <input
                    type="text"
                    value={formData.description}
                    onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                    className="w-full p-2 border border-gray-300 rounded-md text-gray-900 focus:ring-2 focus:ring-indigo-500"
                    placeholder="习惯描述..."
                  />
                </div>
              </div>
              <button
                type="submit"
                disabled={createMutation.isPending}
                className="w-full bg-gradient-to-r from-indigo-600 to-purple-600 text-white py-3 rounded-lg font-semibold hover:from-indigo-700 hover:to-purple-700 disabled:opacity-50 shadow-md transition-all"
              >
                {createMutation.isPending ? '添加中...' : '添加习惯'}
              </button>
            </form>
          </div>
        )}

        {activeTab === 'checkin' ? (
          /* 习惯打卡列表 */
          habits.length === 0 ? (
            <div className="text-center py-16 bg-white rounded-xl shadow-md">
              <div className="text-6xl mb-4">✅</div>
              <h3 className="text-xl font-bold text-gray-800 mb-2">还没有添加习惯</h3>
              <p className="text-gray-600 mb-4">点击上方"添加习惯"按钮开始培养好习惯</p>
            </div>
          ) : (
            <div className="space-y-6">
              {groupedHabits.map((group) => (
                <div key={group.value} className="bg-white rounded-xl shadow-md p-4 border border-gray-200">
                  <h3 className="text-lg font-bold text-gray-900 mb-3">
                    {group.icon} {group.label}
                  </h3>
                  <div className="space-y-2">
                    {group.items.map((item: any) => (
                      <div
                        key={item.habit.id}
                        className={`flex items-center justify-between p-3 rounded-lg cursor-pointer transition-all ${
                          item.record?.completed
                            ? 'bg-green-50 border-2 border-green-300'
                            : 'bg-gray-50 border-2 border-gray-200 hover:border-gray-300'
                        }`}
                        onClick={() => handleToggle(item.habit.id, item.record?.completed || false)}
                      >
                        <div className="flex items-center gap-3">
                          <div className={`w-10 h-10 rounded-full flex items-center justify-center text-xl ${
                            item.record?.completed ? 'bg-green-500' : 'bg-gray-200'
                          }`}>
                            {item.record?.completed ? '✓' : item.habit.icon || '📌'}
                          </div>
                          <div>
                            <div className="font-semibold text-gray-900">{item.habit.name}</div>
                            {item.streak > 0 && (
                              <div className="text-sm text-orange-600">🔥 连续 {item.streak} 天</div>
                            )}
                          </div>
                        </div>
                        <div className={`text-sm font-medium ${
                          item.record?.completed ? 'text-green-600' : 'text-gray-500'
                        }`}>
                          {item.record?.completed ? '已完成 ✓' : '未完成'}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )
        ) : (
          /* 统计视图 */
          <div className="bg-white rounded-xl shadow-md p-6 border border-gray-200">
            <h3 className="text-lg font-bold text-gray-900 mb-4">📊 最近30天统计</h3>
            {stats.length === 0 ? (
              <p className="text-gray-600 text-center py-8">暂无统计数据</p>
            ) : (
              <div className="space-y-4">
                {stats.map((stat: any) => (
                  <div key={stat.habit_id} className="p-4 bg-gray-50 rounded-lg">
                    <div className="flex justify-between items-center mb-2">
                      <span className="font-semibold text-gray-900">{stat.habit_name}</span>
                      <div className="flex items-center gap-4 text-sm">
                        <span className="text-gray-600">完成 {stat.completed_days}/{stat.total_days} 天</span>
                        <span className={`font-bold ${
                          stat.completion_rate >= 80 ? 'text-green-600' :
                          stat.completion_rate >= 50 ? 'text-yellow-600' : 'text-red-600'
                        }`}>
                          {stat.completion_rate}%
                        </span>
                      </div>
                    </div>
                    <div className="bg-gray-200 rounded-full h-2 mb-2">
                      <div
                        className={`h-2 rounded-full transition-all ${
                          stat.completion_rate >= 80 ? 'bg-green-500' :
                          stat.completion_rate >= 50 ? 'bg-yellow-500' : 'bg-red-500'
                        }`}
                        style={{ width: `${stat.completion_rate}%` }}
                      ></div>
                    </div>
                    <div className="flex justify-between text-sm text-gray-600">
                      <span>🔥 当前连续: {stat.current_streak} 天</span>
                      <span>⭐ 最长连续: {stat.longest_streak} 天</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </main>
  );
}

// 导出受保护的页面
export default function HabitsPage() {
  return (
    <ProtectedRoute>
      <HabitsContent />
    </ProtectedRoute>
  );
}

