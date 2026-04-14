'use client';

import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  ResponsiveContainer,
} from 'recharts';
import {
  GarminData,
  MetricCard,
  formatDuration,
  formatSleepTime,
  getSleepScoreColor,
  getHrvStatusText,
} from './types';

interface SleepChartItem {
  date: string;
  deep: number;
  light: number;
  rem: number;
  awake: number;
}

interface HrChartItem {
  date: string;
  resting: number | null;
  avg: number | null;
}

interface HrvChartItem {
  date: string;
  hrv: number | null;
}

interface HealthMetricsCardsProps {
  record: GarminData;
  sleepChartData: SleepChartItem[];
  hrChartData: HrChartItem[];
  hrvChartData: HrvChartItem[];
  avg7DayRestingHR: number | null;
}

export default function HealthMetricsCards({
  record,
  sleepChartData,
  hrChartData,
  hrvChartData,
  avg7DayRestingHR,
}: HealthMetricsCardsProps) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
      {/* 睡眠分数 */}
      <MetricCard icon="😴" title="睡眠分数">
        <div className="flex items-baseline gap-4">
          <span className={`text-5xl font-bold ${getSleepScoreColor(record?.sleep_score)}`}>
            {record?.sleep_score || '--'}
          </span>
          <div>
            <div className="text-lg text-gray-700">
              {formatDuration(record?.total_sleep_duration)}
            </div>
            <div className="text-sm text-gray-500">持续时间</div>
          </div>
        </div>
        {/* 睡眠阶段柱状图 */}
        <div className="mt-4 h-24">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={sleepChartData} barGap={0}>
              <XAxis dataKey="date" axisLine={false} tickLine={false} tick={{ fontSize: 10 }} />
              <Bar dataKey="deep" stackId="a" fill="#1e40af" radius={[0, 0, 0, 0]} />
              <Bar dataKey="light" stackId="a" fill="#3b82f6" />
              <Bar dataKey="rem" stackId="a" fill="#c026d3" />
              <Bar dataKey="awake" stackId="a" fill="#f97316" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="flex justify-between text-xs text-gray-400 mt-1">
          <span>{formatSleepTime(record?.sleep_start_time)}</span>
          <span>{formatSleepTime(record?.sleep_end_time)}</span>
        </div>
      </MetricCard>

      {/* HRV状态 */}
      <MetricCard icon="💓" title="HRV状态">
        <div className="flex items-center gap-2 mb-2">
          <span className={`w-3 h-3 rounded-sm ${
            record?.hrv_status === 'BALANCED' ? 'bg-green-500' :
            record?.hrv_status === 'UNBALANCED' ? 'bg-orange-500' : 'bg-gray-400'
          }`}></span>
          <span className={`text-xl font-bold ${getHrvStatusText(record?.hrv_status).color}`}>
            {getHrvStatusText(record?.hrv_status).text}
          </span>
        </div>
        <div className="text-3xl font-bold text-gray-800">
          {record?.hrv ? Math.round(record.hrv) : '--'} <span className="text-lg font-normal text-gray-500">毫秒</span>
        </div>
        <div className="text-sm text-gray-500">7天平均</div>

        {/* HRV状态条 */}
        <div className="flex gap-0.5 mt-3">
          {['red', 'orange', 'yellow', 'green', 'green'].map((color, i) => (
            <div key={i} className={`h-2 flex-1 rounded-sm bg-${color}-${i < 2 ? '500' : '400'}`}
              style={{ backgroundColor: ['#ef4444', '#f97316', '#eab308', '#22c55e', '#22c55e'][i] }}
            />
          ))}
        </div>

        {/* HRV趋势图 */}
        <div className="mt-3 h-16">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={hrvChartData}>
              <defs>
                <linearGradient id="hrvGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                </linearGradient>
              </defs>
              <Area type="monotone" dataKey="hrv" stroke="#10b981" fill="url(#hrvGradient)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
        <div className="text-xs text-gray-400 text-center mt-1">过去 4 周</div>
      </MetricCard>

      {/* 身体电量 */}
      <MetricCard icon="🔋" title="身体电量">
        <BodyBatteryContent record={record} />
      </MetricCard>

      {/* 心率 */}
      <MetricCard icon="❤️" title="心率">
        <div className="text-3xl font-bold text-gray-800">
          {avg7DayRestingHR || '--'} <span className="text-lg font-normal text-gray-500">bpm</span>
        </div>
        <div className="text-sm text-gray-500">过去 7 天平均静息心率</div>

        <div className="mt-2 text-2xl font-bold text-gray-800">
          {record?.resting_heart_rate || '--'} <span className="text-lg font-normal text-gray-500">bpm</span>
        </div>
        <div className="text-sm text-gray-500">静止</div>

        {/* 心率曲线 */}
        <div className="mt-3 h-16">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={hrChartData}>
              <Line type="monotone" dataKey="resting" stroke="#3b82f6" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <div className="text-xs text-gray-400 text-center mt-1">过去 7 天</div>
      </MetricCard>
    </div>
  );
}

