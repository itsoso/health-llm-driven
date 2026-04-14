'use client';

import { format } from 'date-fns';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';

interface SleepAnalysisPanelProps {
  data: any;
}

export default function SleepAnalysisPanel({ data }: SleepAnalysisPanelProps) {
  if (!data) return null;

  return (
    <div className="space-y-6">
      <div className="bg-white p-6 rounded-xl shadow-lg border border-gray-200">
        <h2 className="text-2xl font-bold mb-6 text-gray-900">睡眠质量分析</h2>
        {data.status === 'success' ? (
          <div className="space-y-6">
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
              <div className="p-5 bg-blue-50 rounded-xl border-2 border-blue-200">
                <p className="text-sm font-semibold text-gray-700 mb-2">平均睡眠分数</p>
                <p className="text-3xl font-bold text-blue-700">{data.average_sleep_score}</p>
              </div>
              <div className="p-5 bg-green-50 rounded-xl border-2 border-green-200">
                <p className="text-sm font-semibold text-gray-700 mb-2">平均睡眠时长</p>
                <p className="text-3xl font-bold text-green-700">{data.average_sleep_duration_hours?.toFixed(1)}h</p>
              </div>
              <div className="p-5 bg-purple-50 rounded-xl border-2 border-purple-200">
                <p className="text-sm font-semibold text-gray-700 mb-2">深度睡眠</p>
                <p className="text-3xl font-bold text-purple-700">{data.average_deep_sleep_minutes?.toFixed(0)}m</p>
              </div>
              <div className="p-5 bg-yellow-50 rounded-xl border-2 border-yellow-200">
                <p className="text-sm font-semibold text-gray-700 mb-2">REM睡眠</p>
                <p className="text-3xl font-bold text-yellow-700">{data.average_rem_sleep_minutes?.toFixed(0)}m</p>
              </div>
              <div className="p-5 bg-orange-50 rounded-xl border-2 border-orange-200">
                <p className="text-sm font-semibold text-gray-700 mb-2">清醒时间</p>
                <p className="text-3xl font-bold text-orange-700">{data.average_awake_minutes?.toFixed(0)}m</p>
              </div>
            </div>

            {data.daily_data && data.daily_data.length > 0 && (
              <div className="mt-6 bg-white p-6 rounded-xl border-2 border-gray-200">
                <h3 className="text-xl font-bold mb-4 text-gray-900">深度睡眠趋势</h3>
                <ResponsiveContainer width="100%" height={300}>
                  <LineChart
                    data={data.daily_data
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
                    <XAxis dataKey="date" stroke="#6b7280" style={{ fontSize: '12px', fontWeight: 500 }} />
                    <YAxis stroke="#6b7280" style={{ fontSize: '12px', fontWeight: 500 }} label={{ value: '时长 (小时)', angle: -90, position: 'insideLeft', style: { fontSize: '12px', fontWeight: 600 } }} />
                    <Tooltip contentStyle={{ backgroundColor: 'white', border: '2px solid #e5e7eb', borderRadius: '8px', fontSize: '14px', fontWeight: 500 }} formatter={(value: any) => value ? `${value}小时` : '-'} />
                    <Legend wrapperStyle={{ fontSize: '14px', fontWeight: 600 }} />
                    <Line type="monotone" dataKey="deepSleep" stroke="#8b5cf6" strokeWidth={3} dot={{ fill: '#8b5cf6', r: 5 }} name="深度睡眠" />
                    <Line type="monotone" dataKey="remSleep" stroke="#6366f1" strokeWidth={3} dot={{ fill: '#6366f1', r: 5 }} name="快速眼动" />
                    <Line type="monotone" dataKey="awake" stroke="#f59e0b" strokeWidth={2} strokeDasharray="5 5" dot={{ fill: '#f59e0b', r: 4 }} name="清醒时间" />
                  </LineChart>
                </ResponsiveContainer>

                <div className="mt-6 p-4 bg-purple-50 rounded-lg border border-purple-200">
                  <h4 className="text-lg font-bold mb-3 text-purple-900">深度睡眠解读</h4>
                  <div className="space-y-2 text-gray-800">
                    <p className="font-medium">
                      <span className="text-purple-700 font-bold">平均深度睡眠：{data.average_deep_sleep_minutes?.toFixed(0)}分钟</span>
                    </p>
                    {data.average_deep_sleep_minutes && (
                      <div className="text-sm leading-6">
                        {data.average_deep_sleep_minutes >= 90 ? (
                          <p className="text-green-700 font-semibold">✅ 优秀：深度睡眠充足，有助于身体恢复和免疫系统功能。</p>
                        ) : data.average_deep_sleep_minutes >= 60 ? (
                          <p className="text-blue-700 font-semibold">👍 良好：深度睡眠在正常范围内，继续保持。</p>
                        ) : (
                          <p className="text-orange-700 font-semibold">⚠️ 不足：深度睡眠偏少，建议改善睡眠环境，避免睡前使用电子设备。</p>
                        )}
                        <p className="mt-2 text-gray-700">深度睡眠是睡眠周期中最关键的阶段，占总睡眠的15-20%为佳。它有助于：</p>
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

                {data.average_awake_minutes && (
                  <div className="mt-4 p-4 bg-orange-50 rounded-lg border border-orange-200">
                    <h4 className="text-lg font-bold mb-3 text-orange-900">清醒时间解读</h4>
                    <div className="space-y-2 text-gray-800">
                      <p className="font-medium">
                        <span className="text-orange-700 font-bold">平均清醒时间：{data.average_awake_minutes?.toFixed(0)}分钟</span>
                      </p>
                      <div className="text-sm leading-6">
                        {data.average_awake_minutes <= 30 ? (
                          <p className="text-green-700 font-semibold">✅ 优秀：夜间清醒时间很少，睡眠连续性良好。</p>
                        ) : data.average_awake_minutes <= 60 ? (
                          <p className="text-blue-700 font-semibold">👍 正常：清醒时间在可接受范围内。</p>
                        ) : (
                          <p className="text-red-700 font-semibold">⚠️ 偏多：夜间清醒时间较长，可能影响睡眠质量。建议检查睡眠环境、避免睡前摄入咖啡因或酒精。</p>
                        )}
                        <p className="mt-2 text-gray-700">夜间清醒时间越少越好，理想情况下应少于30分钟。过多的清醒时间可能由以下因素引起：</p>
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
                {data.quality_assessment?.overall === 'excellent' && '✅ 优秀'}
                {data.quality_assessment?.overall === 'good' && '👍 良好'}
                {data.quality_assessment?.overall === 'fair' && '⚠️ 一般'}
                {data.quality_assessment?.overall === 'poor' && '❌ 较差'}
              </p>
            </div>

            {data.recommendations && (
              <div className="mt-6 p-5 bg-blue-50 rounded-xl border-2 border-blue-200">
                <h3 className="text-lg font-bold mb-3 text-blue-900">建议</h3>
                <ul className="list-disc list-inside space-y-2">
                  {data.recommendations.map((rec: string, idx: number) => (
                    <li key={idx} className="text-gray-900 font-medium leading-7">{rec}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ) : (
          <p className="text-gray-700 font-medium">{data.message}</p>
        )}
      </div>
    </div>
  );
}
