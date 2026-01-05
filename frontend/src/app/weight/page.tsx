'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { format, subDays } from 'date-fns';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import { useAuth } from '@/contexts/AuthContext';
import ProtectedRoute from '@/components/ProtectedRoute';

// 使用相对路径，通过Next.js代理到后端
const API_BASE = '/api';

function WeightContent() {
  const { user, isAuthenticated } = useAuth();
  const userId = user?.id;
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState({
    weight: '',
    body_fat_percentage: '',
    muscle_mass: '',
    notes: '',
  });

  const today = format(new Date(), 'yyyy-MM-dd');

  const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;

  // 获取体重记录
  const { data: records, isLoading } = useQuery({
    queryKey: ['weight-records'],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/weight/records/me?limit=90`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      return res.json();
    },
    enabled: isAuthenticated,
  });

  // 获取统计
  const { data: stats } = useQuery({
    queryKey: ['weight-stats'],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/weight/records/me/stats?days=30`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      return res.json();
    },
    enabled: isAuthenticated,
  });

  // 创建记录
  const createMutation = useMutation({
    mutationFn: async (data: any) => {
      const res = await fetch(`${API_BASE}/weight/records`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(data),
      });
      if (!res.ok) {
        throw new Error('保存失败');
      }
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['weight-records'] });
      queryClient.invalidateQueries({ queryKey: ['weight-stats'] });
      setShowForm(false);
      setFormData({ weight: '', body_fat_percentage: '', muscle_mass: '', notes: '' });
      alert('✅ 体重记录保存成功！');
    },
    onError: (error) => {
      alert('❌ 保存失败，请重试');
      console.error('Save error:', error);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    createMutation.mutate({
      user_id: userId,
      record_date: today,
      weight: parseFloat(formData.weight),
      body_fat_percentage: formData.body_fat_percentage ? parseFloat(formData.body_fat_percentage) : null,
      muscle_mass: formData.muscle_mass ? parseFloat(formData.muscle_mass) : null,
      notes: formData.notes || null,
    });
  };

  // 确保records是数组
  const recordsList = Array.isArray(records) ? records : [];

  // 准备图表数据
  const chartData = recordsList
    .slice()
    .sort((a: any, b: any) => new Date(a.record_date).getTime() - new Date(b.record_date).getTime())
    .map((r: any) => ({
      date: format(new Date(r.record_date), 'MM-dd'),
      weight: r.weight,
      bodyFat: r.body_fat_percentage,
    }));

  const getWeightChangeColor = (change: number) => {
    if (change < 0) return 'text-green-600';
    if (change > 0) return 'text-red-600';
    return 'text-gray-600';
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
          <div>
            <p className="text-gray-600 text-sm">追踪体重变化，管理健康目标</p>
          </div>
          <button
            onClick={() => setShowForm(!showForm)}
            className="px-4 py-2 bg-gradient-to-r from-indigo-600 to-purple-600 text-white font-semibold rounded-lg hover:from-indigo-700 hover:to-purple-700 shadow-md transition-all"
          >
            {showForm ? '取消' : '+ 记录体重'}
          </button>
        </div>

        {/* 统计卡片 */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <div className="bg-white p-4 rounded-xl shadow-md border border-indigo-100">
            <p className="text-sm text-gray-600 mb-1">当前体重</p>
            <p className="text-3xl font-bold text-indigo-600">{stats?.current_weight || '-'} <span className="text-lg">kg</span></p>
          </div>
          <div className="bg-white p-4 rounded-xl shadow-md border border-green-100">
            <p className="text-sm text-gray-600 mb-1">30天变化</p>
            <p className={`text-3xl font-bold ${getWeightChangeColor(stats?.weight_change_30d || 0)}`}>
              {stats?.weight_change_30d > 0 ? '+' : ''}{stats?.weight_change_30d || '-'} <span className="text-lg">kg</span>
            </p>
          </div>
          <div className="bg-white p-4 rounded-xl shadow-md border border-blue-100">
            <p className="text-sm text-gray-600 mb-1">最低体重</p>
            <p className="text-3xl font-bold text-blue-600">{stats?.lowest_weight || '-'} <span className="text-lg">kg</span></p>
          </div>
          <div className="bg-white p-4 rounded-xl shadow-md border border-orange-100">
            <p className="text-sm text-gray-600 mb-1">记录天数</p>
            <p className="text-3xl font-bold text-orange-600">{stats?.total_records || 0} <span className="text-lg">天</span></p>
          </div>
        </div>

        {/* 添加记录表单 */}
        {showForm && (
          <div className="bg-white rounded-xl shadow-lg p-6 mb-6 border border-indigo-200">
            <h3 className="text-xl font-bold text-gray-900 mb-4">📝 记录今日体重</h3>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <label className="block text-sm font-semibold text-gray-800 mb-2">
                    体重 (kg) *
                  </label>
                  <input
                    type="number"
                    step="0.1"
                    required
                    value={formData.weight}
                    onChange={(e) => setFormData({ ...formData, weight: e.target.value })}
                    className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 text-gray-900 text-lg"
                    placeholder="例如: 75.5"
                  />
                </div>
                <div>
                  <label className="block text-sm font-semibold text-gray-800 mb-2">
                    体脂率 (%)
                  </label>
                  <input
                    type="number"
                    step="0.1"
                    value={formData.body_fat_percentage}
                    onChange={(e) => setFormData({ ...formData, body_fat_percentage: e.target.value })}
                    className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 text-gray-900 text-lg"
                    placeholder="例如: 20.5"
                  />
                </div>
                <div>
                  <label className="block text-sm font-semibold text-gray-800 mb-2">
                    肌肉量 (kg)
                  </label>
                  <input
                    type="number"
                    step="0.1"
                    value={formData.muscle_mass}
                    onChange={(e) => setFormData({ ...formData, muscle_mass: e.target.value })}
                    className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 text-gray-900 text-lg"
                    placeholder="例如: 55.0"
                  />
                </div>
              </div>
              <div>
                <label className="block text-sm font-semibold text-gray-800 mb-2">备注</label>
                <input
                  type="text"
                  value={formData.notes}
                  onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                  className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 text-gray-900"
                  placeholder="可选备注..."
                />
              </div>
              <button
                type="submit"
                disabled={createMutation.isPending}
                className="w-full bg-gradient-to-r from-indigo-600 to-purple-600 text-white py-3 rounded-lg font-semibold hover:from-indigo-700 hover:to-purple-700 disabled:opacity-50 shadow-md transition-all"
              >
                {createMutation.isPending ? '保存中...' : '✓ 保存记录'}
              </button>
            </form>
          </div>
        )}

        {/* 体重趋势图 */}
        {chartData.length > 0 && (
          <div className="bg-white rounded-xl shadow-md p-6 mb-6 border border-gray-200">
            <h3 className="text-xl font-bold text-gray-900 mb-4">📈 体重趋势</h3>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis dataKey="date" stroke="#6b7280" style={{ fontSize: '12px' }} />
                <YAxis 
                  domain={['dataMin - 2', 'dataMax + 2']} 
                  stroke="#6b7280" 
                  style={{ fontSize: '12px' }}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: 'white',
                    border: '2px solid #e5e7eb',
                    borderRadius: '8px',
                  }}
                />
                {stats?.current_weight && (
                  <ReferenceLine y={stats.current_weight} stroke="#6366f1" strokeDasharray="5 5" label="当前" />
                )}
                <Line
                  type="monotone"
                  dataKey="weight"
                  stroke="#6366f1"
                  strokeWidth={3}
                  dot={{ fill: '#6366f1', r: 4 }}
                  name="体重(kg)"
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* 历史记录 */}
        <div className="bg-white rounded-xl shadow-md p-6 border border-gray-200">
          <h3 className="text-xl font-bold text-gray-900 mb-4">📋 历史记录</h3>
          {recordsList.length === 0 ? (
            <div className="text-center py-10 text-gray-500">
              <p className="text-4xl mb-2">⚖️</p>
              <p>暂无体重记录，开始记录你的第一个数据吧！</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-gray-200">
                    <th className="text-left py-3 px-4 text-sm font-semibold text-gray-700">日期</th>
                    <th className="text-right py-3 px-4 text-sm font-semibold text-gray-700">体重</th>
                    <th className="text-right py-3 px-4 text-sm font-semibold text-gray-700">体脂率</th>
                    <th className="text-right py-3 px-4 text-sm font-semibold text-gray-700">肌肉量</th>
                    <th className="text-left py-3 px-4 text-sm font-semibold text-gray-700">备注</th>
                  </tr>
                </thead>
                <tbody>
                  {recordsList.slice(0, 30).map((record: any, index: number) => (
                    <tr key={record.id} className="border-b border-gray-100 hover:bg-gray-50">
                      <td className="py-3 px-4 text-gray-900">{format(new Date(record.record_date), 'yyyy-MM-dd')}</td>
                      <td className="py-3 px-4 text-right font-bold text-indigo-600">{record.weight} kg</td>
                      <td className="py-3 px-4 text-right text-gray-600">{record.body_fat_percentage ? `${record.body_fat_percentage}%` : '-'}</td>
                      <td className="py-3 px-4 text-right text-gray-600">{record.muscle_mass ? `${record.muscle_mass} kg` : '-'}</td>
                      <td className="py-3 px-4 text-gray-500 text-sm">{record.notes || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}

// 导出受保护的页面
export default function WeightPage() {
  return (
    <ProtectedRoute>
      <WeightContent />
    </ProtectedRoute>
  );
}

