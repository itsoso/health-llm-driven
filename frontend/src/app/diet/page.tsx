'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { format } from 'date-fns';
import { useAuth } from '@/contexts/AuthContext';
import ProtectedRoute from '@/components/ProtectedRoute';

// 使用相对路径，通过Next.js代理到后端
const API_BASE = '/api';

const MEAL_TYPES = [
  { value: 'breakfast', label: '早餐', icon: '🌅', color: 'bg-yellow-100 text-yellow-800' },
  { value: 'lunch', label: '午餐', icon: '☀️', color: 'bg-orange-100 text-orange-800' },
  { value: 'dinner', label: '晚餐', icon: '🌙', color: 'bg-indigo-100 text-indigo-800' },
  { value: 'snack', label: '加餐', icon: '🍎', color: 'bg-green-100 text-green-800' },
];

function DietContent() {
  const { user, isAuthenticated } = useAuth();
  const userId = user?.id;
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [selectedDate, setSelectedDate] = useState(format(new Date(), 'yyyy-MM-dd'));
  const [formData, setFormData] = useState({
    meal_type: 'breakfast',
    food_items: '',
    calories: '',
    protein: '',
    carbs: '',
    fat: '',
    notes: '',
  });

  const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;

  // 获取某日饮食记录
  const { data: dailySummary, isLoading } = useQuery({
    queryKey: ['diet-summary', selectedDate],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/diet/records/me/date/${selectedDate}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      return res.json();
    },
    enabled: isAuthenticated,
  });

  // 获取统计
  const { data: stats } = useQuery({
    queryKey: ['diet-stats'],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/diet/records/me/stats?days=7`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      return res.json();
    },
    enabled: isAuthenticated,
  });

  // 创建记录
  const createMutation = useMutation({
    mutationFn: async (data: any) => {
      const res = await fetch(`${API_BASE}/diet/records`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(data),
      });
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['diet-summary'] });
      queryClient.invalidateQueries({ queryKey: ['diet-stats'] });
      setShowForm(false);
      setFormData({ meal_type: 'breakfast', food_items: '', calories: '', protein: '', carbs: '', fat: '', notes: '' });
    },
  });

  // 删除记录
  const deleteMutation = useMutation({
    mutationFn: async (recordId: number) => {
      const res = await fetch(`${API_BASE}/diet/records/${recordId}`, { 
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      });
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['diet-summary'] });
      queryClient.invalidateQueries({ queryKey: ['diet-stats'] });
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    createMutation.mutate({
      user_id: userId,
      record_date: selectedDate,
      meal_type: formData.meal_type,
      food_items: formData.food_items,
      calories: formData.calories ? parseInt(formData.calories) : null,
      protein: formData.protein ? parseFloat(formData.protein) : null,
      carbs: formData.carbs ? parseFloat(formData.carbs) : null,
      fat: formData.fat ? parseFloat(formData.fat) : null,
      notes: formData.notes || null,
    });
  };

  const getMealInfo = (mealType: string) => {
    return MEAL_TYPES.find(m => m.value === mealType) || MEAL_TYPES[0];
  };

  if (isLoading) {
    return (
      <main className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 pt-24 pb-8 px-8">
        <div className="max-w-6xl mx-auto">
          <div className="text-center py-20">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto mb-4"></div>
            <p className="text-gray-800 text-lg font-medium">加载中...</p>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 pt-24 pb-8 px-8">
      <div className="max-w-6xl mx-auto">
        {/* 头部 */}
        <div className="flex justify-between items-center mb-6">
          <div className="flex items-center gap-4">
            <input
              type="date"
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
              className="px-3 py-2 border border-gray-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-orange-500"
            />
            <p className="text-gray-600 text-sm">记录每日饮食，控制热量摄入</p>
          </div>
          <button
            onClick={() => setShowForm(!showForm)}
            className="px-4 py-2 bg-gradient-to-r from-orange-500 to-red-500 text-white font-semibold rounded-lg hover:from-orange-600 hover:to-red-600 shadow-md transition-all"
          >
            {showForm ? '取消' : '+ 添加饮食'}
          </button>
        </div>

        {/* 今日统计 */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
          <div className="bg-white p-4 rounded-xl shadow-md border border-orange-100">
            <p className="text-sm text-gray-600 mb-1">今日热量</p>
            <p className="text-2xl font-bold text-orange-600">{dailySummary?.total_calories || 0} <span className="text-sm">kcal</span></p>
          </div>
          <div className="bg-white p-4 rounded-xl shadow-md border border-red-100">
            <p className="text-sm text-gray-600 mb-1">蛋白质</p>
            <p className="text-2xl font-bold text-red-600">{dailySummary?.total_protein?.toFixed(1) || 0} <span className="text-sm">g</span></p>
          </div>
          <div className="bg-white p-4 rounded-xl shadow-md border border-yellow-100">
            <p className="text-sm text-gray-600 mb-1">碳水</p>
            <p className="text-2xl font-bold text-yellow-600">{dailySummary?.total_carbs?.toFixed(1) || 0} <span className="text-sm">g</span></p>
          </div>
          <div className="bg-white p-4 rounded-xl shadow-md border border-purple-100">
            <p className="text-sm text-gray-600 mb-1">脂肪</p>
            <p className="text-2xl font-bold text-purple-600">{dailySummary?.total_fat?.toFixed(1) || 0} <span className="text-sm">g</span></p>
          </div>
          <div className="bg-white p-4 rounded-xl shadow-md border border-green-100">
            <p className="text-sm text-gray-600 mb-1">餐数</p>
            <p className="text-2xl font-bold text-green-600">{dailySummary?.meals_count || 0} <span className="text-sm">餐</span></p>
          </div>
        </div>

        {/* 7天平均 */}
        {stats && stats.days_recorded > 0 && (
          <div className="bg-gradient-to-r from-orange-50 to-red-50 rounded-xl p-4 mb-6 border border-orange-200">
            <h4 className="text-sm font-semibold text-gray-700 mb-2">📊 7天平均摄入</h4>
            <div className="flex flex-wrap gap-4 text-sm">
              <span className="text-gray-700">热量: <strong className="text-orange-600">{stats.average_daily_calories?.toFixed(0)}</strong> kcal</span>
              <span className="text-gray-700">蛋白质: <strong className="text-red-600">{stats.average_daily_protein?.toFixed(1)}</strong> g</span>
              <span className="text-gray-700">碳水: <strong className="text-yellow-600">{stats.average_daily_carbs?.toFixed(1)}</strong> g</span>
              <span className="text-gray-700">脂肪: <strong className="text-purple-600">{stats.average_daily_fat?.toFixed(1)}</strong> g</span>
            </div>
          </div>
        )}

        {/* 添加饮食表单 */}
        {showForm && (
          <div className="bg-white rounded-xl shadow-lg p-6 mb-6 border border-orange-200">
            <h3 className="text-xl font-bold text-gray-900 mb-4">🍽️ 添加饮食记录</h3>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-sm font-semibold text-gray-800 mb-2">餐食类型</label>
                <div className="flex flex-wrap gap-2">
                  {MEAL_TYPES.map(meal => (
                    <button
                      key={meal.value}
                      type="button"
                      onClick={() => setFormData({ ...formData, meal_type: meal.value })}
                      className={`px-4 py-2 rounded-lg font-medium transition-all ${
                        formData.meal_type === meal.value
                          ? 'bg-orange-500 text-white shadow-md'
                          : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                      }`}
                    >
                      {meal.icon} {meal.label}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className="block text-sm font-semibold text-gray-800 mb-2">食物列表 *</label>
                <textarea
                  required
                  value={formData.food_items}
                  onChange={(e) => setFormData({ ...formData, food_items: e.target.value })}
                  className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 text-gray-900"
                  rows={2}
                  placeholder="例如: 鸡蛋2个, 全麦面包1片, 牛奶200ml"
                />
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div>
                  <label className="block text-sm font-semibold text-gray-800 mb-2">热量 (kcal)</label>
                  <input
                    type="number"
                    value={formData.calories}
                    onChange={(e) => setFormData({ ...formData, calories: e.target.value })}
                    className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 text-gray-900"
                    placeholder="300"
                  />
                </div>
                <div>
                  <label className="block text-sm font-semibold text-gray-800 mb-2">蛋白质 (g)</label>
                  <input
                    type="number"
                    step="0.1"
                    value={formData.protein}
                    onChange={(e) => setFormData({ ...formData, protein: e.target.value })}
                    className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 text-gray-900"
                    placeholder="20"
                  />
                </div>
                <div>
                  <label className="block text-sm font-semibold text-gray-800 mb-2">碳水 (g)</label>
                  <input
                    type="number"
                    step="0.1"
                    value={formData.carbs}
                    onChange={(e) => setFormData({ ...formData, carbs: e.target.value })}
                    className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 text-gray-900"
                    placeholder="30"
                  />
                </div>
                <div>
                  <label className="block text-sm font-semibold text-gray-800 mb-2">脂肪 (g)</label>
                  <input
                    type="number"
                    step="0.1"
                    value={formData.fat}
                    onChange={(e) => setFormData({ ...formData, fat: e.target.value })}
                    className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 text-gray-900"
                    placeholder="10"
                  />
                </div>
              </div>
              <div>
                <label className="block text-sm font-semibold text-gray-800 mb-2">备注</label>
                <input
                  type="text"
                  value={formData.notes}
                  onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                  className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 text-gray-900"
                  placeholder="可选备注..."
                />
              </div>
              <button
                type="submit"
                disabled={createMutation.isPending}
                className="w-full bg-gradient-to-r from-orange-500 to-red-500 text-white py-3 rounded-lg font-semibold hover:from-orange-600 hover:to-red-600 disabled:opacity-50 shadow-md transition-all"
              >
                {createMutation.isPending ? '保存中...' : '✓ 保存记录'}
              </button>
            </form>
          </div>
        )}

        {/* 今日饮食记录 */}
        <div className="bg-white rounded-xl shadow-md p-6 border border-gray-200">
          <h3 className="text-xl font-bold text-gray-900 mb-4">📋 {selectedDate} 饮食记录</h3>
          {!dailySummary?.meals?.length ? (
            <div className="text-center py-10 text-gray-500">
              <p className="text-4xl mb-2">🍽️</p>
              <p>今天还没有饮食记录</p>
            </div>
          ) : (
            <div className="space-y-4">
              {dailySummary.meals.map((meal: any) => {
                const mealInfo = getMealInfo(meal.meal_type);
                return (
                  <div key={meal.id} className="flex items-start justify-between p-4 bg-gray-50 rounded-lg border border-gray-100">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-2">
                        <span className={`px-2 py-1 rounded-full text-xs font-semibold ${mealInfo.color}`}>
                          {mealInfo.icon} {mealInfo.label}
                        </span>
                        {meal.calories && (
                          <span className="text-sm text-orange-600 font-medium">{meal.calories} kcal</span>
                        )}
                      </div>
                      <p className="text-gray-900 font-medium">{meal.food_items}</p>
                      <div className="flex gap-4 mt-2 text-xs text-gray-500">
                        {meal.protein && <span>蛋白质: {meal.protein}g</span>}
                        {meal.carbs && <span>碳水: {meal.carbs}g</span>}
                        {meal.fat && <span>脂肪: {meal.fat}g</span>}
                      </div>
                      {meal.notes && <p className="text-sm text-gray-500 mt-1">{meal.notes}</p>}
                    </div>
                    <button
                      onClick={() => deleteMutation.mutate(meal.id)}
                      className="text-red-500 hover:text-red-700 text-sm"
                    >
                      删除
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </main>
  );
}

// 导出受保护的页面
export default function DietPage() {
  return (
    <ProtectedRoute>
      <DietContent />
    </ProtectedRoute>
  );
}

