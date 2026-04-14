'use client';

import { format } from 'date-fns';
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

interface DataChartsAndTableProps {
  chartData: Array<Record<string, any>>;
  garminData: any;
  currentPage: number;
  setCurrentPage: (page: number) => void;
  pageSize: number;
}

export default function DataChartsAndTable({
  chartData,
  garminData,
  currentPage,
  setCurrentPage,
  pageSize,
}: DataChartsAndTableProps) {
  return (
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
            <Bar dataKey="lightSleep" stackId="sleep" fill="#60a5fa" name="浅睡" radius={[0, 0, 0, 0]} />
            <Bar dataKey="awake" stackId="sleep" fill="#f59e0b" name="清醒" radius={[8, 8, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
        <div className="mt-4 text-sm text-gray-600">
          <p className="font-semibold mb-2">睡眠阶段说明：</p>
          <ul className="space-y-1">
            <li>• <span className="text-purple-700 font-medium">深睡</span>：深度恢复阶段，占总睡眠15-20%为佳</li>
            <li>• <span className="text-indigo-700 font-medium">快速眼动</span>：记忆巩固阶段，占总睡眠20-25%为佳</li>
            <li>• <span className="text-blue-500 font-medium">浅睡</span>：过渡阶段，占总睡眠50-60%</li>
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
            <li>• <span className="text-green-700 font-medium">&ge;50ms</span>：优秀，恢复状态良好</li>
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

      {/* 呼吸频率趋势图 */}
      <div className="bg-white p-6 rounded-xl shadow-lg border border-gray-200">
        <h2 className="text-2xl font-bold mb-6 text-gray-900">呼吸频率趋势</h2>
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
              label={{ value: '次/分钟', angle: -90, position: 'insideLeft', style: { fontSize: '12px', fontWeight: 600 } }}
              domain={[8, 24]}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: 'white',
                border: '2px solid #e5e7eb',
                borderRadius: '8px',
                fontSize: '14px',
                fontWeight: 500
              }}
              formatter={(value: any) => value ? `${value.toFixed(1)} 次/分钟` : '-'}
            />
            <Legend
              wrapperStyle={{ fontSize: '14px', fontWeight: 600 }}
            />
            <Line
              type="monotone"
              dataKey="respirationAwake"
              stroke="#3b82f6"
              strokeWidth={3}
              dot={{ fill: '#3b82f6', r: 5 }}
              name="白天呼吸频率"
              connectNulls
            />
            <Line
              type="monotone"
              dataKey="respirationSleep"
              stroke="#8b5cf6"
              strokeWidth={3}
              dot={{ fill: '#8b5cf6', r: 5 }}
              name="睡眠呼吸频率"
              connectNulls
            />
            {/* 参考线：正常呼吸范围 */}
            <Line
              type="monotone"
              dataKey={() => 12}
              stroke="#10b981"
              strokeWidth={1}
              strokeDasharray="5 5"
              dot={false}
              name="正常下限 (12)"
              legendType="none"
            />
            <Line
              type="monotone"
              dataKey={() => 20}
              stroke="#f59e0b"
              strokeWidth={1}
              strokeDasharray="5 5"
              dot={false}
              name="正常上限 (20)"
              legendType="none"
            />
          </LineChart>
        </ResponsiveContainer>
        <div className="mt-4 text-sm text-gray-600">
          <p className="font-semibold mb-2">呼吸频率参考值（次/分钟）：</p>
          <ul className="space-y-1">
            <li>• <span className="text-green-700 font-medium">12-20</span>：正常范围</li>
            <li>• <span className="text-blue-700 font-medium">&lt;12</span>：呼吸较慢，可能处于深度放松状态</li>
            <li>• <span className="text-orange-700 font-medium">&gt;20</span>：呼吸较快，可能与运动、压力或健康状况有关</li>
          </ul>
          <p className="mt-2 text-gray-500">注：睡眠期间呼吸频率通常比白天低，这是正常的生理现象</p>
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
                <th className="px-5 py-4 text-left text-xs font-bold text-gray-700 uppercase tracking-wider border-r border-gray-200">压力</th>
                <th className="px-5 py-4 text-left text-xs font-bold text-gray-700 uppercase tracking-wider border-r border-gray-200">白天呼吸</th>
                <th className="px-5 py-4 text-left text-xs font-bold text-gray-700 uppercase tracking-wider">睡眠呼吸</th>
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
                    {item.body_battery_most_charged ?? item.body_battery_charged ?? '-'}
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
                  <td className="px-5 py-4 whitespace-nowrap text-sm border-r border-gray-100">
                    <span className={`font-semibold ${
                      item.avg_respiration_awake === null || item.avg_respiration_awake === undefined ? 'text-gray-500' :
                      item.avg_respiration_awake > 20 ? 'text-orange-700' :
                      item.avg_respiration_awake < 12 ? 'text-blue-700' :
                      'text-green-700'
                    }`}>
                      {item.avg_respiration_awake !== null && item.avg_respiration_awake !== undefined
                        ? `${item.avg_respiration_awake.toFixed(1)}` : '-'}
                    </span>
                  </td>
                  <td className="px-5 py-4 whitespace-nowrap text-sm">
                    <span className={`font-semibold ${
                      item.avg_respiration_sleep === null || item.avg_respiration_sleep === undefined ? 'text-gray-500' :
                      item.avg_respiration_sleep > 18 ? 'text-orange-700' :
                      item.avg_respiration_sleep < 10 ? 'text-blue-700' :
                      'text-green-700'
                    }`}>
                      {item.avg_respiration_sleep !== null && item.avg_respiration_sleep !== undefined
                        ? `${item.avg_respiration_sleep.toFixed(1)}` : '-'}
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
                onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
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
                onClick={() => setCurrentPage(Math.min(Math.ceil(garminData.data.length / pageSize), currentPage + 1))}
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
  );
}
