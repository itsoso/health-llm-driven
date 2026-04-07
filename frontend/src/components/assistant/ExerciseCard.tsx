'use client';

interface ExerciseCardProps {
  exerciseToday: any[];
}

const EXERCISE_ICONS: Record<string, string> = {
  '俯卧撑': '💪',
  '深蹲': '🦵',
  '引体向上': '🏋️',
  '仰卧起坐': '🫁',
  '平板支撑': '🧘',
  '跳绳': '🪢',
  '开合跳': '🤸',
};

export default function ExerciseCard({ exerciseToday }: ExerciseCardProps) {
  // 按类型聚合
  const grouped = exerciseToday.reduce((acc: Record<string, { reps: number; sets: number; duration: number }>, e: any) => {
    const key = e.exercise_type;
    if (!acc[key]) acc[key] = { reps: 0, sets: 0, duration: 0 };
    if (e.reps) acc[key].reps += e.reps;
    if (e.sets) acc[key].sets += e.sets;
    if (e.duration) acc[key].duration += e.duration;
    return acc;
  }, {});

  const types = Object.keys(grouped);
  const totalReps = Object.values(grouped).reduce((sum, g) => sum + g.reps, 0);

  if (types.length === 0) {
    return (
      <div className="bg-white rounded-xl p-3 border border-gray-100 shadow-sm">
        <span className="text-[11px] font-semibold text-gray-600">💪 力量训练</span>
        <div className="text-center py-3 text-gray-400 text-xs">今日暂无记录</div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl p-3 border border-gray-100 shadow-sm">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[11px] font-semibold text-gray-600">💪 力量训练</span>
        {totalReps > 0 && (
          <span className="text-[10px] font-bold text-blue-500">{totalReps} 次</span>
        )}
      </div>
      <div className="space-y-1.5">
        {types.map(type => {
          const g = grouped[type];
          const icon = EXERCISE_ICONS[type] || '🏋️';
          return (
            <div key={type} className="flex items-center justify-between bg-blue-50 rounded-lg px-2.5 py-1.5">
              <span className="text-xs font-medium text-gray-700">
                {icon} {type}
              </span>
              <div className="flex items-center gap-2 text-xs">
                {g.reps > 0 && (
                  <span className="font-bold text-blue-600">{g.reps}<span className="text-[10px] font-normal text-gray-500 ml-0.5">个</span></span>
                )}
                {g.sets > 0 && (
                  <span className="text-gray-500">{g.sets}组</span>
                )}
                {g.duration > 0 && (
                  <span className="text-gray-500">{g.duration}min</span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