/** 身体电量内容（从 IIFE 提取） */
function BodyBatteryContent({ record }: { record: GarminData }) {
  const currentBattery = record?.body_battery_current;
  const peakBattery = record?.body_battery_most_charged ?? record?.body_battery_charged;
  const displayBattery = currentBattery ?? peakBattery;
  const hasCurrent = currentBattery !== null && currentBattery !== undefined;
  const hasPeak = peakBattery !== null && peakBattery !== undefined;

  const getBatteryColor = (value: number | null | undefined) => {
    if (value === null || value === undefined) return 'text-gray-400';
    if (value >= 80) return 'text-green-500';
    if (value >= 50) return 'text-yellow-500';
    return 'text-red-500';
  };

  const getBatteryBgColor = (value: number | null | undefined) => {
    if (value === null || value === undefined) return 'bg-gray-400';
    if (value >= 80) return 'bg-green-500';
    if (value >= 50) return 'bg-yellow-500';
    return 'bg-red-500';
  };

  return (
    <>
      <div className="flex items-center gap-2 mb-1">
        <span className={`text-4xl font-bold ${getBatteryColor(displayBattery)}`}>
          {displayBattery ?? '--'}
        </span>
        <span className="text-lg text-gray-500">/100</span>
      </div>
      <div className="text-sm text-gray-500 mb-2">
        {hasCurrent ? '当前' : hasPeak ? '峰值' : '暂无数据'}
        {hasCurrent && (
          <span className={`ml-2 ${getBatteryColor(currentBattery)}`}>
            {currentBattery! >= 80 ? '充足' : currentBattery! >= 50 ? '中等' : '偏低'}
          </span>
        )}
      </div>

      <div className="relative h-3 bg-gray-200 rounded-full overflow-hidden mb-3">
        <div
          className={`h-full transition-all ${getBatteryBgColor(displayBattery)}`}
          style={{ width: `${Math.min(displayBattery ?? 0, 100)}%` }}
        />
      </div>

      <div className="space-y-1 text-sm">
        {hasCurrent && hasPeak && currentBattery !== peakBattery && (
          <div className="flex justify-between">
            <span className="text-gray-500">📈 峰值</span>
            <span className={`font-medium ${getBatteryColor(peakBattery)}`}>{peakBattery}</span>
          </div>
        )}
        {record?.body_battery_lowest !== null && (
          <div className="flex justify-between">
            <span className="text-gray-500">📉 最低</span>
            <span className="text-gray-800 font-medium">{record.body_battery_lowest}</span>
          </div>
        )}
        {record?.body_battery_drained !== null && (
          <div className="flex justify-between">
            <span className="text-gray-500">⚡ 消耗</span>
            <span className="text-orange-600 font-medium">-{record.body_battery_drained}</span>
          </div>
        )}
      </div>
    </>
  );
}
