'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { dailyHealthApi, garminAnalysisApi, dataCollectionStatusApi } from '@/services/api';
import { format, subDays } from 'date-fns';
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
import { useAuth } from '@/contexts/AuthContext';
import ProtectedRoute from '@/components/ProtectedRoute';

function GarminContent() {
  const { user, isAuthenticated } = useAuth();
  const userId = user?.id;
  const [days, setDays] = useState(30);
  const [activeTab, setActiveTab] = useState<'data' | 'sleep' | 'heart' | 'battery' | 'activity' | 'comprehensive'>('data');
  
  // 分页状态
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 15; // 每页显示条数

  // 获取Garmin原始数据
  const endDate = format(new Date(), 'yyyy-MM-dd');
  const startDate = format(subDays(new Date(), days), 'yyyy-MM-dd');

  const { data: garminData, isLoading: loadingData } = useQuery({
    queryKey: ['garmin-data', userId, startDate, endDate],
    queryFn: () => dailyHealthApi.getMyGarminData(startDate, endDate),
    enabled: !!userId,
  });

  // 获取同步状态
  const { data: syncStatus } = useQuery({
    queryKey: ['garmin-sync-status', userId, days],
    queryFn: () => dataCollectionStatusApi.getMySyncStatus(days),
    enabled: !!userId,
  });

  // 获取睡眠分析
  const { data: sleepAnalysis } = useQuery({
    queryKey: ['garmin-sleep', userId, days],
    queryFn: () => garminAnalysisApi.analyzeMySleep(days),
    enabled: !!userId && (activeTab === 'sleep' || activeTab === 'comprehensive'),
  });

  // 获取心率分析
  const { data: heartAnalysis } = useQuery({
    queryKey: ['garmin-heart', userId, days],
    queryFn: () => garminAnalysisApi.analyzeMyHeartRate(days),
    enabled: !!userId && (activeTab === 'heart' || activeTab === 'comprehensive'),
  });

  // 获取身体电量分析
  const { data: batteryAnalysis } = useQuery({
    queryKey: ['garmin-battery', userId, days],
    queryFn: () => garminAnalysisApi.analyzeMyBodyBattery(days),
    enabled: !!userId && (activeTab === 'battery' || activeTab === 'comprehensive'),
  });

  // 获取活动分析
  const { data: activityAnalysis } = useQuery({
    queryKey: ['garmin-activity', userId, days],
    queryFn: () => garminAnalysisApi.analyzeMyActivity(days),
    enabled: !!userId && (activeTab === 'activity' || activeTab === 'comprehensive'),
  });

  // 获取综合分析
  const { data: comprehensiveAnalysis } = useQuery({
    queryKey: ['garmin-comprehensive', userId, days],
    queryFn: () => garminAnalysisApi.getMyComprehensive(days),
    enabled: !!userId && activeTab === 'comprehensive',
  });

  // 准备图表数据 - 按日期从旧到新排序
  const chartData = garminData?.data
    ?.slice() // 创建副本，避免修改原数组
    .sort((a: any, b: any) => {
      // 按日期升序排序（从旧到新）
      return new Date(a.record_date).getTime() - new Date(b.record_date).getTime();
    })
    .map((item: any) => ({
      date: format(new Date(item.record_date), 'MM-dd'),
      sleepScore: item.sleep_score,
      deepSleep: item.deep_sleep_duration ? Math.floor(item.deep_sleep_duration / 60) : null,
      remSleep: item.rem_sleep_duration ? Math.floor(item.rem_sleep_duration / 60) : null,
      awake: item.awake_duration ? Math.floor(item.awake_duration / 60) : null,
      nap: item.nap_duration ? Math.floor(item.nap_duration / 60) : null,
      avgHeartRate: item.avg_heart_rate,
      hrv: item.hrv,
      steps: item.steps,
      bodyBattery: item.body_battery_charged,
      stressLevel: item.stress_level,
    })) || [];

  if (loadingData) {
    return (
      <main className="min-h-screen p-8">
        <div className="max-w-7xl mx-auto">
          <div className="text-center">加载中...</div>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen p-8 bg-gradient-to-br from-gray-50 via-white to-blue-50">
      <div className="max-w-7xl mx-auto">
        <div className="mb-6">
          {/* 数据范围选择 */}
          <div className="flex items-center gap-4 mb-4">
            <label className="text-sm font-semibold text-gray-700">查看范围:</label>
            <select
              value={days}
              onChange={(e) => {
                setDays(Number(e.target.value));
                setCurrentPage(1); // 切换范围时重置页码
              }}
              className="px-4 py-2 border-2 border-gray-300 rounded-lg bg-white text-gray-900 font-medium focus:border-blue-500 focus:outline-none shadow-sm"
            >
              <option value={7}>最近7天</option>
              <option value={30}>最近30天</option>
              <option value={90}>最近90天</option>
              <option value={180}>最近180天</option>
              <option value={365}>最近1年</option>
              <option value={730}>最近2年</option>
            </select>
          </div>

          {/* 同步状态 */}
          {syncStatus?.data && (
            <div className="mb-4 p-5 bg-gradient-to-r from-blue-50 to-indigo-50 rounded-xl border-2 border-blue-200 shadow-md">
              <div className="flex justify-between items-center">
                <div>
                  <p className="text-sm font-medium text-gray-700 mb-1">数据覆盖情况</p>
                  <p className="text-2xl font-bold text-gray-900">
                    {syncStatus.data.days_with_data} / {syncStatus.data.total_days} 天
                    <span className="text-lg text-blue-700 ml-2">({syncStatus.data.coverage_percentage}%)</span>
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-sm font-medium text-gray-700 mb-1">日期范围</p>
                  <p className="text-base font-semibold text-gray-900">
                    {syncStatus.data.date_range.start} 至 {syncStatus.data.date_range.end}
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* 标签页 */}
        <div className="mb-6 border-b-2 border-gray-200">
          <div className="flex space-x-2">
            {[
              { id: 'data', label: '原始数据', icon: '📈' },
              { id: 'sleep', label: '睡眠分析', icon: '😴' },
              { id: 'heart', label: '心率分析', icon: '❤️' },
              { id: 'battery', label: '身体电量', icon: '🔋' },
              { id: 'activity', label: '活动分析', icon: '🏃' },
              { id: 'comprehensive', label: '综合分析', icon: '📊' },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={`px-5 py-3 border-b-3 transition-all font-semibold ${
                  activeTab === tab.id
                    ? 'border-blue-600 text-blue-700 bg-blue-50'
                    : 'border-transparent text-gray-700 hover:text-gray-900 hover:bg-gray-50'
                }`}
              >
                <span className="mr-2">{tab.icon}</span>
                {tab.label}
              </button>
            ))}
          </div>
        </div>

        {/* 原始数据视图 */}
        {activeTab === 'data' && (
          <div className="space-y-6">
            <div className="bg-white p-6 rounded-xl shadow-lg border border-gray-200">
              <h2 className="text-2xl font-bold mb-6 text-gray-900">数据趋势图</h2>
              <ResponsiveContainer width="100%" height={400}>
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis 
                    dataKey="date" 
                    stroke="#6b7280"
                    style={{ fontSize: '12px', fontWeight: 500 }}
                  />
                  <YAxis 
                    yAxisId="left" 
                    stroke="#6b7280"
                    style={{ fontSize: '12px', fontWeight: 500 }}
                  />
                  <YAxis 
                    yAxisId="right" 
                    orientation="right"
                    stroke="#6b7280"
                    style={{ fontSize: '12px', fontWeight: 500 }}
                  />
                  <Tooltip 
                    contentStyle={{ 
                      backgroundColor: 'white', 
                      border: '2px solid #e5e7eb',
                      borderRadius: '8px',
                      fontSize: '14px',
                      fontWeight: 500
                    }}
                  />
                  <Legend 
                    wrapperStyle={{ fontSize: '14px', fontWeight: 600 }}
                  />
                  <Line
                    yAxisId="left"
                    type="monotone"
                    dataKey="sleepScore"
                    stroke="#6366f1"
                    strokeWidth={3}
                    dot={{ fill: '#6366f1', r: 4 }}
                    name="睡眠分数"
                  />
                  <Line
                    yAxisId="left"
                    type="monotone"
                    dataKey="avgHeartRate"
                    stroke="#10b981"
                    strokeWidth={3}
                    dot={{ fill: '#10b981', r: 4 }}
                    name="平均心率"
                  />
                  <Line
                    yAxisId="left"
                    type="monotone"
                    dataKey="hrv"
                    stroke="#ec4899"
                    strokeWidth={3}
                    strokeDasharray="5 5"
                    dot={{ fill: '#ec4899', r: 4 }}
                    name="HRV (ms)"
                  />
                  <Line
                    yAxisId="right"
                    type="monotone"
                    dataKey="steps"
                    stroke="#f59e0b"
                    strokeWidth={3}
                    dot={{ fill: '#f59e0b', r: 4 }}
                    name="步数"
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>

            <div className="bg-white p-6 rounded-xl shadow-lg border border-gray-200">
              <h2 className="text-2xl font-bold mb-6 text-gray-900">步数统计</h2>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis 
                    dataKey="date" 
                    stroke="#6b7280"
                    style={{ fontSize: '12px', fontWeight: 500 }}
                  />
                  <YAxis 
                    stroke="#6b7280"
                    style={{ fontSize: '12px', fontWeight: 500 }}
                  />
                  <Tooltip 
                    contentStyle={{ 
                      backgroundColor: 'white', 
                      border: '2px solid #e5e7eb',
                      borderRadius: '8px',
                      fontSize: '14px',
                      fontWeight: 500
                    }}
                  />
                  <Legend 
                    wrapperStyle={{ fontSize: '14px', fontWeight: 600 }}
                  />
                  <Bar dataKey="steps" fill="#6366f1" name="步数" radius={[8, 8, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>

            <div className="bg-white p-6 rounded-xl shadow-lg border border-gray-200">
              <h2 className="text-2xl font-bold mb-6 text-gray-900">睡眠阶段分解</h2>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis 
                    dataKey="date" 
                    stroke="#6b7280"
                    style={{ fontSize: '12px', fontWeight: 500 }}
                  />
                  <YAxis 
                    stroke="#6b7280"
                    style={{ fontSize: '12px', fontWeight: 500 }}
                    label={{ value: '时长 (小时)', angle: -90, position: 'insideLeft', style: { fontSize: '12px', fontWeight: 600 } }}
                  />
                  <Tooltip 
                    contentStyle={{ 
                      backgroundColor: 'white', 
                      border: '2px solid #e5e7eb',
                      borderRadius: '8px',
                      fontSize: '14px',
                      fontWeight: 500
                    }}
                    formatter={(value: any) => value ? `${value}小时` : '-'}
                  />
                  <Legend 
                    wrapperStyle={{ fontSize: '14px', fontWeight: 600 }}
                  />
                  <Bar dataKey="deepSleep" stackId="sleep" fill="#8b5cf6" name="深睡" radius={[0, 0, 0, 0]} />
                  <Bar dataKey="remSleep" stackId="sleep" fill="#6366f1" name="快速眼动" radius={[0, 0, 0, 0]} />
                  <Bar dataKey="awake" stackId="sleep" fill="#f59e0b" name="清醒" radius={[8, 8, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
              <div className="mt-4 text-sm text-gray-600">
                <p className="font-semibold mb-2">睡眠阶段说明：</p>
                <ul className="space-y-1">
                  <li>• <span className="text-purple-700 font-medium">深睡</span>：深度恢复阶段，占总睡眠15-20%为佳</li>
                  <li>• <span className="text-indigo-700 font-medium">快速眼动</span>：记忆巩固阶段，占总睡眠20-25%为佳</li>
                  <li>• <span className="text-orange-700 font-medium">清醒</span>：夜间醒来时间，越少越好</li>
                </ul>
              </div>
            </div>

            <div className="bg-white p-6 rounded-xl shadow-lg border border-gray-200">
              <h2 className="text-2xl font-bold mb-6 text-gray-900">心率变异性 (HRV) 趋势</h2>
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis 
                    dataKey="date" 
                    stroke="#6b7280"
                    style={{ fontSize: '12px', fontWeight: 500 }}
                  />
                  <YAxis 
                    stroke="#6b7280"
                    style={{ fontSize: '12px', fontWeight: 500 }}
                    label={{ value: 'HRV (ms)', angle: -90, position: 'insideLeft', style: { fontSize: '12px', fontWeight: 600 } }}
                  />
                  <Tooltip 
                    contentStyle={{ 
                      backgroundColor: 'white', 
                      border: '2px solid #e5e7eb',
                      borderRadius: '8px',
                      fontSize: '14px',
                      fontWeight: 500
                    }}
                    formatter={(value: any) => value ? `${value.toFixed(1)} ms` : '-'}
                  />
                  <Legend 
                    wrapperStyle={{ fontSize: '14px', fontWeight: 600 }}
                  />
                  <Line 
                    type="monotone" 
                    dataKey="hrv" 
                    stroke="#ec4899" 
                    strokeWidth={3}
                    dot={{ fill: '#ec4899', r: 5 }}
                    name="HRV (ms)"
                  />
                  {/* 参考线：HRV 正常范围 */}
                  <Line 
                    type="monotone" 
                    dataKey={() => 30} 
                    stroke="#94a3b8" 
                    strokeWidth={1}
                    strokeDasharray="5 5"
                    dot={false}
                    name="正常下限 (30ms)"
                    legendType="none"
                  />
                  <Line 
                    type="monotone" 
                    dataKey={() => 50} 
                    stroke="#10b981" 
                    strokeWidth={1}
                    strokeDasharray="5 5"
                    dot={false}
                    name="良好阈值 (50ms)"
                    legendType="none"
                  />
                </LineChart>
              </ResponsiveContainer>
              <div className="mt-4 text-sm text-gray-600">
                <p className="font-semibold mb-2">HRV 参考值：</p>
                <ul className="space-y-1">
                  <li>• <span className="text-green-700 font-medium">≥50ms</span>：优秀，恢复状态良好</li>
                  <li>• <span className="text-blue-700 font-medium">30-50ms</span>：正常范围</li>
                  <li>• <span className="text-orange-700 font-medium">&lt;30ms</span>：偏低，建议关注恢复</li>
                </ul>
              </div>
            </div>

            {/* 压力趋势图 */}
            <div className="bg-white p-6 rounded-xl shadow-lg border border-gray-200">
              <h2 className="text-2xl font-bold mb-6 text-gray-900">压力水平趋势</h2>
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis 
                    dataKey="date" 
                    stroke="#6b7280"
                    style={{ fontSize: '12px', fontWeight: 500 }}
                  />
                  <YAxis 
                    stroke="#6b7280"
                    style={{ fontSize: '12px', fontWeight: 500 }}
                    label={{ value: '压力水平', angle: -90, position: 'insideLeft', style: { fontSize: '12px', fontWeight: 600 } }}
                    domain={[0, 100]}
                  />
                  <Tooltip 
                    contentStyle={{ 
                      backgroundColor: 'white', 
                      border: '2px solid #e5e7eb',
                      borderRadius: '8px',
                      fontSize: '14px',
                      fontWeight: 500
                    }}
                    formatter={(value: any) => value ? `${value}` : '-'}
                  />
                  <Legend 
                    wrapperStyle={{ fontSize: '14px', fontWeight: 600 }}
                  />
                  <Line 
                    type="monotone" 
                    dataKey="stressLevel" 
                    stroke="#ef4444" 
                    strokeWidth={3}
                    dot={{ fill: '#ef4444', r: 5 }}
                    name="压力水平"
                  />
                  {/* 参考线：压力水平阈值 */}
                  <Line 
                    type="monotone" 
                    dataKey={() => 30} 
                    stroke="#10b981" 
                    strokeWidth={1}
                    strokeDasharray="5 5"
                    dot={false}
                    name="低压力 (30)"
                    legendType="none"
                  />
                  <Line 
                    type="monotone" 
                    dataKey={() => 50} 
                    stroke="#f59e0b" 
                    strokeWidth={1}
                    strokeDasharray="5 5"
                    dot={false}
                    name="中等压力 (50)"
                    legendType="none"
                  />
                  <Line 
                    type="monotone" 
                    dataKey={() => 70} 
                    stroke="#ef4444" 
                    strokeWidth={1}
                    strokeDasharray="5 5"
                    dot={false}
                    name="高压力 (70)"
                    legendType="none"
                  />
                </LineChart>
              </ResponsiveContainer>
              <div className="mt-4 text-sm text-gray-600">
                <p className="font-semibold mb-2">压力水平参考值：</p>
                <ul className="space-y-1">
                  <li>• <span className="text-green-700 font-medium">0-30</span>：低压力，放松状态</li>
                  <li>• <span className="text-yellow-700 font-medium">30-50</span>：中等压力，正常范围</li>
                  <li>• <span className="text-orange-700 font-medium">50-70</span>：较高压力，建议关注</li>
                  <li>• <span className="text-red-700 font-medium">70-100</span>：高压力，需要休息和放松</li>
                </ul>
              </div>
            </div>

            {/* 数据表格 - 分页 */}
            <div className="bg-white p-6 rounded-xl shadow-lg border border-gray-200">
              <div className="flex justify-between items-center mb-6">
                <h2 className="text-2xl font-bold text-gray-900">详细数据列表</h2>
                {garminData?.data && garminData.data.length > 0 && (
                  <div className="text-sm font-semibold text-gray-700 bg-gray-100 px-3 py-1.5 rounded-lg">
                    共 {garminData.data.length} 条记录
                  </div>
                )}
              </div>
              
              <div className="overflow-x-auto border border-gray-200 rounded-lg">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gradient-to-r from-gray-100 to-gray-50">
                    <tr>
                      <th className="px-5 py-4 text-left text-xs font-bold text-gray-700 uppercase tracking-wider border-r border-gray-200">日期</th>
                      <th className="px-5 py-4 text-left text-xs font-bold text-gray-700 uppercase tracking-wider border-r border-gray-200">睡眠分数</th>
                      <th className="px-5 py-4 text-left text-xs font-bold text-gray-700 uppercase tracking-wider border-r border-gray-200">深睡</th>
                      <th className="px-5 py-4 text-left text-xs font-bold text-gray-700 uppercase tracking-wider border-r border-gray-200">快速眼动</th>
                      <th className="px-5 py-4 text-left text-xs font-bold text-gray-700 uppercase tracking-wider border-r border-gray-200">清醒</th>
                      <th className="px-5 py-4 text-left text-xs font-bold text-gray-700 uppercase tracking-wider border-r border-gray-200">睡眠时长</th>
                      <th className="px-5 py-4 text-left text-xs font-bold text-gray-700 uppercase tracking-wider border-r border-gray-200">小睡</th>
                      <th className="px-5 py-4 text-left text-xs font-bold text-gray-700 uppercase tracking-wider border-r border-gray-200">平均心率</th>
                      <th className="px-5 py-4 text-left text-xs font-bold text-gray-700 uppercase tracking-wider border-r border-gray-200">静息心率</th>
                      <th className="px-5 py-4 text-left text-xs font-bold text-gray-700 uppercase tracking-wider border-r border-gray-200">HRV</th>
                      <th className="px-5 py-4 text-left text-xs font-bold text-gray-700 uppercase tracking-wider border-r border-gray-200">步数</th>
                      <th className="px-5 py-4 text-left text-xs font-bold text-gray-700 uppercase tracking-wider border-r border-gray-200">活动分钟</th>
                      <th className="px-5 py-4 text-left text-xs font-bold text-gray-700 uppercase tracking-wider border-r border-gray-200">身体电量</th>
                      <th className="px-5 py-4 text-left text-xs font-bold text-gray-700 uppercase tracking-wider">压力</th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-200">
                    {garminData?.data
                      ?.slice((currentPage - 1) * pageSize, currentPage * pageSize)
                      .map((item: any) => (
                      <tr key={item.id} className="hover:bg-blue-50 transition-colors">
                        <td className="px-5 py-4 whitespace-nowrap text-sm font-semibold text-gray-900 border-r border-gray-100">
                          {format(new Date(item.record_date), 'yyyy-MM-dd')}
                        </td>
                        <td className="px-5 py-4 whitespace-nowrap text-sm border-r border-gray-100">
                          <span className={`px-3 py-1.5 rounded-lg font-semibold ${
                            item.sleep_score >= 85 ? 'bg-green-100 text-green-800' :
                            item.sleep_score >= 70 ? 'bg-blue-100 text-blue-800' :
                            item.sleep_score >= 50 ? 'bg-yellow-100 text-yellow-800' :
                            item.sleep_score ? 'bg-red-100 text-red-800' : 'bg-gray-100 text-gray-600'
                          }`}>
                            {item.sleep_score || '-'}
                          </span>
                        </td>
                        <td className="px-5 py-4 whitespace-nowrap text-sm border-r border-gray-100">
                          <span className="font-semibold text-purple-700">
                            {item.deep_sleep_duration !== null && item.deep_sleep_duration !== undefined ? 
                              (item.deep_sleep_duration >= 60 ? 
                                `${Math.floor(item.deep_sleep_duration / 60)}h${item.deep_sleep_duration % 60}m` : 
                                `${item.deep_sleep_duration}m`) : 
                              '-'}
                          </span>
                        </td>
                        <td className="px-5 py-4 whitespace-nowrap text-sm border-r border-gray-100">
                          <span className="font-semibold text-indigo-700">
                            {item.rem_sleep_duration !== null && item.rem_sleep_duration !== undefined ? 
                              (item.rem_sleep_duration >= 60 ? 
                                `${Math.floor(item.rem_sleep_duration / 60)}h${item.rem_sleep_duration % 60}m` : 
                                `${item.rem_sleep_duration}m`) : 
                              '-'}
                          </span>
                        </td>
                        <td className="px-5 py-4 whitespace-nowrap text-sm border-r border-gray-100">
                          <span className="font-semibold text-orange-700">
                            {item.awake_duration !== null && item.awake_duration !== undefined ? 
                              (item.awake_duration >= 60 ? 
                                `${Math.floor(item.awake_duration / 60)}h${item.awake_duration % 60}m` : 
                                `${item.awake_duration}m`) : 
                              '-'}
                          </span>
                        </td>
                        <td className="px-5 py-4 whitespace-nowrap text-sm text-gray-900 font-medium border-r border-gray-100">
                          {item.total_sleep_duration ? `${Math.floor(item.total_sleep_duration / 60)}h${item.total_sleep_duration % 60}m` : '-'}
                        </td>
                        <td className="px-5 py-4 whitespace-nowrap text-sm border-r border-gray-100">
                          <span className="font-semibold text-teal-700">
                            {item.nap_duration !== null && item.nap_duration !== undefined ? 
                              (item.nap_duration >= 60 ? 
                                `${Math.floor(item.nap_duration / 60)}h${item.nap_duration % 60}m` : 
                                `${item.nap_duration}m`) : 
                              '-'}
                          </span>
                        </td>
                        <td className="px-5 py-4 whitespace-nowrap text-sm text-gray-900 font-medium border-r border-gray-100">
                          {item.avg_heart_rate || '-'}
                        </td>
                        <td className="px-5 py-4 whitespace-nowrap text-sm border-r border-gray-100">
                          <span className={`font-semibold ${
                            item.resting_heart_rate && item.resting_heart_rate < 60 ? 'text-green-700' :
                            item.resting_heart_rate && item.resting_heart_rate > 80 ? 'text-red-700' : 'text-gray-900'
                          }`}>
                            {item.resting_heart_rate || '-'}
                          </span>
                        </td>
                        <td className="px-5 py-4 whitespace-nowrap text-sm border-r border-gray-100">
                          <span className={`font-semibold ${
                            item.hrv && item.hrv >= 50 ? 'text-green-700' :
                            item.hrv && item.hrv >= 30 ? 'text-blue-700' :
                            item.hrv && item.hrv < 30 ? 'text-orange-700' : 'text-gray-900'
                          }`}>
                            {item.hrv ? `${item.hrv.toFixed(1)} ms` : '-'}
                          </span>
                        </td>
                        <td className="px-5 py-4 whitespace-nowrap text-sm border-r border-gray-100">
                          <span className={`font-semibold ${
                            item.steps >= 10000 ? 'text-green-700' :
                            item.steps >= 7000 ? 'text-blue-700' :
                            item.steps < 5000 && item.steps ? 'text-orange-700' : 'text-gray-900'
                          }`}>
                            {item.steps?.toLocaleString() || '-'}
                          </span>
                        </td>
                        <td className="px-5 py-4 whitespace-nowrap text-sm text-gray-900 font-medium border-r border-gray-100">
                          {item.active_minutes || '-'}
                        </td>
                        <td className="px-5 py-4 whitespace-nowrap text-sm text-gray-900 font-medium border-r border-gray-100">
                          {item.body_battery_charged || '-'}
                        </td>
                        <td className="px-5 py-4 whitespace-nowrap text-sm border-r border-gray-100">
                          <span className={`font-semibold ${
                            item.stress_level === null || item.stress_level === undefined ? 'text-gray-500' :
                            item.stress_level >= 70 ? 'text-red-700' :
                            item.stress_level >= 50 ? 'text-orange-700' :
                            item.stress_level >= 30 ? 'text-yellow-700' :
                            'text-green-700'
                          }`}>
                            {item.stress_level !== null && item.stress_level !== undefined ? item.stress_level : '-'}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              
              {/* 分页控件 */}
              {garminData?.data && garminData.data.length > pageSize && (
                <div className="mt-6 flex items-center justify-between border-t-2 border-gray-200 pt-5">
                  <div className="text-sm font-semibold text-gray-700">
                    显示第 <span className="text-blue-700">{(currentPage - 1) * pageSize + 1}</span> - <span className="text-blue-700">{Math.min(currentPage * pageSize, garminData.data.length)}</span> 条，
                    共 <span className="text-gray-900">{garminData.data.length}</span> 条
                  </div>
                  
                  <div className="flex items-center gap-2">
                    {/* 首页 */}
                    <button
                      onClick={() => setCurrentPage(1)}
                      disabled={currentPage === 1}
                      className="px-4 py-2 text-sm font-semibold border-2 border-gray-300 rounded-lg hover:bg-gray-100 hover:border-gray-400 disabled:opacity-40 disabled:cursor-not-allowed text-gray-700 transition-colors"
                    >
                      首页
                    </button>
                    
                    {/* 上一页 */}
                    <button
                      onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
                      disabled={currentPage === 1}
                      className="px-4 py-2 text-sm font-semibold border-2 border-gray-300 rounded-lg hover:bg-gray-100 hover:border-gray-400 disabled:opacity-40 disabled:cursor-not-allowed text-gray-700 transition-colors"
                    >
                      上一页
                    </button>
                    
                    {/* 页码 */}
                    <div className="flex items-center gap-1">
                      {(() => {
                        const totalPages = Math.ceil(garminData.data.length / pageSize);
                        const pages: (number | string)[] = [];
                        
                        if (totalPages <= 7) {
                          for (let i = 1; i <= totalPages; i++) pages.push(i);
                        } else {
                          pages.push(1);
                          if (currentPage > 3) pages.push('...');
                          
                          const start = Math.max(2, currentPage - 1);
                          const end = Math.min(totalPages - 1, currentPage + 1);
                          
                          for (let i = start; i <= end; i++) pages.push(i);
                          
                          if (currentPage < totalPages - 2) pages.push('...');
                          pages.push(totalPages);
                        }
                        
                        return pages.map((page, idx) => (
                          typeof page === 'number' ? (
                            <button
                              key={idx}
                              onClick={() => setCurrentPage(page)}
                              className={`px-4 py-2 text-sm font-bold border-2 rounded-lg transition-colors ${
                                currentPage === page
                                  ? 'bg-blue-600 text-white border-blue-600 shadow-md'
                                  : 'border-gray-300 text-gray-700 hover:bg-gray-100 hover:border-gray-400'
                              }`}
                            >
                              {page}
                            </button>
                          ) : (
                            <span key={idx} className="px-2 text-gray-500 font-semibold">...</span>
                          )
                        ));
                      })()}
                    </div>
                    
                    {/* 下一页 */}
                    <button
                      onClick={() => setCurrentPage(prev => Math.min(Math.ceil(garminData.data.length / pageSize), prev + 1))}
                      disabled={currentPage >= Math.ceil(garminData.data.length / pageSize)}
                      className="px-4 py-2 text-sm font-semibold border-2 border-gray-300 rounded-lg hover:bg-gray-100 hover:border-gray-400 disabled:opacity-40 disabled:cursor-not-allowed text-gray-700 transition-colors"
                    >
                      下一页
                    </button>
                    
                    {/* 末页 */}
                    <button
                      onClick={() => setCurrentPage(Math.ceil(garminData.data.length / pageSize))}
                      disabled={currentPage >= Math.ceil(garminData.data.length / pageSize)}
                      className="px-4 py-2 text-sm font-semibold border-2 border-gray-300 rounded-lg hover:bg-gray-100 hover:border-gray-400 disabled:opacity-40 disabled:cursor-not-allowed text-gray-700 transition-colors"
                    >
                      末页
                    </button>
                    
                    {/* 跳转 */}
                    <div className="flex items-center gap-2 ml-4 pl-4 border-l-2 border-gray-200">
                      <span className="text-sm font-semibold text-gray-700">跳至</span>
                      <input
                        type="number"
                        min={1}
                        max={Math.ceil(garminData.data.length / pageSize)}
                        value={currentPage}
                        onChange={(e) => {
                          const page = parseInt(e.target.value);
                          if (page >= 1 && page <= Math.ceil(garminData.data.length / pageSize)) {
                            setCurrentPage(page);
                          }
                        }}
                        className="w-16 px-2 py-1.5 text-sm font-semibold border-2 border-gray-300 rounded-lg text-center text-gray-900 focus:border-blue-500 focus:outline-none"
                      />
                      <span className="text-sm font-semibold text-gray-700">页</span>
                    </div>
                  </div>
                </div>
              )}
              
              {(!garminData?.data || garminData.data.length === 0) && (
                <div className="text-center py-8 text-gray-500">
                  暂无数据，请先同步Garmin数据
                </div>
              )}
            </div>
          </div>
        )}

        {/* 睡眠分析 */}
        {activeTab === 'sleep' && sleepAnalysis?.data && (
          <div className="space-y-6">
            <div className="bg-white p-6 rounded-xl shadow-lg border border-gray-200">
              <h2 className="text-2xl font-bold mb-6 text-gray-900">睡眠质量分析</h2>
              {sleepAnalysis.data.status === 'success' ? (
                <div className="space-y-6">
                  <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                    <div className="p-5 bg-blue-50 rounded-xl border-2 border-blue-200">
                      <p className="text-sm font-semibold text-gray-700 mb-2">平均睡眠分数</p>
                      <p className="text-3xl font-bold text-blue-700">{sleepAnalysis.data.average_sleep_score}</p>
                    </div>
                    <div className="p-5 bg-green-50 rounded-xl border-2 border-green-200">
                      <p className="text-sm font-semibold text-gray-700 mb-2">平均睡眠时长</p>
                      <p className="text-3xl font-bold text-green-700">{sleepAnalysis.data.average_sleep_duration_hours?.toFixed(1)}h</p>
                    </div>
                    <div className="p-5 bg-purple-50 rounded-xl border-2 border-purple-200">
                      <p className="text-sm font-semibold text-gray-700 mb-2">深度睡眠</p>
                      <p className="text-3xl font-bold text-purple-700">{sleepAnalysis.data.average_deep_sleep_minutes?.toFixed(0)}m</p>
                    </div>
                    <div className="p-5 bg-yellow-50 rounded-xl border-2 border-yellow-200">
                      <p className="text-sm font-semibold text-gray-700 mb-2">REM睡眠</p>
                      <p className="text-3xl font-bold text-yellow-700">{sleepAnalysis.data.average_rem_sleep_minutes?.toFixed(0)}m</p>
                    </div>
                    <div className="p-5 bg-orange-50 rounded-xl border-2 border-orange-200">
                      <p className="text-sm font-semibold text-gray-700 mb-2">清醒时间</p>
                      <p className="text-3xl font-bold text-orange-700">{sleepAnalysis.data.average_awake_minutes?.toFixed(0)}m</p>
                    </div>
                  </div>
                  
                  {/* 深度睡眠趋势图 */}
                  {sleepAnalysis.data.daily_data && sleepAnalysis.data.daily_data.length > 0 && (
                    <div className="mt-6 bg-white p-6 rounded-xl border-2 border-gray-200">
                      <h3 className="text-xl font-bold mb-4 text-gray-900">深度睡眠趋势</h3>
                      <ResponsiveContainer width="100%" height={300}>
                        <LineChart 
                          data={sleepAnalysis.data.daily_data
                            .slice()
                            .sort((a: any, b: any) => new Date(a.date).getTime() - new Date(b.date).getTime())
                            .map((item: any) => ({
                              date: format(new Date(item.date), 'MM-dd'),
                              deepSleep: item.deep_sleep_duration ? Math.floor(item.deep_sleep_duration / 60) : null,
                              remSleep: item.rem_sleep_duration ? Math.floor(item.rem_sleep_duration / 60) : null,
                              awake: item.awake_duration ? Math.floor(item.awake_duration / 60) : null,
                            }))}
                        >
                          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                          <XAxis 
                            dataKey="date" 
                            stroke="#6b7280"
                            style={{ fontSize: '12px', fontWeight: 500 }}
                          />
                          <YAxis 
                            stroke="#6b7280"
                            style={{ fontSize: '12px', fontWeight: 500 }}
                            label={{ value: '时长 (小时)', angle: -90, position: 'insideLeft', style: { fontSize: '12px', fontWeight: 600 } }}
                          />
                          <Tooltip 
                            contentStyle={{ 
                              backgroundColor: 'white', 
                              border: '2px solid #e5e7eb',
                              borderRadius: '8px',
                              fontSize: '14px',
                              fontWeight: 500
                            }}
                            formatter={(value: any) => value ? `${value}小时` : '-'}
                          />
                          <Legend 
                            wrapperStyle={{ fontSize: '14px', fontWeight: 600 }}
                          />
                          <Line
                            type="monotone"
                            dataKey="deepSleep"
                            stroke="#8b5cf6"
                            strokeWidth={3}
                            dot={{ fill: '#8b5cf6', r: 5 }}
                            name="深度睡眠"
                          />
                          <Line
                            type="monotone"
                            dataKey="remSleep"
                            stroke="#6366f1"
                            strokeWidth={3}
                            dot={{ fill: '#6366f1', r: 5 }}
                            name="快速眼动"
                          />
                          <Line
                            type="monotone"
                            dataKey="awake"
                            stroke="#f59e0b"
                            strokeWidth={2}
                            strokeDasharray="5 5"
                            dot={{ fill: '#f59e0b', r: 4 }}
                            name="清醒时间"
                          />
                        </LineChart>
                      </ResponsiveContainer>
                      
                      {/* 深度睡眠解读 */}
                      <div className="mt-6 p-4 bg-purple-50 rounded-lg border border-purple-200">
                        <h4 className="text-lg font-bold mb-3 text-purple-900">深度睡眠解读</h4>
                        <div className="space-y-2 text-gray-800">
                          <p className="font-medium">
                            <span className="text-purple-700 font-bold">平均深度睡眠：{sleepAnalysis.data.average_deep_sleep_minutes?.toFixed(0)}分钟</span>
                          </p>
                          {sleepAnalysis.data.average_deep_sleep_minutes && (
                            <div className="text-sm leading-6">
                              {sleepAnalysis.data.average_deep_sleep_minutes >= 90 ? (
                                <p className="text-green-700 font-semibold">✅ 优秀：深度睡眠充足，有助于身体恢复和免疫系统功能。</p>
                              ) : sleepAnalysis.data.average_deep_sleep_minutes >= 60 ? (
                                <p className="text-blue-700 font-semibold">👍 良好：深度睡眠在正常范围内，继续保持。</p>
                              ) : (
                                <p className="text-orange-700 font-semibold">⚠️ 不足：深度睡眠偏少，建议改善睡眠环境，避免睡前使用电子设备。</p>
                              )}
                              <p className="mt-2 text-gray-700">
                                深度睡眠是睡眠周期中最关键的阶段，占总睡眠的15-20%为佳。它有助于：
                              </p>
                              <ul className="list-disc list-inside ml-2 mt-1 text-gray-600">
                                <li>身体修复和肌肉恢复</li>
                                <li>增强免疫系统</li>
                                <li>促进生长激素分泌</li>
                                <li>巩固记忆和学习能力</li>
                              </ul>
                            </div>
                          )}
                        </div>
                      </div>

                      {/* 清醒时间解读 */}
                      {sleepAnalysis.data.average_awake_minutes && (
                        <div className="mt-4 p-4 bg-orange-50 rounded-lg border border-orange-200">
                          <h4 className="text-lg font-bold mb-3 text-orange-900">清醒时间解读</h4>
                          <div className="space-y-2 text-gray-800">
                            <p className="font-medium">
                              <span className="text-orange-700 font-bold">平均清醒时间：{sleepAnalysis.data.average_awake_minutes?.toFixed(0)}分钟</span>
                            </p>
                            <div className="text-sm leading-6">
                              {sleepAnalysis.data.average_awake_minutes <= 30 ? (
                                <p className="text-green-700 font-semibold">✅ 优秀：夜间清醒时间很少，睡眠连续性良好。</p>
                              ) : sleepAnalysis.data.average_awake_minutes <= 60 ? (
                                <p className="text-blue-700 font-semibold">👍 正常：清醒时间在可接受范围内。</p>
                              ) : (
                                <p className="text-red-700 font-semibold">⚠️ 偏多：夜间清醒时间较长，可能影响睡眠质量。建议检查睡眠环境、避免睡前摄入咖啡因或酒精。</p>
                              )}
                              <p className="mt-2 text-gray-700">
                                夜间清醒时间越少越好，理想情况下应少于30分钟。过多的清醒时间可能由以下因素引起：
                              </p>
                              <ul className="list-disc list-inside ml-2 mt-1 text-gray-600">
                                <li>睡眠环境不适（温度、光线、噪音）</li>
                                <li>睡前摄入咖啡因或酒精</li>
                                <li>压力或焦虑</li>
                                <li>不规律的作息时间</li>
                              </ul>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  <div className="mt-6 p-4 bg-gray-50 rounded-xl border border-gray-200">
                    <h3 className="text-lg font-bold mb-3 text-gray-900">质量评估</h3>
                    <p className="text-lg font-semibold text-gray-900">
                      {sleepAnalysis.data.quality_assessment?.overall === 'excellent' && '✅ 优秀'}
                      {sleepAnalysis.data.quality_assessment?.overall === 'good' && '👍 良好'}
                      {sleepAnalysis.data.quality_assessment?.overall === 'fair' && '⚠️ 一般'}
                      {sleepAnalysis.data.quality_assessment?.overall === 'poor' && '❌ 较差'}
                    </p>
                  </div>

                  {sleepAnalysis.data.recommendations && (
                    <div className="mt-6 p-5 bg-blue-50 rounded-xl border-2 border-blue-200">
                      <h3 className="text-lg font-bold mb-3 text-blue-900">建议</h3>
                      <ul className="list-disc list-inside space-y-2">
                        {sleepAnalysis.data.recommendations.map((rec: string, idx: number) => (
                          <li key={idx} className="text-gray-900 font-medium leading-7">{rec}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              ) : (
                <p className="text-gray-700 font-medium">{sleepAnalysis.data.message}</p>
              )}
            </div>
          </div>
        )}

        {/* 心率分析 */}
        {activeTab === 'heart' && heartAnalysis?.data && (
          <div className="bg-white p-6 rounded-xl shadow-lg border border-gray-200">
            <h2 className="text-2xl font-bold mb-6 text-gray-900">心率分析</h2>
            {heartAnalysis.data.status === 'success' ? (
              <div className="space-y-6">
                <div className="grid grid-cols-3 gap-4">
                  <div className="p-5 bg-red-50 rounded-xl border-2 border-red-200">
                    <p className="text-sm font-semibold text-gray-700 mb-2">平均心率</p>
                    <p className="text-3xl font-bold text-red-700">{heartAnalysis.data.average_heart_rate?.toFixed(0)} bpm</p>
                  </div>
                  <div className="p-5 bg-blue-50 rounded-xl border-2 border-blue-200">
                    <p className="text-sm font-semibold text-gray-700 mb-2">静息心率</p>
                    <p className="text-3xl font-bold text-blue-700">{heartAnalysis.data.average_resting_heart_rate?.toFixed(0)} bpm</p>
                  </div>
                  <div className="p-5 bg-green-50 rounded-xl border-2 border-green-200">
                    <p className="text-sm font-semibold text-gray-700 mb-2">HRV</p>
                    <p className="text-3xl font-bold text-green-700">{heartAnalysis.data.average_hrv?.toFixed(1)} ms</p>
                  </div>
                </div>
                {heartAnalysis.data.recommendations && (
                  <div className="mt-6 p-5 bg-red-50 rounded-xl border-2 border-red-200">
                    <h3 className="text-lg font-bold mb-3 text-red-900">建议</h3>
                    <ul className="list-disc list-inside space-y-2">
                      {heartAnalysis.data.recommendations.map((rec: string, idx: number) => (
                        <li key={idx} className="text-gray-900 font-medium leading-7">{rec}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ) : (
              <p className="text-gray-700 font-medium">{heartAnalysis.data.message}</p>
            )}
          </div>
        )}

        {/* 身体电量分析 */}
        {activeTab === 'battery' && batteryAnalysis?.data && (
          <div className="bg-white p-6 rounded-xl shadow-lg border border-gray-200">
            <h2 className="text-2xl font-bold mb-6 text-gray-900">身体电量分析</h2>
            {batteryAnalysis.data.status === 'success' ? (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="p-5 bg-yellow-50 rounded-xl border-2 border-yellow-200">
                  <p className="text-sm font-semibold text-gray-700 mb-2">平均充电值</p>
                  <p className="text-3xl font-bold text-yellow-700">{batteryAnalysis.data.average_charged?.toFixed(0)}</p>
                </div>
                <div className="p-5 bg-orange-50 rounded-xl border-2 border-orange-200">
                  <p className="text-sm font-semibold text-gray-700 mb-2">平均消耗值</p>
                  <p className="text-3xl font-bold text-orange-700">{batteryAnalysis.data.average_drained?.toFixed(0)}</p>
                </div>
                <div className="p-5 bg-green-50 rounded-xl border-2 border-green-200">
                  <p className="text-sm font-semibold text-gray-700 mb-2">最高值</p>
                  <p className="text-3xl font-bold text-green-700">{batteryAnalysis.data.average_most_charged?.toFixed(0)}</p>
                </div>
                <div className="p-5 bg-red-50 rounded-xl border-2 border-red-200">
                  <p className="text-sm font-semibold text-gray-700 mb-2">最低值</p>
                  <p className="text-3xl font-bold text-red-700">{batteryAnalysis.data.average_lowest?.toFixed(0)}</p>
                </div>
              </div>
            ) : (
              <p className="text-gray-700 font-medium">{batteryAnalysis.data.message}</p>
            )}
          </div>
        )}

        {/* 活动分析 */}
        {activeTab === 'activity' && activityAnalysis?.data && (
          <div className="bg-white p-6 rounded-xl shadow-lg border border-gray-200">
            <h2 className="text-2xl font-bold mb-6 text-gray-900">活动分析</h2>
            {activityAnalysis.data.status === 'success' ? (
              <div className="space-y-6">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="p-5 bg-blue-50 rounded-xl border-2 border-blue-200">
                    <p className="text-sm font-semibold text-gray-700 mb-2">平均步数/天</p>
                    <p className="text-3xl font-bold text-blue-700">{activityAnalysis.data.average_steps_per_day?.toLocaleString()}</p>
                  </div>
                  <div className="p-5 bg-green-50 rounded-xl border-2 border-green-200">
                    <p className="text-sm font-semibold text-gray-700 mb-2">总步数</p>
                    <p className="text-3xl font-bold text-green-700">{activityAnalysis.data.total_steps?.toLocaleString()}</p>
                  </div>
                  <div className="p-5 bg-purple-50 rounded-xl border-2 border-purple-200">
                    <p className="text-sm font-semibold text-gray-700 mb-2">平均活动分钟</p>
                    <p className="text-3xl font-bold text-purple-700">{activityAnalysis.data.average_active_minutes_per_day?.toFixed(0)}</p>
                  </div>
                  <div className="p-5 bg-yellow-50 rounded-xl border-2 border-yellow-200">
                    <p className="text-sm font-semibold text-gray-700 mb-2">符合WHO建议</p>
                    <p className="text-3xl font-bold text-yellow-700">
                      {activityAnalysis.data.assessment?.meets_who_recommendations ? '✅' : '❌'}
                    </p>
                  </div>
                </div>
              </div>
            ) : (
              <p className="text-gray-700 font-medium">{activityAnalysis.data.message}</p>
            )}
          </div>
        )}

        {/* 综合分析 */}
        {activeTab === 'comprehensive' && comprehensiveAnalysis?.data && (
          <div className="space-y-6">
            <div className="bg-white p-6 rounded-xl shadow-lg border border-gray-200">
              <h2 className="text-2xl font-bold mb-6 text-gray-900">综合分析报告</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* 睡眠 */}
                {comprehensiveAnalysis.data.sleep?.status === 'success' && (
                  <div className="p-5 bg-blue-50 rounded-xl border-2 border-blue-200">
                    <h3 className="text-lg font-bold mb-3 text-gray-900">睡眠质量</h3>
                    <p className="text-3xl font-bold text-blue-700">
                      {comprehensiveAnalysis.data.sleep.average_sleep_score?.toFixed(0)}/100
                    </p>
                    <p className="text-sm font-semibold text-gray-700 mt-2">
                      {comprehensiveAnalysis.data.sleep.average_sleep_duration_hours?.toFixed(1)} 小时/天
                    </p>
                  </div>
                )}

                {/* 心率 */}
                {comprehensiveAnalysis.data.heart_rate?.status === 'success' && (
                  <div className="p-5 bg-red-50 rounded-xl border-2 border-red-200">
                    <h3 className="text-lg font-bold mb-3 text-gray-900">心率健康</h3>
                    <p className="text-3xl font-bold text-red-700">
                      {comprehensiveAnalysis.data.heart_rate.average_resting_heart_rate?.toFixed(0)} bpm
                    </p>
                    <p className="text-sm font-semibold text-gray-700 mt-2">静息心率</p>
                  </div>
                )}

                {/* 活动 */}
                {comprehensiveAnalysis.data.activity?.status === 'success' && (
                  <div className="p-5 bg-green-50 rounded-xl border-2 border-green-200">
                    <h3 className="text-lg font-bold mb-3 text-gray-900">活动水平</h3>
                    <p className="text-3xl font-bold text-green-700">
                      {comprehensiveAnalysis.data.activity.average_steps_per_day?.toLocaleString()}
                    </p>
                    <p className="text-sm font-semibold text-gray-700 mt-2">平均步数/天</p>
                  </div>
                )}

                {/* 身体电量 */}
                {comprehensiveAnalysis.data.body_battery?.status === 'success' && (
                  <div className="p-5 bg-yellow-50 rounded-xl border-2 border-yellow-200">
                    <h3 className="text-lg font-bold mb-3 text-gray-900">身体电量</h3>
                    <p className="text-3xl font-bold text-yellow-700">
                      {comprehensiveAnalysis.data.body_battery.average_charged?.toFixed(0)}/100
                    </p>
                    <p className="text-sm font-semibold text-gray-700 mt-2">平均充电值</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}

// 导出受保护的页面
export default function GarminPage() {
  return (
    <ProtectedRoute>
      <GarminContent />
    </ProtectedRoute>
  );
}

