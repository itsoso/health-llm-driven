'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { format } from 'date-fns';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  Legend,
} from 'recharts';
import { useAuth } from '@/contexts/AuthContext';
import ProtectedRoute from '@/components/ProtectedRoute';

// 使用相对路径，通过Next.js代理到后端
const API_BASE = '/api';

function BloodPressureContent() {
  const { user, isAuthenticated } = useAuth();
  const userId = user?.id;
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState({
    systolic: '',
    diastolic: '',
    pulse: '',
    measurement_position: '坐',
    arm: '左',
    notes: '',
  });

  const today = format(new Date(), 'yyyy-MM-dd');
  const now = format(new Date(), 'HH:mm');
  const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;

  // 获取血压记录
  const { data: records, isLoading } = useQuery({
    queryKey: ['blood-pressure-records'],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/blood-pressure/records/me?limit=60`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      return res.json();
    },
    enabled: isAuthenticated,
  });

  // 获取统计
  const { data: stats } = useQuery({
    queryKey: ['blood-pressure-stats'],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/blood-pressure/records/me/stats?days=30`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      return res.json();
    },
    enabled: isAuthenticated,
  });

  // 创建记录
  const createMutation = useMutation({
    mutationFn: async (data: any) => {
      const res = await fetch(`${API_BASE}/blood-pressure/records`, {
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
      queryClient.invalidateQueries({ queryKey: ['blood-pressure-records'] });
      queryClient.invalidateQueries({ queryKey: ['blood-pressure-stats'] });
      setShowForm(false);
      setFormData({ systolic: '', diastolic: '', pulse: '', measurement_position: '坐', arm: '左', notes: '' });
      alert('✅ 血压记录保存成功！');
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
      record_time: now,
      systolic: parseInt(formData.systolic),
      diastolic: parseInt(formData.diastolic),
      pulse: formData.pulse ? parseInt(formData.pulse) : null,
      measurement_position: formData.measurement_position,
      arm: formData.arm,
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
      systolic: r.systolic,
      diastolic: r.diastolic,
      pulse: r.pulse,
    }));

  const getCategoryColor = (category: string) => {
    if (category === '正常') return 'bg-green-100 text-green-800';
    if (category === '正常偏高') return 'bg-yellow-100 text-yellow-800';
    if (category?.includes('前期')) return 'bg-orange-100 text-orange-800';
    return 'bg-red-100 text-red-800';
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
            <p className="text-gray-600 text-sm">监测血压变化，预防心血管疾病</p>
          </div>
          <button
            onClick={() => setShowForm(!showForm)}
            className="px-4 py-2 bg-gradient-to-r from-red-500 to-pink-600 text-white font-semibold rounded-lg hover:from-red-600 hover:to-pink-700 shadow-md transition-all"
          >
            {showForm ? '取消' : '+ 记录血压'}
          </button>
        </div>

        {/* 统计卡片 */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <div className="bg-white p-4 rounded-xl shadow-md border border-red-100">
            <p className="text-sm text-gray-600 mb-1">平均收缩压</p>
            <p className="text-3xl font-bold text-red-600">{stats?.average_systolic?.toFixed(0) || '-'} <span className="text-lg">mmHg</span></p>
          </div>
          <div className="bg-white p-4 rounded-xl shadow-md border border-blue-100">
            <p className="text-sm text-gray-600 mb-1">平均舒张压</p>
            <p className="text-3xl font-bold text-blue-600">{stats?.average_diastolic?.toFixed(0) || '-'} <span className="text-lg">mmHg</span></p>
          </div>
          <div className="bg-white p-4 rounded-xl shadow-md border border-green-100">
            <p className="text-sm text-gray-600 mb-1">正常次数</p>
            <p className="text-3xl font-bold text-green-600">{stats?.normal_count || 0} <span className="text-lg">次</span></p>
          </div>
          <div className="bg-white p-4 rounded-xl shadow-md border border-orange-100">
            <p className="text-sm text-gray-600 mb-1">偏高次数</p>
            <p className="text-3xl font-bold text-orange-600">{(stats?.elevated_count || 0) + (stats?.high_count || 0)} <span className="text-lg">次</span></p>
          </div>
        </div>

        {/* 添加记录表单 */}
        {showForm && (
          <div className="bg-white rounded-xl shadow-lg p-6 mb-6 border border-red-200">
            <h3 className="text-xl font-bold text-gray-900 mb-4">🩺 记录血压</h3>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <label className="block text-sm font-semibold text-gray-800 mb-2">
                    收缩压 (mmHg) *
                  </label>
                  <input
                    type="number"
                    required
                    value={formData.systolic}
                    onChange={(e) => setFormData({ ...formData, systolic: e.target.value })}
                    className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-red-500 text-gray-900 text-lg"
                    placeholder="例如: 120"
                  />
                </div>
                <div>
                  <label className="block text-sm font-semibold text-gray-800 mb-2">
                    舒张压 (mmHg) *
                  </label>
                  <input
                    type="number"
                    required
                    value={formData.diastolic}
                    onChange={(e) => setFormData({ ...formData, diastolic: e.target.value })}
                    className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-red-500 text-gray-900 text-lg"
                    placeholder="例如: 80"
                  />
                </div>
                <div>
                  <label className="block text-sm font-semibold text-gray-800 mb-2">
                    脉搏 (次/分)
                  </label>
                  <input
                    type="number"
                    value={formData.pulse}
                    onChange={(e) => setFormData({ ...formData, pulse: e.target.value })}
                    className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-red-500 text-gray-900 text-lg"
                    placeholder="例如: 72"
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-semibold text-gray-800 mb-2">测量姿势</label>
                  <select
                    value={formData.measurement_position}
                    onChange={(e) => setFormData({ ...formData, measurement_position: e.target.value })}
                    className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-red-500 text-gray-900"
                  >
                    <option value="坐">坐姿</option>
                    <option value="卧">卧姿</option>
                    <option value="站">站姿</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-semibold text-gray-800 mb-2">测量手臂</label>
                  <select
                    value={formData.arm}
                    onChange={(e) => setFormData({ ...formData, arm: e.target.value })}
                    className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-red-500 text-gray-900"
                  >
                    <option value="左">左臂</option>
                    <option value="右">右臂</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="block text-sm font-semibold text-gray-800 mb-2">备注</label>
                <input
                  type="text"
                  value={formData.notes}
                  onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                  className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-red-500 text-gray-900"
                  placeholder="可选备注..."
                />
              </div>
              <button
                type="submit"
                disabled={createMutation.isPending}
                className="w-full bg-gradient-to-r from-red-500 to-pink-600 text-white py-3 rounded-lg font-semibold hover:from-red-600 hover:to-pink-700 disabled:opacity-50 shadow-md transition-all"
              >
                {createMutation.isPending ? '保存中...' : '✓ 保存记录'}
              </button>
            </form>
          </div>
        )}

        {/* 血压参考标准 */}
        <div className="bg-white rounded-xl shadow-md p-4 mb-6 border border-gray-200">
          <h4 className="text-sm font-semibold text-gray-700 mb-2">📊 血压分类标准</h4>
          <div className="flex flex-wrap gap-2 text-xs">
            <span className="px-2 py-1 bg-green-100 text-green-800 rounded">正常: &lt;120/80</span>
            <span className="px-2 py-1 bg-yellow-100 text-yellow-800 rounded">正常偏高: 120-129/&lt;80</span>
            <span className="px-2 py-1 bg-orange-100 text-orange-800 rounded">高血压前期: 130-139/80-89</span>
            <span className="px-2 py-1 bg-red-100 text-red-800 rounded">高血压: ≥140/90</span>
          </div>
        </div>

        {/* 血压趋势图 */}
        {chartData.length > 0 && (
          <div className="bg-white rounded-xl shadow-md p-6 mb-6 border border-gray-200">
            <h3 className="text-xl font-bold text-gray-900 mb-4">📈 血压趋势</h3>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis dataKey="date" stroke="#6b7280" style={{ fontSize: '12px' }} />
                <YAxis domain={[40, 180]} stroke="#6b7280" style={{ fontSize: '12px' }} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: 'white',
                    border: '2px solid #e5e7eb',
                    borderRadius: '8px',
                  }}
                />
                <Legend />
                <ReferenceLine y={120} stroke="#22c55e" strokeDasharray="5 5" />
                <ReferenceLine y={80} stroke="#3b82f6" strokeDasharray="5 5" />
                <Line type="monotone" dataKey="systolic" stroke="#ef4444" strokeWidth={2} name="收缩压" dot={{ r: 3 }} />
                <Line type="monotone" dataKey="diastolic" stroke="#3b82f6" strokeWidth={2} name="舒张压" dot={{ r: 3 }} />
                <Line type="monotone" dataKey="pulse" stroke="#a855f7" strokeWidth={2} name="脉搏" dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* 历史记录 */}
        <div className="bg-white rounded-xl shadow-md p-6 border border-gray-200">
          <h3 className="text-xl font-bold text-gray-900 mb-4">📋 历史记录</h3>
          {recordsList.length === 0 ? (
            <div className="text-center py-10 text-gray-500">
              <p className="text-4xl mb-2">🩺</p>
              <p>暂无血压记录，开始记录你的第一个数据吧！</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-gray-200">
                    <th className="text-left py-3 px-4 text-sm font-semibold text-gray-700">日期</th>
                    <th className="text-center py-3 px-4 text-sm font-semibold text-gray-700">血压</th>
                    <th className="text-center py-3 px-4 text-sm font-semibold text-gray-700">脉搏</th>
                    <th className="text-center py-3 px-4 text-sm font-semibold text-gray-700">分类</th>
                    <th className="text-left py-3 px-4 text-sm font-semibold text-gray-700">备注</th>
                  </tr>
                </thead>
                <tbody>
                  {recordsList.slice(0, 30).map((record: any) => (
                    <tr key={record.id} className="border-b border-gray-100 hover:bg-gray-50">
                      <td className="py-3 px-4 text-gray-900">{format(new Date(record.record_date), 'yyyy-MM-dd')}</td>
                      <td className="py-3 px-4 text-center">
                        <span className="font-bold text-red-600">{record.systolic}</span>
                        <span className="text-gray-400 mx-1">/</span>
                        <span className="font-bold text-blue-600">{record.diastolic}</span>
                        <span className="text-gray-500 text-sm ml-1">mmHg</span>
                      </td>
                      <td className="py-3 px-4 text-center text-purple-600">{record.pulse || '-'}</td>
                      <td className="py-3 px-4 text-center">
                        <span className={`text-xs px-2 py-1 rounded-full ${getCategoryColor(record.category)}`}>
                          {record.category}
                        </span>
                      </td>
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
export default function BloodPressurePage() {
  return (
    <ProtectedRoute>
      <BloodPressureContent />
    </ProtectedRoute>
  );
}

