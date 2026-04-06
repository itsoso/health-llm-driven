'use client';
import { useRouter } from 'next/navigation';

interface DataGridProps {
  todayGarmin: any;
  dietToday: any;
  bpLatest: any;
  rhinitisToday: any;
  weightStats: any;
}

export default function DataGrid({ todayGarmin, dietToday, bpLatest, rhinitisToday, weightStats }: DataGridProps) {
  const router = useRouter();

  const sleepDeep = todayGarmin?.deep_sleep_duration ? todayGarmin.deep_sleep_duration / 60 : 0;
  const sleepRem = todayGarmin?.rem_sleep_duration ? todayGarmin.rem_sleep_duration / 60 : 0;
  const sleepLight = todayGarmin?.light_sleep_duration ? todayGarmin.light_sleep_duration / 60 : 0;
  const sleepTotal = todayGarmin?.total_sleep_duration ? todayGarmin.total_sleep_duration / 60 : 0;
  const sleepH = Math.floor(sleepTotal);
  const sleepM = Math.round((sleepTotal - sleepH) * 60);

  return (
    <div className="grid grid-cols-2 lg:grid-cols-3 gap-2.5">
      {/* Sleep */}
      {sleepTotal > 0 && (
        <div className="bg-white rounded-xl p-3 border border-gray-100 shadow-sm cursor-pointer" onClick={() => router.push('/sleep')}>
          <div className="flex items-center justify-between mb-1">
            <span className="text-[11px] font-semibold text-gray-600">😴 睡眠</span>
            <span className="text-[10px] text-gray-400">{sleepH}h{sleepM > 0 ? `${sleepM}m` : ''}</span>
          </div>
          <div className="flex h-2 rounded-full overflow-hidden mb-1.5">
            {sleepDeep > 0 && <div className="bg-indigo-600" style={{ width: `${(sleepDeep / sleepTotal) * 100}%` }} />}
            {sleepRem > 0 && <div className="bg-purple-400" style={{ width: `${(sleepRem / sleepTotal) * 100}%` }} />}
            {sleepLight > 0 && <div className="bg-blue-200" style={{ width: `${(sleepLight / sleepTotal) * 100}%` }} />}
          </div>
          <div className="flex items-center gap-2 text-xs">
            <span className="font-bold text-gray-800">{todayGarmin?.sleep_score || '--'}<span className="text-[9px] text-gray-400">分</span></span>
            <span className="text-gray-500">HRV {todayGarmin?.hrv || '--'}</span>
            <span className="text-gray-500">SpO2 {todayGarmin?.spo2_avg || '--'}%</span>
          </div>
        </div>
      )}
      {/* Diet */}
      <div className="bg-white rounded-xl p-3 border border-gray-100 shadow-sm">
        <div className="flex items-center justify-between mb-0.5">
          <span className="text-[11px] font-semibold text-gray-600">🍽️ 饮食</span>
          {dietToday?.meals_count > 0 && <span className="text-[10px] text-gray-400">{dietToday.meals_count}餐</span>}
        </div>
        <div className="text-xl font-bold text-gray-800">{dietToday?.total_calories ? Math.round(dietToday.total_calories) : 0}<span className="text-[10px] font-normal text-gray-400 ml-0.5">kcal</span></div>
        <div className="flex gap-1.5 mt-0.5 text-[9px] text-gray-500">
          <span><span className="text-red-500 font-medium">{Math.round(dietToday?.total_protein || 0)}</span>g 蛋白</span>
          <span><span className="text-amber-500 font-medium">{Math.round(dietToday?.total_carbs || 0)}</span>g 碳水</span>
          <span><span className="text-green-500 font-medium">{Math.round(dietToday?.total_fat || 0)}</span>g 脂肪</span>
        </div>
      </div>
      {/* Blood Pressure */}
      {bpLatest && bpLatest.total_records > 0 && (
        <div className="bg-white rounded-xl p-3 border border-gray-100 shadow-sm cursor-pointer" onClick={() => router.push('/blood-pressure')}>
          <div className="flex items-center justify-between mb-1">
            <span className="text-[11px] font-semibold text-gray-600">🩺 血压</span>
            <span className={`text-[9px] px-1.5 py-0.5 rounded ${bpLatest.normal_count >= bpLatest.total_records * 0.8 ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'}`}>
              {bpLatest.normal_count >= bpLatest.total_records * 0.8 ? '正常' : '偏高'}
            </span>
          </div>
          <div className="text-xl font-bold text-gray-800">{Math.round(bpLatest.average_systolic)}/{Math.round(bpLatest.average_diastolic)} <span className="text-[10px] font-normal text-gray-400">mmHg</span></div>
          <div className="text-[10px] text-gray-400 mt-0.5">脉搏 {bpLatest.average_pulse ? Math.round(bpLatest.average_pulse) : '--'} bpm · {bpLatest.total_records}次记录</div>
        </div>
      )}
      {/* Rhinitis */}
      <div className="bg-white rounded-xl p-3 border border-gray-100 shadow-sm">
        <span className="text-[11px] font-semibold text-gray-600">👃 鼻炎</span>
        <div className="flex items-center gap-3 mt-1.5">
          <div className="text-center">
            <span className="text-xl font-bold text-gray-800">{rhinitisToday?.sneeze_count || 0}</span>
            <span className="text-[10px] text-gray-400 ml-0.5">喷嚏</span>
          </div>
          <div className="text-center">
            <span className="text-xl font-bold text-gray-800">{rhinitisToday?.nasal_wash_count || 0}<span className="text-xs font-normal text-gray-400">/2</span></span>
            <span className="text-[10px] text-gray-400 ml-0.5">洗鼻</span>
          </div>
        </div>
      </div>
      {/* Weight */}
      <div className="bg-white rounded-xl p-3 border border-gray-100 shadow-sm">
        <span className="text-[11px] font-semibold text-gray-600">⚖️ 体重</span>
        <div className="text-xl font-bold text-gray-800 mt-1">{weightStats?.current_weight || '--'}<span className="text-[10px] font-normal text-gray-400 ml-0.5">kg</span></div>
        {weightStats?.weight_change_30d != null && (
          <div className={`text-[10px] font-medium mt-0.5 ${weightStats.weight_change_30d > 0 ? 'text-red-500' : 'text-green-600'}`}>
            30天 {weightStats.weight_change_30d > 0 ? '+' : ''}{weightStats.weight_change_30d}kg
          </div>
        )}
      </div>
    </div>
  );
}
