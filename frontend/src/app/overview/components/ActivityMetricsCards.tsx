'use client';

import { format } from 'date-fns';
import { GarminData, MetricCard } from './types';

interface ActivityMetricsCardsProps {
  record: GarminData;
  weeklyIntensityMinutes: number;
  intensityGoal: number;
  intensityProgress: number;
  vo2maxValue: number | null | undefined;
  latestVO2maxRecord: GarminData | undefined;
}

export default function ActivityMetricsCards({
  record,
  weeklyIntensityMinutes,
  intensityGoal,
  intensityProgress,
  vo2maxValue,
  latestVO2maxRecord,
}: ActivityMetricsCardsProps) {
  return (
    <>
      {/* 第二行：活动指标 */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
        {/* 强度活动时间 */}
        <MetricCard icon="🏃" title="强度活动时间">
          <div className="flex justify-center">
            <div className="relative w-28 h-28">
              <svg className="w-full h-full transform -rotate-90">
                <circle
                  cx="56"
                  cy="56"
                  r="48"
                  stroke="#e5e7eb"
                  strokeWidth="8"
                  fill="none"
                />
                <circle
                  cx="56"
                  cy="56"
                  r="48"
                  stroke="#3b82f6"
                  strokeWidth="8"
                  fill="none"
                  strokeDasharray={`${intensityProgress * 3.02} 302`}
                  strokeLinecap="round"
                />
              </svg>
              <div className="absolute inset-0 flex items-center justify-center">
                <span className="text-3xl font-bold text-gray-800">{weeklyIntensityMinutes}</span>
              </div>
            </div>
          </div>
          <div className="text-center text-sm text-gray-500 mt-2">
            目标: {intensityGoal} 分钟
          </div>
          <div className="flex justify-center gap-3 mt-3">
            {['一', '二', '三', '四', '五', '六', '日'].map((day, i) => (
              <span key={day} className={`text-xs ${i === new Date().getDay() - 1 ? 'text-blue-500 font-bold' : 'text-gray-400'}`}>
                {day}
              </span>
            ))}
          </div>
        </MetricCard>

        {/* 热量消耗 */}
        <MetricCard icon="🔥" title="热量消耗">
          <div className="text-4xl font-bold text-gray-800">
            {record?.calories_burned?.toLocaleString() || '--'}
          </div>
          <div className="flex gap-0 mt-3 rounded-full overflow-hidden h-3">
            <div
              className="bg-red-500"
              style={{ width: `${record?.active_calories && record?.calories_burned ? (record.active_calories / record.calories_burned) * 100 : 30}%` }}
            />
            <div
              className="bg-blue-500"
              style={{ width: `${record?.bmr_calories && record?.calories_burned ? (record.bmr_calories / record.calories_burned) * 100 : 70}%` }}
            />
          </div>
          <div className="flex justify-between mt-2 text-sm">
            <div>
              <span className="text-gray-800 font-medium">{record?.active_calories || '--'}</span>
              <span className="text-gray-500 ml-1">运动</span>
            </div>
            <div>
              <span className="text-gray-800 font-medium">{record?.bmr_calories || '--'}</span>
              <span className="text-gray-500 ml-1">静息消耗</span>
            </div>
          </div>
        </MetricCard>

        {/* 呼吸 */}
        <MetricCard icon="🌬️" title="呼吸">
          <div className="space-y-2">
            <div>
              <div className="text-3xl font-bold text-gray-800">
                {record?.avg_respiration_awake ? Math.round(record.avg_respiration_awake) : '--'} <span className="text-lg font-normal text-gray-500">brpm</span>
              </div>
              <div className="text-sm text-gray-500">清醒平均</div>
            </div>
            <div>
              <div className="text-2xl font-bold text-gray-800">
                {record?.avg_respiration_sleep ? Math.round(record.avg_respiration_sleep) : '--'} <span className="text-base font-normal text-gray-500">brpm</span>
              </div>
              <div className="text-sm text-gray-500">睡眠平均</div>
            </div>
            <div>
              <div className="text-lg text-gray-700">
                {record?.lowest_respiration ? Math.round(record.lowest_respiration) : '--'}/{record?.highest_respiration ? Math.round(record.highest_respiration) : '--'} <span className="text-sm text-gray-500">brpm</span>
              </div>
              <div className="text-sm text-gray-500">低/高</div>
            </div>
          </div>
        </MetricCard>

        {/* VO2 Max */}
        <MetricCard icon="🏃‍♂️" title="跑步最大摄氧量">
          {vo2maxValue ? (
            <div>
              <div className="text-4xl font-bold text-blue-500">
                {vo2maxValue.toFixed(1)}
              </div>
              <div className="text-sm text-gray-500 mt-1">mL/kg/min</div>
              {latestVO2maxRecord && latestVO2maxRecord.record_date !== record?.record_date && (
                <div className="text-xs text-gray-400 mt-1">
                  {format(new Date(latestVO2maxRecord.record_date), 'MM-dd')} 数据
                </div>
              )}
            </div>
          ) : (
            <div className="text-center py-4">
              <div className="text-4xl mb-2">🏃</div>
              <p className="text-gray-500 text-sm">跟踪户外跑步情况，了解您当前的最大摄氧量。</p>
            </div>
          )}
        </MetricCard>
      </div>

      {/* 第三行：次要指标，紧凑排列 */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-4 gap-4">
        {/* 血氧饱和度 */}
        <MetricCard icon="🩸" title="脉搏血氧饱和度适应">
          {record?.spo2_avg !== null && record?.spo2_avg !== undefined ? (
            <div>
              <div className="text-4xl font-bold text-green-500">
                {record.spo2_avg.toFixed(0)}%
              </div>
              <div className="text-sm text-gray-500 mt-1">
                范围: {record.spo2_min !== null && record.spo2_min !== undefined ? record.spo2_min.toFixed(0) : '--'}% - {record.spo2_max !== null && record.spo2_max !== undefined ? record.spo2_max.toFixed(0) : '--'}%
              </div>
            </div>
          ) : (
            <div className="text-center py-4">
              <div className="text-4xl mb-2 opacity-50">🔴</div>
              <p className="text-gray-500 text-sm">今日无读数</p>
            </div>
          )}
        </MetricCard>

        {/* 步数 */}
        <MetricCard icon="👣" title="步数">
          <div className="text-3xl font-bold text-gray-800">
            {record?.steps?.toLocaleString() || '--'}
          </div>
        </MetricCard>

        {/* 距离 */}
        <MetricCard icon="📏" title="距离">
          <div className="text-3xl font-bold text-gray-800">
            {record?.distance_meters ? (record.distance_meters / 1000).toFixed(2) : '--'} <span className="text-lg font-normal text-gray-500">km</span>
          </div>
        </MetricCard>

        {/* 楼层 */}
        <MetricCard icon="🏢" title="楼层">
          <div className="text-3xl font-bold text-gray-800">
            {record?.floors_climbed || '--'} <span className="text-lg font-normal text-gray-500">层</span>
          </div>
        </MetricCard>

        {/* 压力 */}
        <MetricCard
          icon={(() => {
            const stress = record?.stress_level;
            if (!stress) return '😐';
            if (stress <= 25) return '😊';
            if (stress <= 50) return '😐';
            if (stress <= 75) return '😟';
            return '😰';
          })()}
          title="压力"
        >
          <div className="text-3xl font-bold text-gray-800">
            {record?.stress_level || '--'}
          </div>
          {record?.stress_level && (
            <div className={`text-sm font-medium mt-1 ${
              record.stress_level <= 25 ? 'text-green-600' :
              record.stress_level <= 50 ? 'text-blue-600' :
              record.stress_level <= 75 ? 'text-yellow-600' :
              'text-red-600'
            }`}>
              {record.stress_level <= 25 ? '放松' :
               record.stress_level <= 50 ? '正常' :
               record.stress_level <= 75 ? '中等' :
               '偏高'}
            </div>
          )}
        </MetricCard>
      </div>
    </>
  );
}
