'use client';

import { DailyRecommendation } from '../types';

interface MetricCardsProps {
  currentData: DailyRecommendation;
  activeTab: 'one-day' | 'seven-day';
  sevenDayData: any;
}

export function MetricCards({ currentData, activeTab, sevenDayData }: MetricCardsProps) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
      <div className="bg-white rounded-xl shadow p-4">
        <div className="text-3xl mb-2">😴</div>
        <div className="text-sm text-gray-700 font-medium">睡眠分数</div>
        <div className="text-2xl font-bold text-indigo-600">
          {activeTab === 'seven-day' && sevenDayData?.averages?.sleep_score
            ? sevenDayData.averages.sleep_score
            : currentData?.raw_data?.sleep_score || '-'}
        </div>
        <div className="text-xs text-gray-600">
          {activeTab === 'seven-day' && sevenDayData?.averages?.sleep_duration_minutes
            ? `${(sevenDayData.averages.sleep_duration_minutes / 60).toFixed(1)}小时`
            : currentData?.raw_data?.sleep_duration_minutes
              ? `${(currentData.raw_data.sleep_duration_minutes / 60).toFixed(1)}小时`
              : '-'}
        </div>
      </div>

      <div className="bg-white rounded-xl shadow p-4">
        <div className="text-3xl mb-2">🚶</div>
        <div className="text-sm text-gray-700 font-medium">步数</div>
        <div className="text-2xl font-bold text-green-600">
          {activeTab === 'seven-day' && sevenDayData?.averages?.steps
            ? sevenDayData.averages.steps.toLocaleString()
            : currentData?.raw_data?.steps?.toLocaleString() || '-'}
        </div>
        <div className="text-xs text-gray-600">
          {currentData?.activity_analysis?.steps_goal_met ? '✅ 达标' : '🎯 继续加油'}
        </div>
      </div>

      <div className="bg-white rounded-xl shadow p-4">
        <div className="text-3xl mb-2">❤️</div>
        <div className="text-sm text-gray-700 font-medium">静息心率</div>
        <div className="text-2xl font-bold text-red-500">
          {activeTab === 'seven-day' && sevenDayData?.averages?.resting_heart_rate
            ? sevenDayData.averages.resting_heart_rate
            : currentData?.raw_data?.resting_heart_rate || '-'}
        </div>
        <div className="text-xs text-gray-600">bpm</div>
      </div>

      <div className="bg-white rounded-xl shadow p-4">
        <div className="text-3xl mb-2">🔋</div>
        <div className="text-sm text-gray-700 font-medium">身体电量</div>
        {(() => {
          const currentBattery = currentData?.raw_data?.body_battery_current;
          const peakBattery = activeTab === 'seven-day' && sevenDayData?.averages?.body_battery
            ? sevenDayData.averages.body_battery
            : currentData?.raw_data?.body_battery_highest;
          const lowestBattery = currentData?.raw_data?.body_battery_lowest;
          const displayBattery = currentBattery ?? peakBattery;
          const hasCurrent = currentBattery !== null && currentBattery !== undefined;

          const getBatteryColor = (value: number | null | undefined) => {
            if (value === null || value === undefined) return 'text-gray-400';
            if (value >= 80) return 'text-green-600';
            if (value >= 50) return 'text-yellow-600';
            return 'text-red-500';
          };

          const getBatteryStatus = (value: number | null | undefined) => {
            if (value === null || value === undefined) return '';
            if (value >= 80) return '充足';
            if (value >= 50) return '中等';
            return '偏低';
          };

          return (
            <>
              <div className={`text-2xl font-bold ${getBatteryColor(displayBattery)}`}>
                {displayBattery ?? '-'}
              </div>
              <div className="text-xs text-gray-600">
                {hasCurrent ? (
                  <span>当前 · {getBatteryStatus(currentBattery)}</span>
                ) : (
                  <span>{activeTab === 'seven-day' ? '7天平均' : '峰值'}</span>
                )}
              </div>
              {(peakBattery || lowestBattery) && activeTab === 'one-day' && (
                <div className="mt-1 text-xs space-y-0.5">
                  {hasCurrent && peakBattery && (
                    <div className="text-gray-500">📈 峰值 <span className="text-green-600 font-medium">{peakBattery}</span></div>
                  )}
                  {lowestBattery && (
                    <div className="text-gray-500">📉 最低 <span className="text-gray-700 font-medium">{lowestBattery}</span></div>
                  )}
                </div>
              )}
            </>
          );
        })()}
      </div>
    </div>
  );
}
