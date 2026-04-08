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
  const spo2 = todayGarmin?.spo2_avg;

  const cards: JSX.Element[] = [];

  // Sleep - 大卡片，最重要
  if (sleepTotal > 0) {
    cards.push(
      <div key="sleep" className="col-span-2 bg-gradient-to-br from-indigo-50 to-white rounded-2xl p-4 border border-indigo-100 shadow-sm cursor-pointer hover:shadow-md transition-shadow" onClick={() => router.push('/sleep')}>
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-semibold text-indigo-700">😴 睡眠分析</span>
          <span className="text-xs text-indigo-400">{sleepH}h{sleepM > 0 ? `${sleepM}m` : ''}</span>
        </div>
        <div className="flex items-end gap-4">
          <div>
            <div className="text-3xl font-extrabold text-indigo-900">{todayGarmin?.sleep_score || '--'}<span className="text-sm font-medium text-indigo-400 ml-1">分</span></div>
          </div>
          <div className="flex-1 space-y-1.5">
            <div className="flex h-2.5 rounded-full overflow-hidden">
              {sleepDeep > 0 && <div className="bg-indigo-600 rounded-l-full" style={{ width: `${(sleepDeep / sleepTotal) * 100}%` }} title={`深睡 ${Math.round(sleepDeep)}min`} />}
              {sleepRem > 0 && <div className="bg-purple-400" style={{ width: `${(sleepRem / sleepTotal) * 100}%` }} title={`REM ${Math.round(sleepRem)}min`} />}
              {sleepLight > 0 && <div className="bg-blue-200 rounded-r-full" style={{ width: `${(sleepLight / sleepTotal) * 100}%` }} title={`浅睡 ${Math.round(sleepLight)}min`} />}
            </div>
            <div className="flex items-center gap-3 text-[10px] text-indigo-600/70">
              <span>深睡 {Math.round(sleepDeep)}m</span>
              <span>REM {Math.round(sleepRem)}m</span>
              <span>浅睡 {Math.round(sleepLight)}m</span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3 mt-2 text-xs">
          <span className={`font-semibold ${todayGarmin?.hrv && todayGarmin.hrv < 40 ? 'text-red-500' : 'text-indigo-700'}`}>
            HRV {todayGarmin?.hrv || '--'}ms
          </span>
          {spo2 && <span className={`font-semibold ${spo2 < 92 ? 'text-red-500' : 'text-indigo-700'}`}>SpO2 {spo2}%</span>}
        </div>
      </div>
    );
  }

  // Diet
  cards.push(
    <div key="diet" className="bg-white rounded-2xl p-3.5 border border-gray-100 shadow-sm">
      <span className="text-xs font-semibold text-gray-600">🍽️ 饮食</span>
      <div className="mt-1.5">
        <div className="text-2xl font-extrabold text-gray-800">
          {dietToday?.total_calories ? Math.round(dietToday.total_calories) : 0}
          <span className="text-[10px] font-normal text-gray-400 ml-0.5">kcal</span>
        </div>
        {dietToday?.meals_count > 0 && <div className="text-[10px] text-gray-400 mb-1">{dietToday.meals_count}餐</div>}
        <div className="flex gap-2 mt-1.5">
          {[
            { label: '蛋白', val: Math.round(dietToday?.total_protein || 0), color: 'bg-red-400' },
            { label: '碳水', val: Math.round(dietToday?.total_carbs || 0), color: 'bg-amber-400' },
            { label: '脂肪', val: Math.round(dietToday?.total_fat || 0), color: 'bg-green-400' },
          ].map(m => (
            <div key={m.label} className="flex-1 text-center">
              <div className="text-xs font-bold text-gray-700">{m.val}g</div>
              <div className={`h-1 rounded-full mt-0.5 ${m.color} opacity-60`} />
              <div className="text-[9px] text-gray-400 mt-0.5">{m.label}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );

  // Blood Pressure
  if (bpLatest && bpLatest.total_records > 0) {
    const isNormal = bpLatest.normal_count >= bpLatest.total_records * 0.8;
    cards.push(
      <div key="bp" className="bg-white rounded-2xl p-3.5 border border-gray-100 shadow-sm cursor-pointer hover:shadow-md transition-shadow" onClick={() => router.push('/blood-pressure')}>
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-gray-600">🩺 血压</span>
          <span className={`text-[9px] px-1.5 py-0.5 rounded-full font-medium ${isNormal ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'}`}>
            {isNormal ? '正常' : '偏高'}
          </span>
        </div>
        <div className="mt-1.5">
          <div className="text-2xl font-extrabold text-gray-800">
            {Math.round(bpLatest.average_systolic)}<span className="text-sm font-normal text-gray-400">/</span>{Math.round(bpLatest.average_diastolic)}
            <span className="text-[10px] font-normal text-gray-400 ml-1">mmHg</span>
          </div>
          <div className="text-[10px] text-gray-400 mt-0.5">脉搏 {bpLatest.average_pulse ? Math.round(bpLatest.average_pulse) : '--'} · {bpLatest.total_records}次</div>
        </div>
      </div>
    );
  }

  // Weight
  cards.push(
    <div key="weight" className="bg-white rounded-2xl p-3.5 border border-gray-100 shadow-sm">
      <span className="text-xs font-semibold text-gray-600">⚖️ 体重</span>
      <div className="mt-1.5">
        <div className="text-2xl font-extrabold text-gray-800">
          {weightStats?.current_weight || '--'}<span className="text-[10px] font-normal text-gray-400 ml-0.5">kg</span>
        </div>
        {weightStats?.weight_change_30d != null && (
          <div className={`text-[10px] font-semibold mt-0.5 ${weightStats.weight_change_30d > 0 ? 'text-red-500' : 'text-green-600'}`}>
            30天 {weightStats.weight_change_30d > 0 ? '+' : ''}{weightStats.weight_change_30d}kg
          </div>
        )}
      </div>
    </div>
  );

  // Rhinitis
  cards.push(
    <div key="rhinitis" className="bg-white rounded-2xl p-3.5 border border-gray-100 shadow-sm">
      <span className="text-xs font-semibold text-gray-600">👃 鼻炎</span>
      <div className="flex items-center gap-4 mt-1.5">
        <div className="text-center">
          <div className="text-2xl font-extrabold text-gray-800">{rhinitisToday?.sneeze_count || 0}</div>
          <div className="text-[10px] text-gray-400">喷嚏</div>
        </div>
        <div className="text-center">
          <div className="text-2xl font-extrabold text-gray-800">{rhinitisToday?.nasal_wash_count || 0}<span className="text-sm font-normal text-gray-400">/2</span></div>
          <div className="text-[10px] text-gray-400">洗鼻</div>
        </div>
      </div>
    </div>
  );

  return (
    <div className="grid grid-cols-2 lg:grid-cols-3 gap-2.5">
      {cards}
    </div>
  );
}
