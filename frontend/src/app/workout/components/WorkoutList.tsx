'use client';

import { format, parseISO } from 'date-fns';
import { zhCN } from 'date-fns/locale';
import { WORKOUT_TYPES, formatDuration, formatDistance } from './workoutUtils';
import { WorkoutSummary } from './workoutTypes';

interface WorkoutListProps {
  workouts: WorkoutSummary[] | undefined;
  loadingWorkouts: boolean;
  selectedWorkout: number | null;
  setSelectedWorkout: (id: number) => void;
}

export default function WorkoutList({ workouts, loadingWorkouts, selectedWorkout, setSelectedWorkout }: WorkoutListProps) {
  return (
    <div className="lg:col-span-1 bg-slate-800/60 rounded-xl p-4 border border-slate-700">
      <h2 className="text-lg font-bold text-white mb-4">训练记录</h2>

      {loadingWorkouts ? (
        <div className="flex items-center justify-center py-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
        </div>
      ) : workouts && workouts.length > 0 ? (
        <div className="space-y-2 max-h-[calc(100vh-280px)] overflow-y-auto">
          {workouts.map((w) => {
            const typeConfig = WORKOUT_TYPES[w.workout_type as keyof typeof WORKOUT_TYPES] || WORKOUT_TYPES.other;
            return (
              <div
                key={w.id}
                onClick={() => setSelectedWorkout(w.id)}
                className={`p-3 rounded-lg cursor-pointer transition-all ${
                  selectedWorkout === w.id
                    ? 'bg-blue-600/30 border border-blue-500'
                    : 'bg-slate-700/50 hover:bg-slate-700 border border-transparent'
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-xl">{typeConfig.icon}</span>
                    <div>
                      <div className="text-white font-medium text-sm">
                        {w.workout_name || typeConfig.name}
                      </div>
                      <div className="text-gray-400 text-xs">
                        {format(parseISO(w.workout_date), 'MM月dd日 EEEE', { locale: zhCN })}
                      </div>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-white text-sm font-mono">{formatDuration(w.duration_seconds)}</div>
                    {w.distance_meters && (
                      <div className="text-gray-400 text-xs">{formatDistance(w.distance_meters)} km</div>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-3 mt-2 text-xs text-gray-400">
                  {w.avg_heart_rate && <span>❤️ {w.avg_heart_rate}bpm</span>}
                  {w.calories && <span>🔥 {w.calories}kcal</span>}
                  {w.has_ai_analysis && <span className="text-green-400">✨ 已分析</span>}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="text-center py-8 text-gray-400">
          <div className="text-4xl mb-2">🏃</div>
          <p>暂无运动记录</p>
          <p className="text-sm mt-1">点击"同步Garmin"获取数据</p>
        </div>
      )}
    </div>
  );
}
