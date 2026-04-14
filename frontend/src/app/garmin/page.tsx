'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { dailyHealthApi, garminAnalysisApi, dataCollectionStatusApi } from '@/services/api';
import { format, subDays } from 'date-fns';
import DataChartsAndTable from './components/DataChartsAndTable';
import SleepAnalysisPanel from './components/SleepAnalysisPanel';
import { useAuth } from '@/contexts/AuthContext';
import ProtectedRoute from '@/components/ProtectedRoute';

function GarminContent() {
  const { user, isAuthenticated } = useAuth();
  const userId = user?.id;
  const [days, setDays] = useState(7);
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
      deepSleep: item.deep_sleep_duration ? Math.round(item.deep_sleep_duration / 60 * 10) / 10 : null,
      remSleep: item.rem_sleep_duration ? Math.round(item.rem_sleep_duration / 60 * 10) / 10 : null,
      lightSleep: item.light_sleep_duration ? Math.round(item.light_sleep_duration / 60 * 10) / 10 : null,
      awake: item.awake_duration ? Math.round(item.awake_duration / 60 * 10) / 10 : null,
      nap: item.nap_duration ? Math.floor(item.nap_duration / 60) : null,
      avgHeartRate: item.avg_heart_rate,
      hrv: item.hrv,
      steps: item.steps,
      bodyBattery: item.body_battery_most_charged ?? item.body_battery_charged,
      stressLevel: item.stress_level,
      respirationAwake: item.avg_respiration_awake,
      respirationSleep: item.avg_respiration_sleep,
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
              { id: 'comprehensive', label: '综合分析', icon: '🔍' },
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
          <DataChartsAndTable
            chartData={chartData}
            garminData={garminData}
            currentPage={currentPage}
            setCurrentPage={setCurrentPage}
            pageSize={pageSize}
          />
        )}

        {/* 睡眠分析 */}
        {activeTab === 'sleep' && sleepAnalysis?.data && (
          <SleepAnalysisPanel data={sleepAnalysis.data} />
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
                  <p className="text-sm font-semibold text-gray-700 mb-2">平均峰值</p>
                  <p className="text-3xl font-bold text-yellow-700">{batteryAnalysis.data.average_most_charged?.toFixed(0) ?? batteryAnalysis.data.average_charged?.toFixed(0)}</p>
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
                      {comprehensiveAnalysis.data.body_battery.average_most_charged?.toFixed(0) ?? comprehensiveAnalysis.data.body_battery.average_charged?.toFixed(0)}/100
                    </p>
                    <p className="text-sm font-semibold text-gray-700 mt-2">平均峰值</p>
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

