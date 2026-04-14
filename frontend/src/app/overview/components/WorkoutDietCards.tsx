'use client';

import {
  GarminData,
  WorkoutSummary,
  DailyDietSummary,
  MetricCard,
  getWorkoutTypeName,
  getMealTypeName,
} from './types';

interface WorkoutDietCardsProps {
  record: GarminData;
  todayWorkouts: WorkoutSummary[];
  totalWorkoutCalories: number;
  totalWorkoutDuration: number;
  totalWorkoutDistance: number;
  dietData: DailyDietSummary | undefined;
  totalCaloriesOut: number;
  totalCaloriesIn: number;
  energyBalance: number;
  bmrCalories: number;
}

export default function WorkoutDietCards({
  record,
  todayWorkouts,
  totalWorkoutCalories,
  totalWorkoutDuration,
  totalWorkoutDistance,
  dietData,
  totalCaloriesOut,
  totalCaloriesIn,
  energyBalance,
  bmrCalories,
}: WorkoutDietCardsProps) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
      {/* 今日运动 */}
      <MetricCard icon="🏋️" title="今日运动">
        {todayWorkouts.length > 0 ? (
          <div>
            <div className="text-3xl font-bold text-orange-500 mb-1">
              {totalWorkoutCalories.toLocaleString()}
              <span className="text-lg font-normal text-gray-500 ml-1">大卡</span>
            </div>
            <div className="text-sm text-gray-500 mb-3">运动消耗热量</div>

            <div className="flex gap-4 text-sm mb-3">
              <div>
                <span className="text-gray-800 font-medium">
                  {Math.floor(totalWorkoutDuration / 60)}分钟
                </span>
                <span className="text-gray-500 ml-1">时长</span>
              </div>
              {totalWorkoutDistance > 0 && (
                <div>
                  <span className="text-gray-800 font-medium">
                    {(totalWorkoutDistance / 1000).toFixed(2)}km
                  </span>
                  <span className="text-gray-500 ml-1">距离</span>
                </div>
              )}
            </div>

            <div className="space-y-2 max-h-32 overflow-y-auto">
              {todayWorkouts.map((workout) => (
                <div key={workout.id} className="flex justify-between items-center text-sm bg-gray-50 rounded-lg px-3 py-2">
                  <div>
                    <span className="font-medium text-gray-800">
                      {workout.workout_name || getWorkoutTypeName(workout.workout_type)}
                    </span>
                    <span className="text-gray-400 ml-2">
                      {Math.floor((workout.duration_seconds || 0) / 60)}分钟
                    </span>
                  </div>
                  <span className="text-orange-500 font-medium">{workout.calories || 0}卡</span>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="text-center py-4">
            <div className="text-4xl mb-2">🏃‍♂️</div>
            <p className="text-gray-500 text-sm">今日暂无运动记录</p>
            <p className="text-gray-400 text-xs mt-1">记录运动以追踪消耗热量</p>
          </div>
        )}
      </MetricCard>

      {/* 今日饮食 */}
      <MetricCard icon="🍽️" title="今日饮食">
        {dietData && dietData.meals_count > 0 ? (
          <div>
            <div className="text-3xl font-bold text-green-500 mb-1">
              {dietData.total_calories.toLocaleString()}
              <span className="text-lg font-normal text-gray-500 ml-1">大卡</span>
            </div>
            <div className="text-sm text-gray-500 mb-3">摄入热量</div>

            <div className="grid grid-cols-3 gap-2 text-sm mb-3">
              <div className="bg-blue-50 rounded-lg p-2 text-center">
                <div className="font-medium text-blue-600">{dietData.total_protein.toFixed(0)}g</div>
                <div className="text-xs text-gray-500">蛋白质</div>
              </div>
              <div className="bg-yellow-50 rounded-lg p-2 text-center">
                <div className="font-medium text-yellow-600">{dietData.total_carbs.toFixed(0)}g</div>
                <div className="text-xs text-gray-500">碳水</div>
              </div>
              <div className="bg-red-50 rounded-lg p-2 text-center">
                <div className="font-medium text-red-500">{dietData.total_fat.toFixed(0)}g</div>
                <div className="text-xs text-gray-500">脂肪</div>
              </div>
            </div>

            <div className="space-y-1 max-h-24 overflow-y-auto">
              {dietData.meals.map((meal) => (
                <div key={meal.id} className="flex justify-between items-center text-sm">
                  <span className="text-gray-600">
                    {getMealTypeName(meal.meal_type)}
                  </span>
                  <span className="text-green-500 font-medium">{meal.calories || 0}卡</span>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="text-center py-4">
            <div className="text-4xl mb-2">🥗</div>
            <p className="text-gray-500 text-sm">今日暂无饮食记录</p>
            <p className="text-gray-400 text-xs mt-1">记录饮食以追踪摄入热量</p>
          </div>
        )}
      </MetricCard>

      {/* 能量平衡 */}
      <MetricCard icon="⚖️" title="能量平衡">
        <div>
          <div className={`text-3xl font-bold mb-1 ${
            energyBalance > 0 ? 'text-green-500' : energyBalance < 0 ? 'text-red-500' : 'text-gray-500'
          }`}>
            {energyBalance > 0 ? '+' : ''}{energyBalance.toLocaleString()}
            <span className="text-lg font-normal text-gray-500 ml-1">大卡</span>
          </div>
          <div className="text-sm text-gray-500 mb-3">
            {energyBalance > 0 ? '热量盈余' : energyBalance < 0 ? '热量亏损' : '能量平衡'}
          </div>

          <div className="space-y-3">
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-gray-500">总消耗</span>
                <span className="text-red-500 font-medium">{totalCaloriesOut.toLocaleString()} 大卡</span>
              </div>
              <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                <div
                  className="h-full bg-red-400 rounded-full"
                  style={{ width: `${Math.min((totalCaloriesOut / Math.max(totalCaloriesOut, totalCaloriesIn, 1)) * 100, 100)}%` }}
                />
              </div>
              <div className="flex justify-between text-xs text-gray-400 mt-1">
                <span>基础代谢: {bmrCalories}</span>
                <span>活动: {record?.active_calories || 0}</span>
              </div>
            </div>

            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-gray-500">总摄入</span>
                <span className="text-green-500 font-medium">{totalCaloriesIn.toLocaleString()} 大卡</span>
              </div>
              <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                <div
                  className="h-full bg-green-400 rounded-full"
                  style={{ width: `${Math.min((totalCaloriesIn / Math.max(totalCaloriesOut, totalCaloriesIn, 1)) * 100, 100)}%` }}
                />
              </div>
              <div className="flex justify-between text-xs text-gray-400 mt-1">
                <span>{dietData?.meals_count || 0} 餐</span>
                <span>{dietData?.total_protein?.toFixed(0) || 0}g 蛋白质</span>
              </div>
            </div>
          </div>

          <div className="mt-3 text-xs text-gray-400 bg-gray-50 rounded-lg p-2">
            💡 {energyBalance < -500 ? '今日热量亏损较大，注意适当补充' :
                energyBalance > 500 ? '今日热量摄入较多，建议增加运动' :
                '能量摄入适中，继续保持！'}
          </div>
        </div>
      </MetricCard>
    </div>
  );
}
