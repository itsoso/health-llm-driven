'use client';

import { format, parseISO } from 'date-fns';
import { zhCN } from 'date-fns/locale';
import { UseMutationResult } from '@tanstack/react-query';
import { WORKOUT_TYPES, formatDuration, formatDistance, formatPace } from './workoutUtils';
import { WorkoutDetail } from './workoutTypes';

interface WorkoutDetailHeaderProps {
  workoutDetail: WorkoutDetail;
  analyzeMutation: UseMutationResult<any, Error, number>;
  postAnalysisMutation: UseMutationResult<any, any, { workoutId: number; forceRegenerate?: boolean; cacheOnly?: boolean }>;
  refreshHRMutation: UseMutationResult<any, Error, number>;
  postAnalysis: any;
}

export default function WorkoutDetailHeader({
  workoutDetail,
  analyzeMutation,
  postAnalysisMutation,
  refreshHRMutation,
  postAnalysis,
}: WorkoutDetailHeaderProps) {
  return (
    <div className="bg-slate-800/60 rounded-xl p-6 border border-slate-700">
      <div className="flex items-start justify-between mb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-3xl">
              {WORKOUT_TYPES[workoutDetail.workout_type as keyof typeof WORKOUT_TYPES]?.icon || '🏅'}
            </span>
            <div>
              <h3 className="text-xl font-bold text-white">
                {workoutDetail.workout_name || WORKOUT_TYPES[workoutDetail.workout_type as keyof typeof WORKOUT_TYPES]?.name || '运动'}
              </h3>
              <p className="text-gray-400 text-sm">
                {format(parseISO(workoutDetail.workout_date), 'yyyy年MM月dd日 EEEE', { locale: zhCN })}
                {workoutDetail.start_time && (
                  <span className="ml-2 text-gray-500">
                    {format(parseISO(workoutDetail.start_time), 'HH:mm')}
                    {workoutDetail.end_time && ` - ${format(parseISO(workoutDetail.end_time), 'HH:mm')}`}
                  </span>
                )}
              </p>
            </div>
          </div>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => analyzeMutation.mutate(workoutDetail.id)}
            disabled={analyzeMutation.isPending}
            className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 transition-colors text-sm"
          >
            {analyzeMutation.isPending ? '分析中...' : '✨ AI分析'}
          </button>
          <button
            onClick={() => postAnalysisMutation.mutate({ workoutId: workoutDetail.id, forceRegenerate: false })}
            disabled={postAnalysisMutation.isPending}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors text-sm"
          >
            {postAnalysisMutation.isPending ? '分析中...' : '🔬 科学分析'}
          </button>
          {postAnalysis && postAnalysis.from_cache && (
            <button
              onClick={() => postAnalysisMutation.mutate({ workoutId: workoutDetail.id, forceRegenerate: true })}
              disabled={postAnalysisMutation.isPending}
              className="px-3 py-2 bg-slate-600 text-white rounded-lg hover:bg-slate-700 disabled:opacity-50 transition-colors text-xs"
              title="重新生成分析"
            >
              {postAnalysisMutation.isPending ? '生成中...' : '🔄 重新生成'}
            </button>
          )}
        </div>
      </div>

      {/* Core Data */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-slate-700/50 rounded-lg p-3">
          <div className="text-gray-400 text-xs">时长</div>
          <div className="text-xl font-bold text-white font-mono">
            {formatDuration(workoutDetail.duration_seconds)}
          </div>
        </div>
        {workoutDetail.distance_meters && (
          <div className="bg-slate-700/50 rounded-lg p-3">
            <div className="text-gray-400 text-xs">距离</div>
            <div className="text-xl font-bold text-white">
              {formatDistance(workoutDetail.distance_meters)} <span className="text-sm">km</span>
            </div>
          </div>
        )}
        {workoutDetail.avg_pace_seconds_per_km && (
          <div className="bg-slate-700/50 rounded-lg p-3">
            <div className="text-gray-400 text-xs">平均配速</div>
            <div className="text-xl font-bold text-white font-mono">
              {formatPace(workoutDetail.avg_pace_seconds_per_km)}
            </div>
          </div>
        )}
        <div className="bg-slate-700/50 rounded-lg p-3">
          <div className="text-gray-400 text-xs">消耗</div>
          <div className="text-xl font-bold text-orange-400">
            {workoutDetail.calories || '--'} <span className="text-sm">kcal</span>
          </div>
        </div>
      </div>

      {/* Heart Rate Data */}
      {(workoutDetail.avg_heart_rate || workoutDetail.max_heart_rate) && (
        <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-red-900/30 rounded-lg p-3 border border-red-800/50">
            <div className="text-red-400 text-xs">平均心率</div>
            <div className="text-xl font-bold text-red-400">
              {workoutDetail.avg_heart_rate || '--'} <span className="text-sm">bpm</span>
            </div>
          </div>
          <div className="bg-red-900/30 rounded-lg p-3 border border-red-800/50">
            <div className="text-red-400 text-xs">最高心率</div>
            <div className="text-xl font-bold text-red-400">
              {workoutDetail.max_heart_rate || '--'} <span className="text-sm">bpm</span>
            </div>
          </div>
          {workoutDetail.training_effect_aerobic && (
            <div className="bg-green-900/30 rounded-lg p-3 border border-green-800/50">
              <div className="text-green-400 text-xs">有氧训练效果</div>
              <div className="text-xl font-bold text-green-400">
                {workoutDetail.training_effect_aerobic.toFixed(1)}
              </div>
            </div>
          )}
          {workoutDetail.training_effect_anaerobic && (
            <div className="bg-orange-900/30 rounded-lg p-3 border border-orange-800/50">
              <div className="text-orange-400 text-xs">无氧训练效果</div>
              <div className="text-xl font-bold text-orange-400">
                {workoutDetail.training_effect_anaerobic.toFixed(1)}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
