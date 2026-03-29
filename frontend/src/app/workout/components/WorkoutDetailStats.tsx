'use client';

import { format, parseISO } from 'date-fns';
import { formatDuration, formatPace, formatDistance, HR_ZONE_COLORS } from './workoutUtils';
import { WorkoutDetail, LapData } from './workoutTypes';

interface WorkoutDetailStatsProps {
  workoutDetail: WorkoutDetail;
  activeTab: 'stats' | 'laps' | 'intervals';
  setActiveTab: (tab: 'stats' | 'laps' | 'intervals') => void;
  hrZoneData: { name: string; value: number; color: string }[];
}

export default function WorkoutDetailStats({
  workoutDetail,
  activeTab,
  setActiveTab,
  hrZoneData,
}: WorkoutDetailStatsProps) {
  return (
    <div className="bg-slate-800/60 rounded-xl p-6 border border-slate-700">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-bold text-white">📋 详细数据</h3>
        <div className="flex gap-2 text-xs">
          <button
            onClick={() => setActiveTab('stats')}
            className={`px-3 py-1 rounded hover:bg-blue-600 transition-colors ${
              activeTab === 'stats' ? 'bg-blue-600/80 text-white' : 'bg-slate-700/50 text-gray-400'
            }`}
          >
            统计信息
          </button>
          <button
            onClick={() => setActiveTab('laps')}
            className={`px-3 py-1 rounded hover:bg-blue-600 transition-colors ${
              activeTab === 'laps' ? 'bg-blue-600/80 text-white' : 'bg-slate-700/50 text-gray-400'
            }`}
          >
            计圈
          </button>
          <button
            onClick={() => setActiveTab('intervals')}
            className={`px-3 py-1 rounded hover:bg-blue-600 transition-colors ${
              activeTab === 'intervals' ? 'bg-blue-600/80 text-white' : 'bg-slate-700/50 text-gray-400'
            }`}
          >
            区间用时
          </button>
        </div>
      </div>

      {/* Stats Tab */}
      {activeTab === 'stats' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Distance & Calories */}
          <div className="space-y-3">
            <h4 className="text-sm font-semibold text-gray-300 border-b border-slate-700 pb-2">距离与消耗</h4>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-400">距离</span>
                <span className="text-white font-medium">{formatDistance(workoutDetail.distance_meters || 0)} km</span>
              </div>
              {workoutDetail.calories && workoutDetail.active_calories && (
                <div className="flex justify-between">
                  <span className="text-gray-400">静息消耗</span>
                  <span className="text-white font-medium">{workoutDetail.calories - workoutDetail.active_calories} kcal</span>
                </div>
              )}
              {workoutDetail.active_calories && (
                <div className="flex justify-between">
                  <span className="text-gray-400">活动消耗</span>
                  <span className="text-white font-medium">{workoutDetail.active_calories} kcal</span>
                </div>
              )}
              <div className="flex justify-between">
                <span className="text-gray-400">总消耗</span>
                <span className="text-white font-medium">{workoutDetail.calories || '--'} kcal</span>
              </div>
              <div className="flex justify-between text-gray-500 text-xs pt-2 border-t border-slate-700">
                <span>已摄入能量</span>
                <span>--</span>
              </div>
              <div className="flex justify-between text-gray-500 text-xs">
                <span>净消耗</span>
                <span>{workoutDetail.calories ? `-${workoutDetail.calories}` : '--'} kcal</span>
              </div>
              <div className="flex justify-between text-gray-500 text-xs pt-2 border-t border-slate-700">
                <span>估计汗液流失</span>
                <span>{workoutDetail.calories ? `${Math.round(workoutDetail.calories * 1.5)} 毫升` : '--'}</span>
              </div>
              <div className="flex justify-between text-gray-500 text-xs">
                <span>已补充水分</span>
                <span>-- 毫升</span>
              </div>
              <div className="flex justify-between text-gray-500 text-xs">
                <span>净补水量</span>
                <span>{workoutDetail.calories ? `-${Math.round(workoutDetail.calories * 1.5)} 毫升` : '--'}</span>
              </div>
            </div>
          </div>

          {/* Training Effect */}
          <div className="space-y-3">
            <h4 className="text-sm font-semibold text-gray-300 border-b border-slate-700 pb-2 flex items-center gap-2">
              训练效果与负荷
              <span className="text-gray-500 text-xs">?</span>
            </h4>
            <div className="space-y-2 text-sm">
              {workoutDetail.training_effect_aerobic && (
                <div className="flex justify-between items-center">
                  <div className="flex items-center gap-2">
                    <span className="text-gray-400">有氧效果</span>
                    <span className="text-xs text-gray-500">
                      {workoutDetail.training_effect_aerobic < 1.0 ? '微小作用' :
                       workoutDetail.training_effect_aerobic < 2.0 ? '维持' :
                       workoutDetail.training_effect_aerobic < 3.0 ? '改善' :
                       workoutDetail.training_effect_aerobic < 4.0 ? '高度改善' : '过度训练'}
                    </span>
                  </div>
                  <span className="text-white font-medium">{workoutDetail.training_effect_aerobic.toFixed(1)}</span>
                </div>
              )}
              {workoutDetail.training_effect_anaerobic && (
                <div className="flex justify-between items-center">
                  <div className="flex items-center gap-2">
                    <span className="text-gray-400">无氧效果</span>
                    <span className="text-xs text-gray-500">
                      {workoutDetail.training_effect_anaerobic === 0 ? '无效益' :
                       workoutDetail.training_effect_anaerobic < 1.0 ? '微小作用' : '有效'}
                    </span>
                  </div>
                  <span className="text-white font-medium">{workoutDetail.training_effect_anaerobic.toFixed(1)}</span>
                </div>
              )}
              {workoutDetail.training_load && (
                <div className="flex justify-between items-center">
                  <div className="flex items-center gap-2">
                    <span className="text-gray-400">运动负荷</span>
                    <span className="text-gray-500 text-xs">?</span>
                  </div>
                  <span className="text-white font-medium">{workoutDetail.training_load}</span>
                </div>
              )}
              {workoutDetail.training_effect_aerobic && (
                <div className="pt-2 border-t border-slate-700">
                  <div className="text-xs text-gray-500">
                    {workoutDetail.training_effect_aerobic < 1.5 ? '● 恢复(低强度有氧) 主要益处' :
                     workoutDetail.training_effect_aerobic < 2.5 ? '● 基础耐力 主要益处' :
                     workoutDetail.training_effect_aerobic < 3.5 ? '● 有氧能力 主要益处' :
                     '● 高强度训练 主要益处'}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Elevation */}
          {(workoutDetail.elevation_gain_meters || workoutDetail.elevation_loss_meters || workoutDetail.min_elevation_meters || workoutDetail.max_elevation_meters) && (
            <div className="space-y-3">
              <h4 className="text-sm font-semibold text-gray-300 border-b border-slate-700 pb-2">海拔高度</h4>
              <div className="space-y-2 text-sm">
                {workoutDetail.elevation_gain_meters && (
                  <div className="flex justify-between">
                    <span className="text-gray-400">累计爬升</span>
                    <span className="text-white font-medium">{workoutDetail.elevation_gain_meters.toFixed(0)} 米</span>
                  </div>
                )}
                {workoutDetail.elevation_loss_meters && (
                  <div className="flex justify-between">
                    <span className="text-gray-400">累计下降</span>
                    <span className="text-white font-medium">{workoutDetail.elevation_loss_meters.toFixed(0)} 米</span>
                  </div>
                )}
                {workoutDetail.min_elevation_meters && (
                  <div className="flex justify-between">
                    <span className="text-gray-400">最低海拔</span>
                    <span className="text-white font-medium">{workoutDetail.min_elevation_meters.toFixed(0)} 米</span>
                  </div>
                )}
                {workoutDetail.max_elevation_meters && (
                  <div className="flex justify-between">
                    <span className="text-gray-400">最高海拔</span>
                    <span className="text-white font-medium">{workoutDetail.max_elevation_meters.toFixed(0)} 米</span>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Intensity Duration */}
          {workoutDetail.duration_seconds && (
            <div className="space-y-3">
              <h4 className="text-sm font-semibold text-gray-300 border-b border-slate-700 pb-2">强度活动时间</h4>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-400">中度</span>
                  <span className="text-white font-medium">
                    {workoutDetail.duration_seconds ? Math.floor(workoutDetail.duration_seconds * 0.5 / 60) : 0} 分钟
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">高强度</span>
                  <span className="text-white font-medium">
                    {workoutDetail.duration_seconds ? `${Math.floor(workoutDetail.duration_seconds * 0.1 / 60)} 分钟 x2` : '0 分钟'}
                  </span>
                </div>
                <div className="flex justify-between pt-2 border-t border-slate-700">
                  <span className="text-gray-400">总计</span>
                  <span className="text-white font-medium">
                    {workoutDetail.duration_seconds ? Math.floor(workoutDetail.duration_seconds * 0.6 / 60) : 0} 分钟
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Heart Rate */}
          {(workoutDetail.avg_heart_rate || workoutDetail.max_heart_rate || workoutDetail.min_heart_rate) && (
            <div className="space-y-3">
              <h4 className="text-sm font-semibold text-gray-300 border-b border-slate-700 pb-2">心率</h4>
              <div className="space-y-2 text-sm">
                {workoutDetail.avg_heart_rate && (
                  <div className="flex justify-between">
                    <span className="text-gray-400">平均心率</span>
                    <span className="text-white font-medium">{workoutDetail.avg_heart_rate} bpm</span>
                  </div>
                )}
                {workoutDetail.max_heart_rate && (
                  <div className="flex justify-between">
                    <span className="text-gray-400">最大心率</span>
                    <span className="text-white font-medium">{workoutDetail.max_heart_rate} bpm</span>
                  </div>
                )}
                {workoutDetail.min_heart_rate && (
                  <div className="flex justify-between">
                    <span className="text-gray-400">最小心率</span>
                    <span className="text-white font-medium">{workoutDetail.min_heart_rate} bpm</span>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Pace/Speed */}
          {(workoutDetail.avg_speed_kmh || workoutDetail.max_speed_kmh || workoutDetail.avg_pace_seconds_per_km) && (
            <div className="space-y-3">
              <h4 className="text-sm font-semibold text-gray-300 border-b border-slate-700 pb-2">配速/速度</h4>
              <div className="space-y-2 text-sm">
                {workoutDetail.avg_speed_kmh && (
                  <div className="flex justify-between">
                    <span className="text-gray-400">平均速度</span>
                    <span className="text-white font-medium">{workoutDetail.avg_speed_kmh.toFixed(1)} km/h</span>
                  </div>
                )}
                {workoutDetail.max_speed_kmh && (
                  <div className="flex justify-between">
                    <span className="text-gray-400">最大速度</span>
                    <span className="text-white font-medium">{workoutDetail.max_speed_kmh.toFixed(1)} km/h</span>
                  </div>
                )}
                {workoutDetail.avg_pace_seconds_per_km && (
                  <div className="flex justify-between">
                    <span className="text-gray-400">平均配速</span>
                    <span className="text-white font-mono">{formatPace(workoutDetail.avg_pace_seconds_per_km)}</span>
                  </div>
                )}
                {workoutDetail.best_pace_seconds_per_km && (
                  <div className="flex justify-between">
                    <span className="text-gray-400">最佳配速</span>
                    <span className="text-white font-mono">{formatPace(workoutDetail.best_pace_seconds_per_km)}</span>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Timing */}
          <div className="space-y-3">
            <h4 className="text-sm font-semibold text-gray-300 border-b border-slate-700 pb-2">计时</h4>
            <div className="space-y-2 text-sm">
              {workoutDetail.start_time && (
                <div className="flex justify-between">
                  <span className="text-gray-400">开始时间</span>
                  <span className="text-white font-medium">{format(parseISO(workoutDetail.start_time), 'yyyy-MM-dd HH:mm:ss')}</span>
                </div>
              )}
              {workoutDetail.end_time && (
                <div className="flex justify-between">
                  <span className="text-gray-400">结束时间</span>
                  <span className="text-white font-medium">{format(parseISO(workoutDetail.end_time), 'yyyy-MM-dd HH:mm:ss')}</span>
                </div>
              )}
              <div className="flex justify-between">
                <span className="text-gray-400">总时长</span>
                <span className="text-white font-medium font-mono">{formatDuration(workoutDetail.duration_seconds)}</span>
              </div>
              {workoutDetail.moving_duration_seconds && (
                <div className="flex justify-between">
                  <span className="text-gray-400">移动时间</span>
                  <span className="text-white font-medium font-mono">{formatDuration(workoutDetail.moving_duration_seconds)}</span>
                </div>
              )}
            </div>
          </div>

          {/* Other */}
          {(workoutDetail.steps || workoutDetail.avg_cadence) && (
            <div className="space-y-3">
              <h4 className="text-sm font-semibold text-gray-300 border-b border-slate-700 pb-2">其他</h4>
              <div className="space-y-2 text-sm">
                {workoutDetail.steps && (
                  <div className="flex justify-between">
                    <span className="text-gray-400">步数</span>
                    <span className="text-white font-medium">{workoutDetail.steps.toLocaleString()}</span>
                  </div>
                )}
                {workoutDetail.avg_cadence && (
                  <div className="flex justify-between">
                    <span className="text-gray-400">平均步频</span>
                    <span className="text-white font-medium">{workoutDetail.avg_cadence} 步/分钟</span>
                  </div>
                )}
                {workoutDetail.max_cadence && (
                  <div className="flex justify-between">
                    <span className="text-gray-400">最大步频</span>
                    <span className="text-white font-medium">{workoutDetail.max_cadence} 步/分钟</span>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Laps Tab */}
      {activeTab === 'laps' && (() => {
        const laps: LapData[] = workoutDetail.lap_data ? JSON.parse(workoutDetail.lap_data) : [];
        if (laps.length === 0) {
          return (
            <div className="text-center py-12">
              <div className="text-6xl mb-4">📈</div>
              <p className="text-gray-400 text-lg mb-2">暂无计圈数据</p>
              <p className="text-gray-500 text-sm">Garmin同步的运动会自动包含计圈信息</p>
            </div>
          );
        }

        return (
          <div className="space-y-4">
            {laps.map((lap) => (
              <div key={lap.lap} className="bg-slate-700/30 rounded-lg p-4 border border-slate-600/50">
                <div className="flex items-center justify-between mb-3 pb-2 border-b border-slate-600">
                  <h4 className="text-lg font-bold text-white">第 {lap.lap} 圈</h4>
                  {lap.duration && (
                    <span className="text-blue-400 font-mono font-semibold">{formatDuration(lap.duration)}</span>
                  )}
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                  {lap.distance && (
                    <div>
                      <div className="text-gray-400 text-xs mb-1">距离</div>
                      <div className="text-white font-medium">{formatDistance(lap.distance)} km</div>
                    </div>
                  )}
                  {lap.avg_pace && (
                    <div>
                      <div className="text-gray-400 text-xs mb-1">配速</div>
                      <div className="text-white font-mono">{formatPace(lap.avg_pace)}</div>
                    </div>
                  )}
                  {lap.avg_speed && (
                    <div>
                      <div className="text-gray-400 text-xs mb-1">速度</div>
                      <div className="text-white font-medium">{lap.avg_speed.toFixed(1)} km/h</div>
                    </div>
                  )}
                  {lap.avg_hr && (
                    <div>
                      <div className="text-gray-400 text-xs mb-1">平均心率</div>
                      <div className="text-white font-medium">{lap.avg_hr} bpm</div>
                    </div>
                  )}
                  {lap.max_hr && (
                    <div>
                      <div className="text-gray-400 text-xs mb-1">最大心率</div>
                      <div className="text-white font-medium">{lap.max_hr} bpm</div>
                    </div>
                  )}
                  {lap.elevation_gain && (
                    <div>
                      <div className="text-gray-400 text-xs mb-1">爬升</div>
                      <div className="text-white font-medium">{Math.round(lap.elevation_gain)} m</div>
                    </div>
                  )}
                  {lap.calories && (
                    <div>
                      <div className="text-gray-400 text-xs mb-1">卡路里</div>
                      <div className="text-white font-medium">{lap.calories} kcal</div>
                    </div>
                  )}
                  {lap.avg_cadence && (
                    <div>
                      <div className="text-gray-400 text-xs mb-1">步频</div>
                      <div className="text-white font-medium">{lap.avg_cadence} 步/分</div>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        );
      })()}

      {/* Intervals Tab */}
      {activeTab === 'intervals' && hrZoneData.length > 0 && (() => {
        const total = hrZoneData.reduce((sum, z) => sum + z.value, 0);
        const maxHR = workoutDetail?.max_heart_rate || 220;
        const hrZones = [
          { zone: 1, name: '热身', range: `${Math.round(maxHR * 0.5)}-${Math.round(maxHR * 0.6)} bpm`, color: HR_ZONE_COLORS[0] },
          { zone: 2, name: '燃脂', range: `${Math.round(maxHR * 0.6)}-${Math.round(maxHR * 0.7)} bpm`, color: HR_ZONE_COLORS[1] },
          { zone: 3, name: '有氧', range: `${Math.round(maxHR * 0.7)}-${Math.round(maxHR * 0.8)} bpm`, color: HR_ZONE_COLORS[2] },
          { zone: 4, name: '临界', range: `${Math.round(maxHR * 0.8)}-${Math.round(maxHR * 0.9)} bpm`, color: HR_ZONE_COLORS[3] },
          { zone: 5, name: '无氧', range: `> ${Math.round(maxHR * 0.9)} bpm`, color: HR_ZONE_COLORS[4] },
        ];

        return (
          <div className="space-y-4">
            {hrZones.map((zone, idx) => {
              const zoneData = hrZoneData[idx];
              const percentage = total > 0 ? (zoneData.value / total) * 100 : 0;
              return (
                <div key={zone.zone} className="space-y-2">
                  <div className="flex items-center justify-between text-sm">
                    <div className="flex items-center gap-2">
                      <span className="text-white font-medium">区间 {zone.zone}</span>
                      <span className="text-gray-400 text-xs">{zone.range}</span>
                      <span className="text-gray-500 text-xs">({zone.name})</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-white font-mono">{formatDuration(zoneData.value)}</span>
                      <span className="text-gray-400 font-medium">{percentage.toFixed(0)}%</span>
                    </div>
                  </div>
                  <div className="w-full bg-slate-700/30 rounded-full h-3 overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all duration-500"
                      style={{
                        width: `${percentage}%`,
                        backgroundColor: zone.color
                      }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        );
      })()}
    </div>
  );
}
