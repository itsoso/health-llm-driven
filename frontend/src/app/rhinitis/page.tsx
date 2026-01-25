'use client';

import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { format } from 'date-fns';
import { zhCN } from 'date-fns/locale';
import { useAuth } from '@/contexts/AuthContext';
import ProtectedRoute from '@/components/ProtectedRoute';
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '/api';

interface RhinitisRecord {
  id?: number;
  checkin_date: string;
  sneeze_count: number | null;
  sneeze_times: Array<{ time: string; count: number }> | null;
  nasal_wash_count: number | null;
  nasal_wash_times: Array<{ time: string; type: string }> | null;
  notes: string | null;
}

function RhinitisContent() {
  const { token } = useAuth();
  const queryClient = useQueryClient();
  const today = format(new Date(), 'yyyy-MM-dd');

  // 表单状态
  const [sneezeCount, setSneezeCount] = useState<number>(0);
  const [sneezeTime, setSneezeTime] = useState<string>(format(new Date(), 'HH:mm'));
  const [nasalWashCount, setNasalWashCount] = useState<number>(0);
  const [nasalWashTime, setNasalWashTime] = useState<string>(format(new Date(), 'HH:mm'));
  const [nasalWashType, setNasalWashType] = useState<'wash' | 'soak'>('wash');
  const [notes, setNotes] = useState<string>('');
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [days, setDays] = useState<number>(30);

  // 获取今日记录
  const { data: todayRecord, isLoading } = useQuery({
    queryKey: ['rhinitis-today'],
    queryFn: async () => {
      try {
        const res = await fetch(`${API_BASE}/checkin/me/today`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.status === 404) return null;
        if (!res.ok) throw new Error('获取记录失败');
        return res.json();
      } catch {
        return null;
      }
    },
    enabled: !!token,
  });

  // 获取统计数据
  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['rhinitis-stats', days],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/checkin/me/stats?days=${days}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error('获取统计失败');
      return res.json();
    },
    enabled: !!token,
  });

  // 初始化表单数据
  useEffect(() => {
    if (todayRecord) {
      setSneezeCount(todayRecord.sneeze_count || 0);
      setNasalWashCount(todayRecord.nasal_wash_count || 0);
      setNotes(todayRecord.notes || '');
    }
  }, [todayRecord]);

  // 保存记录
  const saveMutation = useMutation({
    mutationFn: async (data: Partial<RhinitisRecord>) => {
      const res = await fetch(`${API_BASE}/checkin/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          checkin_date: today,
          ...data,
        }),
      });
      if (!res.ok) {
        // 检查响应内容类型
        const contentType = res.headers.get('content-type');
        let errorMessage = '保存失败';
        
        if (contentType && contentType.includes('application/json')) {
          try {
            const errorData = await res.json();
            errorMessage = errorData.detail || errorData.message || '保存失败';
          } catch {
            errorMessage = `服务器错误 (${res.status})`;
          }
        } else {
          // 非JSON响应，可能是HTML错误页面
          const text = await res.text();
          errorMessage = `服务器错误 (${res.status}): ${text.substring(0, 100)}`;
        }
        
        throw new Error(errorMessage);
      }
      
      // 确保响应是JSON格式
      const contentType = res.headers.get('content-type');
      if (!contentType || !contentType.includes('application/json')) {
        throw new Error('服务器返回了非JSON格式的响应');
      }
      
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rhinitis-today'] });
      setMessage({ type: 'success', text: '✓ 记录保存成功' });
      setTimeout(() => setMessage(null), 3000);
    },
    onError: (error: Error) => {
      setMessage({ type: 'error', text: `✗ ${error.message}` });
    },
  });

  // 添加打喷嚏记录
  const addSneezeRecord = () => {
    const currentTimes = todayRecord?.sneeze_times || [];
    const newTimes = [...currentTimes, { time: sneezeTime, count: sneezeCount }];
    const totalCount = newTimes.reduce((sum, t) => sum + t.count, 0);
    
    saveMutation.mutate({
      sneeze_count: totalCount,
      sneeze_times: newTimes,
    });
  };

  // 添加洗鼻/泡鼻记录
  const addNasalWashRecord = () => {
    const currentTimes = todayRecord?.nasal_wash_times || [];
    const newTimes = [...currentTimes, { time: nasalWashTime, type: nasalWashType }];
    
    saveMutation.mutate({
      nasal_wash_count: newTimes.length,
      nasal_wash_times: newTimes,
    });
  };

  // 保存备注
  const saveNotes = () => {
    saveMutation.mutate({ notes });
  };

  const sneezeTimes = todayRecord?.sneeze_times || [];
  const nasalWashTimes = todayRecord?.nasal_wash_times || [];

  return (
    <main className="min-h-screen p-4 md:p-8 bg-gradient-to-br from-amber-50 via-orange-50 to-yellow-50 pt-4 md:pt-4">
      <div className="max-w-4xl mx-auto">
        {/* 页面标题 */}
        <div className="mb-6">
          <h1 className="text-2xl md:text-3xl font-bold text-gray-900 flex items-center gap-2">
            <span>🤧</span> 鼻炎追踪
          </h1>
          <p className="text-gray-600 mt-1">
            {format(new Date(), 'yyyy年MM月dd日 EEEE', { locale: zhCN })}
          </p>
        </div>

        {/* 消息提示 */}
        {message && (
          <div className={`mb-4 p-4 rounded-xl ${
            message.type === 'success' 
              ? 'bg-green-100 text-green-800 border border-green-200' 
              : 'bg-red-100 text-red-800 border border-red-200'
          }`}>
            {message.text}
          </div>
        )}

        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-amber-500"></div>
          </div>
        ) : (
          <div className="space-y-6">
            {/* 今日统计 */}
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-white rounded-xl p-4 shadow-sm border border-amber-100">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-2xl">🤧</span>
                  <span className="text-gray-600">今日打喷嚏</span>
                </div>
                <div className="text-3xl font-bold text-amber-600">
                  {todayRecord?.sneeze_count || 0} <span className="text-lg font-normal">次</span>
                </div>
              </div>
              <div className="bg-white rounded-xl p-4 shadow-sm border border-blue-100">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-2xl">💧</span>
                  <span className="text-gray-600">今日洗鼻</span>
                </div>
                <div className="text-3xl font-bold text-blue-600">
                  {todayRecord?.nasal_wash_count || 0} <span className="text-lg font-normal">次</span>
                </div>
              </div>
            </div>

            {/* 打喷嚏记录 */}
            <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
              <h2 className="text-lg font-bold text-gray-900 mb-4 flex items-center gap-2">
                <span>🤧</span> 打喷嚏记录
              </h2>
              
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">次数</label>
                  <input
                    type="number"
                    min="1"
                    value={sneezeCount || ''}
                    placeholder="输入次数"
                    onChange={(e) => setSneezeCount(parseInt(e.target.value) || 0)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 text-gray-900"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">时间</label>
                  <input
                    type="time"
                    value={sneezeTime}
                    onChange={(e) => setSneezeTime(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 text-gray-900"
                  />
                </div>
                <div className="flex items-end">
                  <button
                    onClick={addSneezeRecord}
                    disabled={saveMutation.isPending || sneezeCount <= 0}
                    className="w-full px-4 py-2 bg-amber-500 text-white rounded-lg hover:bg-amber-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    {saveMutation.isPending ? '保存中...' : '➕ 添加记录'}
                  </button>
                </div>
              </div>

              {/* 打喷嚏记录列表 */}
              {sneezeTimes.length > 0 && (
                <div className="mt-4 border-t pt-4">
                  <h3 className="text-sm font-medium text-gray-600 mb-2">今日记录</h3>
                  <div className="flex flex-wrap gap-2">
                    {sneezeTimes.map((record: { time: string; count: number }, index: number) => (
                      <span key={index} className="px-3 py-1 bg-amber-100 text-amber-800 rounded-full text-sm">
                        {record.time} - {record.count}次
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* 洗鼻/泡鼻记录 */}
            <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
              <h2 className="text-lg font-bold text-gray-900 mb-4 flex items-center gap-2">
                <span>💧</span> 洗鼻/泡鼻记录
              </h2>
              
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">类型</label>
                  <div className="flex gap-4">
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="radio"
                        checked={nasalWashType === 'wash'}
                        onChange={() => setNasalWashType('wash')}
                        className="text-blue-500 focus:ring-blue-500"
                      />
                      <span>💧 洗鼻</span>
                    </label>
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="radio"
                        checked={nasalWashType === 'soak'}
                        onChange={() => setNasalWashType('soak')}
                        className="text-blue-500 focus:ring-blue-500"
                      />
                      <span>🫧 泡鼻</span>
                    </label>
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">时间</label>
                  <input
                    type="time"
                    value={nasalWashTime}
                    onChange={(e) => setNasalWashTime(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-gray-900"
                  />
                </div>
                <div className="flex items-end">
                  <button
                    onClick={addNasalWashRecord}
                    disabled={saveMutation.isPending}
                    className="w-full px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    {saveMutation.isPending ? '保存中...' : '➕ 添加记录'}
                  </button>
                </div>
              </div>

              {/* 洗鼻记录列表 */}
              {nasalWashTimes.length > 0 && (
                <div className="mt-4 border-t pt-4">
                  <h3 className="text-sm font-medium text-gray-600 mb-2">今日记录</h3>
                  <div className="flex flex-wrap gap-2">
                    {nasalWashTimes.map((record: { time: string; type: string }, index: number) => (
                      <span key={index} className={`px-3 py-1 rounded-full text-sm ${
                        record.type === 'wash' 
                          ? 'bg-blue-100 text-blue-800' 
                          : 'bg-purple-100 text-purple-800'
                      }`}>
                        {record.time} - {record.type === 'wash' ? '💧洗鼻' : '🫧泡鼻'}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* 备注 */}
            <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
              <h2 className="text-lg font-bold text-gray-900 mb-4 flex items-center gap-2">
                <span>📝</span> 备注
              </h2>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="记录今日鼻炎症状、用药情况等..."
                rows={3}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 resize-none text-gray-900"
              />
              <button
                onClick={saveNotes}
                disabled={saveMutation.isPending}
                className="mt-3 px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 disabled:opacity-50 transition-colors"
              >
                {saveMutation.isPending ? '保存中...' : '💾 保存备注'}
              </button>
            </div>

            {/* 历史统计 */}
            {stats && !statsLoading && stats.total_records > 0 && (
              <>
                {/* 统计卡片 */}
                <div className="bg-gradient-to-r from-amber-500 to-orange-500 rounded-xl p-6 shadow-lg text-white">
                  <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
                    <span>📈</span> 最近 {days} 天统计
                  </h2>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="bg-white/20 rounded-lg p-4 backdrop-blur-sm">
                      <div className="text-sm opacity-90">打卡天数</div>
                      <div className="text-2xl font-bold">{stats.total_records}</div>
                    </div>
                    <div className="bg-white/20 rounded-lg p-4 backdrop-blur-sm">
                      <div className="text-sm opacity-90">平均打喷嚏</div>
                      <div className="text-2xl font-bold">{stats.sneeze_stats.avg_per_day} <span className="text-sm">次/天</span></div>
                    </div>
                    <div className="bg-white/20 rounded-lg p-4 backdrop-blur-sm">
                      <div className="text-sm opacity-90">平均洗鼻</div>
                      <div className="text-2xl font-bold">{stats.nasal_wash_stats.avg_per_day} <span className="text-sm">次/天</span></div>
                    </div>
                    <div className="bg-white/20 rounded-lg p-4 backdrop-blur-sm">
                      <div className="text-sm opacity-90">最多打喷嚏</div>
                      <div className="text-2xl font-bold">{stats.sneeze_stats.max_per_day} <span className="text-sm">次</span></div>
                    </div>
                  </div>
                  
                  {/* 时间范围选择 */}
                  <div className="mt-4 flex gap-2">
                    {[7, 14, 30, 90].map((d) => (
                      <button
                        key={d}
                        onClick={() => setDays(d)}
                        className={`px-3 py-1 rounded-lg text-sm transition-colors ${
                          days === d
                            ? 'bg-white text-amber-600 font-semibold'
                            : 'bg-white/20 hover:bg-white/30'
                        }`}
                      >
                        {d}天
                      </button>
                    ))}
                  </div>
                </div>

                {/* 趋势图表 */}
                <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
                  <h2 className="text-lg font-bold text-gray-900 mb-4">📈 打喷嚏趋势</h2>
                  <ResponsiveContainer width="100%" height={250}>
                    <LineChart data={stats.daily_trend}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                      <XAxis 
                        dataKey="date" 
                        stroke="#6b7280"
                        style={{ fontSize: '12px' }}
                        tickFormatter={(value) => format(new Date(value), 'MM-dd')}
                      />
                      <YAxis 
                        stroke="#6b7280"
                        style={{ fontSize: '12px' }}
                        label={{ value: '次数', angle: -90, position: 'insideLeft' }}
                      />
                      <Tooltip 
                        contentStyle={{ 
                          backgroundColor: 'white', 
                          border: '1px solid #e5e7eb',
                          borderRadius: '8px'
                        }}
                        labelFormatter={(value) => format(new Date(value), 'yyyy-MM-dd')}
                      />
                      <Legend />
                      <Line 
                        type="monotone" 
                        dataKey="sneeze_count" 
                        stroke="#f59e0b" 
                        strokeWidth={2}
                        name="打喷嚏次数"
                        dot={{ fill: '#f59e0b', r: 4 }}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>

                {/* 洗鼻趋势 */}
                <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
                  <h2 className="text-lg font-bold text-gray-900 mb-4">💧 洗鼻/泡鼻趋势</h2>
                  <ResponsiveContainer width="100%" height={250}>
                    <BarChart data={stats.daily_trend}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                      <XAxis 
                        dataKey="date" 
                        stroke="#6b7280"
                        style={{ fontSize: '12px' }}
                        tickFormatter={(value) => format(new Date(value), 'MM-dd')}
                      />
                      <YAxis 
                        stroke="#6b7280"
                        style={{ fontSize: '12px' }}
                        label={{ value: '次数', angle: -90, position: 'insideLeft' }}
                      />
                      <Tooltip 
                        contentStyle={{ 
                          backgroundColor: 'white', 
                          border: '1px solid #e5e7eb',
                          borderRadius: '8px'
                        }}
                        labelFormatter={(value) => format(new Date(value), 'yyyy-MM-dd')}
                      />
                      <Legend />
                      <Bar 
                        dataKey="nasal_wash_count" 
                        fill="#3b82f6" 
                        name="洗鼻次数"
                        radius={[8, 8, 0, 0]}
                      />
                    </BarChart>
                  </ResponsiveContainer>
                </div>

                {/* AI 建议 */}
                <div className="bg-gradient-to-r from-blue-500 to-cyan-500 rounded-xl p-6 shadow-lg text-white">
                  <h2 className="text-lg font-bold mb-3 flex items-center gap-2">
                    <span>✨</span> AI 健康建议
                  </h2>
                  <div className="space-y-2 text-sm">
                    {stats.sneeze_stats.avg_per_day > 10 && (
                      <p>• 最近打喷嚏较频繁（平均 {stats.sneeze_stats.avg_per_day} 次/天），建议增加洗鼻频率，避免接触过敏原</p>
                    )}
                    {stats.nasal_wash_stats.avg_per_day < 2 && (
                      <p>• 洗鼻次数偏少（平均 {stats.nasal_wash_stats.avg_per_day} 次/天），建议每天早晚各洗鼻一次，保持鼻腔清洁</p>
                    )}
                    {stats.nasal_wash_stats.avg_per_day >= 2 && stats.sneeze_stats.avg_per_day < 5 && (
                      <p>• 坚持得很好！继续保持每天洗鼻的习惯，鼻炎症状明显改善 ✨</p>
                    )}
                    {stats.sneeze_stats.max_per_day > 20 && (
                      <p>• 单日最多打喷嚏 {stats.sneeze_stats.max_per_day} 次，建议记录当天的环境和饮食，找出过敏原</p>
                    )}
                    <p>• 建议：保持室内空气湿度在 40-60%，定期清洁床品，避免尘螨滋生</p>
                  </div>
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </main>
  );
}

export default function RhinitisPage() {
  return (
    <ProtectedRoute>
      <RhinitisContent />
    </ProtectedRoute>
  );
}

