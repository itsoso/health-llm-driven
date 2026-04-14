'use client';

import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { format } from 'date-fns';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import { useAuth } from '@/contexts/AuthContext';
import { useToast } from '@/contexts/ToastContext';
import { api } from '@/services/api/client';
import ProtectedRoute from '@/components/ProtectedRoute';

const QUICK_AMOUNTS = [
  { amount: 200, label: '一杯水', icon: '🥛' },
  { amount: 250, label: '一杯茶', icon: '🍵' },
  { amount: 350, label: '一瓶水', icon: '🧴' },
  { amount: 500, label: '大瓶水', icon: '💧' },
];

const DRINK_TYPES = ['水', '茶', '咖啡', '果汁', '牛奶', '其他'];

function WaterContent() {
  const { user, isAuthenticated } = useAuth();
  const userId = user?.id;
  const queryClient = useQueryClient();

  useEffect(() => { document.title = '饮水 | 健康管理'; }, []);
  const [showForm, setShowForm] = useState(false);
  const [selectedDate, setSelectedDate] = useState(format(new Date(), 'yyyy-MM-dd'));
  const [formData, setFormData] = useState({
    amount: '',
    drink_type: '水',
    notes: '',
  });

  const { showToast } = useToast();
  const today = format(new Date(), 'yyyy-MM-dd');

  // 获取某日饮水记录
  const { data: dailySummary, isLoading } = useQuery({
    queryKey: ['water-summary', selectedDate],
    queryFn: () => api.get(`/water/records/me/date/${selectedDate}`).then(r => r.data),
    enabled: isAuthenticated,
  });

  // 获取统计
  const { data: stats } = useQuery({
    queryKey: ['water-stats'],
    queryFn: () => api.get('/water/records/me/stats', { params: { days: 7 } }).then(r => r.data),
    enabled: isAuthenticated,
  });

  // 获取最近7天记录用于图表
  const { data: recentRecords } = useQuery({
    queryKey: ['water-recent'],
    queryFn: () => api.get('/water/records/me', { params: { limit: 100 } }).then(r => r.data),
    enabled: isAuthenticated,
  });

  // 快速添加
  const quickAddMutation = useMutation({
    mutationFn: (amount: number) =>
      api.post(`/water/records/quick?amount=${amount}`).then(r => r.data),
    onSuccess: (_data, amount) => {
      queryClient.invalidateQueries({ queryKey: ['water-summary'] });
      queryClient.invalidateQueries({ queryKey: ['water-stats'] });
      queryClient.invalidateQueries({ queryKey: ['water-recent'] });
      showToast(`已记录${amount}ml饮水`, 'success');
    },
    onError: () => showToast('操作失败，请重试', 'error'),
  });

  // 创建记录
  const createMutation = useMutation({
    mutationFn: (data: any) => api.post('/water/records', data).then(r => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['water-summary'] });
      queryClient.invalidateQueries({ queryKey: ['water-stats'] });
      queryClient.invalidateQueries({ queryKey: ['water-recent'] });
      setShowForm(false);
      setFormData({ amount: '', drink_type: '水', notes: '' });
      showToast('饮水记录已添加', 'success');
    },
    onError: () => showToast('操作失败，请重试', 'error'),
  });

  // 删除记录
  const deleteMutation = useMutation({
    mutationFn: (recordId: number) =>
      api.delete(`/water/records/${recordId}`).then(r => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['water-summary'] });
      queryClient.invalidateQueries({ queryKey: ['water-stats'] });
      queryClient.invalidateQueries({ queryKey: ['water-recent'] });
      showToast('记录已删除', 'success');
    },
    onError: () => showToast('操作失败，请重试', 'error'),
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    createMutation.mutate({
      user_id: userId,
      record_date: selectedDate,
      amount: parseInt(formData.amount),
      drink_type: formData.drink_type,
      notes: formData.notes || null,
    });
  };

  // 计算环形进度
  const progress = dailySummary?.progress_percentage || 0;
  const circumference = 2 * Math.PI * 45;
  const strokeDashoffset = circumference - (progress / 100) * circumference;

  // 确保recentRecords是数组
  const recentRecordsList = Array.isArray(recentRecords) ? recentRecords : [];

  // 准备图表数据
  const chartData = (() => {
    const dailyData: Record<string, number> = {};
    recentRecordsList.forEach((r: any) => {
      const d = r.record_date;
      if (!dailyData[d]) dailyData[d] = 0;
      dailyData[d] += r.amount || 0;
    });
    
    return Object.entries(dailyData)
      .sort(([a], [b]) => a.localeCompare(b))
      .slice(-7)
      .map(([date, amount]) => ({
        date: format(new Date(date), 'MM-dd'),
        amount,
      }));
  })();

  if (isLoading) {
    return (
      <main className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 pt-4 pb-8 px-8">
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
    <main className="min-h-screen bg-gradient-to-br from-cyan-50 via-white to-blue-50 pt-4 pb-8 px-8">
      <div className="max-w-6xl mx-auto">
        {/* 头部 */}
        <div className="flex justify-between items-center mb-6">
          <div className="flex items-center gap-4">
            <input
              type="date"
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
              className="px-3 py-2 border border-gray-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-cyan-500"
            />
            <p className="text-gray-600 text-sm">每日目标: 2000ml</p>
          </div>
          <button
            onClick={() => setShowForm(!showForm)}
            className="px-4 py-2 bg-gradient-to-r from-cyan-500 to-blue-500 text-white font-semibold rounded-lg hover:from-cyan-600 hover:to-blue-600 shadow-md transition-all"
          >
            {showForm ? '取消' : '+ 自定义'}
          </button>
        </div>

        {/* 今日进度 */}
        <div className="bg-white rounded-xl shadow-md p-6 mb-6 border border-cyan-100">
          <div className="flex items-center justify-between">
            <div className="flex-1">
              <h3 className="text-lg font-bold text-gray-900 mb-2">今日饮水</h3>
              <p className="text-4xl font-bold text-cyan-600 mb-1">
                {dailySummary?.total_amount || 0} <span className="text-lg text-gray-500">/ 2000 ml</span>
              </p>
              <p className="text-sm text-gray-500">还需 {Math.max(0, 2000 - (dailySummary?.total_amount || 0))} ml</p>
            </div>
            {/* 环形进度 */}
            <div className="relative w-28 h-28">
              <svg className="w-28 h-28 transform -rotate-90">
                <circle
                  cx="56"
                  cy="56"
                  r="45"
                  stroke="#e5e7eb"
                  strokeWidth="10"
                  fill="none"
                />
                <circle
                  cx="56"
                  cy="56"
                  r="45"
                  stroke="#06b6d4"
                  strokeWidth="10"
                  fill="none"
                  strokeLinecap="round"
                  strokeDasharray={circumference}
                  strokeDashoffset={strokeDashoffset}
                  className="transition-all duration-500"
                />
              </svg>
              <div className="absolute inset-0 flex items-center justify-center">
                <span className="text-xl font-bold text-cyan-600">{Math.round(progress)}%</span>
              </div>
            </div>
          </div>
        </div>

        {/* 快速添加 */}
        {selectedDate === today && (
          <div className="bg-white rounded-xl shadow-md p-6 mb-6 border border-cyan-100">
            <h3 className="text-lg font-bold text-gray-900 mb-4">⚡ 快速添加</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {QUICK_AMOUNTS.map(item => (
                <button
                  key={item.amount}
                  onClick={() => quickAddMutation.mutate(item.amount)}
                  disabled={quickAddMutation.isPending}
                  className="flex flex-col items-center p-4 bg-cyan-50 rounded-xl hover:bg-cyan-100 transition-all border border-cyan-200 disabled:opacity-50"
                >
                  <span className="text-3xl mb-1">{item.icon}</span>
                  <span className="text-sm font-semibold text-gray-700">{item.label}</span>
                  <span className="text-xs text-cyan-600">{item.amount}ml</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* 自定义表单 */}
        {showForm && (
          <div className="bg-white rounded-xl shadow-lg p-6 mb-6 border border-cyan-200">
            <h3 className="text-xl font-bold text-gray-900 mb-4">💧 自定义饮水记录</h3>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-semibold text-gray-800 mb-2">饮水量 (ml) *</label>
                  <input
                    type="number"
                    required
                    value={formData.amount}
                    onChange={(e) => setFormData({ ...formData, amount: e.target.value })}
                    className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-cyan-500 text-gray-900 text-lg"
                    placeholder="例如: 300"
                  />
                </div>
                <div>
                  <label className="block text-sm font-semibold text-gray-800 mb-2">饮品类型</label>
                  <select
                    value={formData.drink_type}
                    onChange={(e) => setFormData({ ...formData, drink_type: e.target.value })}
                    className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-cyan-500 text-gray-900"
                  >
                    {DRINK_TYPES.map(type => (
                      <option key={type} value={type}>{type}</option>
                    ))}
                  </select>
                </div>
              </div>
              <div>
                <label className="block text-sm font-semibold text-gray-800 mb-2">备注</label>
                <input
                  type="text"
                  value={formData.notes}
                  onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                  className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-cyan-500 text-gray-900"
                  placeholder="可选备注..."
                />
              </div>
              <button
                type="submit"
                disabled={createMutation.isPending}
                className="w-full bg-gradient-to-r from-cyan-500 to-blue-500 text-white py-3 rounded-lg font-semibold hover:from-cyan-600 hover:to-blue-600 disabled:opacity-50 shadow-md transition-all"
              >
                {createMutation.isPending ? '保存中...' : '✓ 保存记录'}
              </button>
            </form>
          </div>
        )}

        {/* 统计和趋势 */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
          {/* 7天统计 */}
          <div className="bg-white rounded-xl shadow-md p-6 border border-gray-200">
            <h3 className="text-lg font-bold text-gray-900 mb-4">📈 7天统计</h3>
            <div className="space-y-3">
              <div className="flex justify-between items-center">
                <span className="text-gray-600">日均饮水</span>
                <span className="font-bold text-cyan-600">{stats?.average_daily_amount?.toFixed(0) || 0} ml</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-gray-600">最高饮水</span>
                <span className="font-bold text-green-600">{stats?.highest_daily_amount || 0} ml</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-gray-600">达标天数</span>
                <span className="font-bold text-blue-600">{stats?.days_reached_target || 0} / {stats?.days_recorded || 0} 天</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-gray-600">达标率</span>
                <span className="font-bold text-purple-600">{stats?.target_percentage?.toFixed(0) || 0}%</span>
              </div>
            </div>
          </div>

          {/* 趋势图 */}
          {chartData.length > 0 ? (
            <div className="bg-white rounded-xl shadow-md p-6 border border-gray-200">
              <h3 className="text-lg font-bold text-gray-900 mb-4">📈 饮水趋势</h3>
              <ResponsiveContainer width="100%" height={180}>
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis dataKey="date" stroke="#6b7280" style={{ fontSize: '11px' }} />
                  <YAxis stroke="#6b7280" style={{ fontSize: '11px' }} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'white',
                      border: '2px solid #e5e7eb',
                      borderRadius: '8px',
                    }}
                  />
                  <ReferenceLine y={2000} stroke="#06b6d4" strokeDasharray="5 5" />
                  <Bar dataKey="amount" fill="#06b6d4" radius={[4, 4, 0, 0]} name="饮水量(ml)" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="bg-white rounded-xl shadow-md p-6 border border-gray-200 text-center py-10">
              <p className="text-4xl mb-3">📈</p>
              <p className="text-gray-500 mb-4">暂无记录</p>
              <button
                onClick={() => setShowForm(true)}
                className="px-4 py-2 bg-gradient-to-r from-cyan-500 to-blue-500 text-white font-semibold rounded-lg hover:from-cyan-600 hover:to-blue-600 shadow-md transition-all"
              >
                记录第一条
              </button>
            </div>
          )}
        </div>

        {/* 今日记录 */}
        <div className="bg-white rounded-xl shadow-md p-6 border border-gray-200">
          <h3 className="text-xl font-bold text-gray-900 mb-4">📋 {selectedDate} 饮水记录</h3>
          {!dailySummary?.records?.length ? (
            <div className="text-center py-10 text-gray-500">
              <p className="text-4xl mb-2">💧</p>
              <p className="mb-4">今天还没有饮水记录</p>
              <button
                onClick={() => setShowForm(true)}
                className="px-4 py-2 bg-gradient-to-r from-cyan-500 to-blue-500 text-white font-semibold rounded-lg hover:from-cyan-600 hover:to-blue-600 shadow-md transition-all"
              >
                记录第一条
              </button>
            </div>
          ) : (
            <div className="space-y-2">
              {dailySummary.records.map((record: any) => (
                <div key={record.id} className="flex items-center justify-between p-3 bg-cyan-50 rounded-lg border border-cyan-100">
                  <div className="flex items-center gap-3">
                    <span className="text-2xl">💧</span>
                    <div>
                      <span className="font-bold text-cyan-600">{record.amount} ml</span>
                      <span className="text-gray-500 text-sm ml-2">{record.drink_type || '水'}</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-xs text-gray-500">
                      {record.drink_time ? format(new Date(`2000-01-01T${record.drink_time}`), 'HH:mm') : ''}
                    </span>
                    <button
                      onClick={() => deleteMutation.mutate(record.id)}
                      className="text-red-500 hover:text-red-700 text-sm"
                    >
                      删除
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </main>
  );
}

// 导出受保护的页面
export default function WaterPage() {
  return (
    <ProtectedRoute>
      <WaterContent />
    </ProtectedRoute>
  );
}

