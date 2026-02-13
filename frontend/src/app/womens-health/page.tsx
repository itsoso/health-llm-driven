'use client';

import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { format, startOfMonth, endOfMonth, eachDayOfInterval, getDay, addMonths, subMonths } from 'date-fns';
import { zhCN } from 'date-fns/locale';
import ProtectedRoute from '@/components/ProtectedRoute';
import { womensHealthApi, MenstrualCycleItem, CyclePrediction, CycleStats, CycleCalendar, CycleSymptomItem } from '@/services/api';

const FLOW_OPTIONS = [
  { value: 'light', label: '少量', color: 'bg-pink-200' },
  { value: 'moderate', label: '适中', color: 'bg-pink-400' },
  { value: 'heavy', label: '大量', color: 'bg-pink-600' },
];

const SYMPTOM_TYPES = [
  { value: 'cramps', label: '痛经' },
  { value: 'headache', label: '头痛' },
  { value: 'bloating', label: '腹胀' },
  { value: 'mood_swing', label: '情绪波动' },
  { value: 'fatigue', label: '疲劳' },
  { value: 'breast_tenderness', label: '乳房胀痛' },
  { value: 'acne', label: '痘痘' },
  { value: 'insomnia', label: '失眠' },
];

function WomensHealthContent() {
  const queryClient = useQueryClient();
  const [currentMonth, setCurrentMonth] = useState(new Date());
  const [showStartModal, setShowStartModal] = useState(false);
  const [showSymptomModal, setShowSymptomModal] = useState(false);
  const [selectedDate, setSelectedDate] = useState(format(new Date(), 'yyyy-MM-dd'));
  const [flowIntensity, setFlowIntensity] = useState('moderate');
  const [symptomForm, setSymptomForm] = useState({ symptom_type: 'cramps', severity: 3, notes: '' });

  const year = currentMonth.getFullYear();
  const month = currentMonth.getMonth() + 1;

  const { data: calendar, isLoading: calLoading } = useQuery({
    queryKey: ['wh-calendar', year, month],
    queryFn: async () => { const r = await womensHealthApi.getCalendar(year, month); return r.data; },
  });

  const { data: cycles } = useQuery({
    queryKey: ['wh-cycles'],
    queryFn: async () => { const r = await womensHealthApi.getCycles(12); return r.data; },
  });

  const { data: prediction } = useQuery({
    queryKey: ['wh-prediction'],
    queryFn: async () => { const r = await womensHealthApi.predict(); return r.data; },
  });

  const { data: stats } = useQuery({
    queryKey: ['wh-stats'],
    queryFn: async () => { const r = await womensHealthApi.getStats(); return r.data; },
  });

  const startMutation = useMutation({
    mutationFn: (data: { start_date: string; flow_intensity: string }) =>
      womensHealthApi.startPeriod(data.start_date, data.flow_intensity),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['wh-calendar'] });
      queryClient.invalidateQueries({ queryKey: ['wh-cycles'] });
      queryClient.invalidateQueries({ queryKey: ['wh-prediction'] });
      queryClient.invalidateQueries({ queryKey: ['wh-stats'] });
      setShowStartModal(false);
    },
  });

  const endMutation = useMutation({
    mutationFn: (data: { cycleId: number; end_date: string }) =>
      womensHealthApi.endPeriod(data.cycleId, data.end_date),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['wh-calendar'] });
      queryClient.invalidateQueries({ queryKey: ['wh-cycles'] });
      queryClient.invalidateQueries({ queryKey: ['wh-prediction'] });
      queryClient.invalidateQueries({ queryKey: ['wh-stats'] });
    },
  });

  const symptomMutation = useMutation({
    mutationFn: (data: { record_date: string; symptom_type: string; severity: number; notes?: string }) =>
      womensHealthApi.logSymptom(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['wh-calendar'] });
      setShowSymptomModal(false);
    },
  });

  // Calendar generation
  const calendarDays = useMemo(() => {
    const start = startOfMonth(currentMonth);
    const end = endOfMonth(currentMonth);
    const days = eachDayOfInterval({ start, end });
    const startDay = getDay(start); // 0=Sunday
    const padding = Array.from({ length: startDay }, (_, i) => null);
    return [...padding, ...days];
  }, [currentMonth]);

  const periodDaysSet = useMemo(() => new Set(calendar?.period_days || []), [calendar]);
  const symptomDaysMap = calendar?.symptom_days || {};

  // Check if there's an active (no end_date) cycle
  const activeCycle = cycles?.find(c => !c.end_date);

  const handleStartPeriod = () => {
    startMutation.mutate({ start_date: selectedDate, flow_intensity: flowIntensity });
  };

  const handleEndPeriod = () => {
    if (activeCycle) {
      endMutation.mutate({ cycleId: activeCycle.id, end_date: format(new Date(), 'yyyy-MM-dd') });
    }
  };

  const handleLogSymptom = () => {
    symptomMutation.mutate({
      record_date: selectedDate,
      symptom_type: symptomForm.symptom_type,
      severity: symptomForm.severity,
      notes: symptomForm.notes || undefined,
    });
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-pink-50 to-purple-50 p-4 md:p-6 space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">女性健康</h1>

      {/* Prediction & Stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {prediction?.prediction && (
          <div className="bg-white rounded-2xl p-5 shadow-sm">
            <h2 className="text-lg font-semibold text-pink-600 mb-3">下次经期预测</h2>
            <div className="space-y-2">
              <div className="flex justify-between">
                <span className="text-gray-500">预计开始</span>
                <span className="font-semibold text-pink-600">{prediction.prediction.predicted_start}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">预计结束</span>
                <span className="font-medium">{prediction.prediction.predicted_end}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">平均周期</span>
                <span className="font-medium">{prediction.prediction.avg_cycle_length}天</span>
              </div>
            </div>
          </div>
        )}

        {stats && stats.total_cycles > 0 && (
          <div className="bg-white rounded-2xl p-5 shadow-sm">
            <h2 className="text-lg font-semibold text-purple-600 mb-3">周期统计</h2>
            <div className="space-y-2">
              <div className="flex justify-between">
                <span className="text-gray-500">记录周期数</span>
                <span className="font-semibold">{stats.total_cycles}</span>
              </div>
              {stats.avg_cycle_length && (
                <div className="flex justify-between">
                  <span className="text-gray-500">平均周期</span>
                  <span className="font-medium">{stats.avg_cycle_length}天</span>
                </div>
              )}
              {stats.avg_period_length && (
                <div className="flex justify-between">
                  <span className="text-gray-500">平均经期</span>
                  <span className="font-medium">{stats.avg_period_length}天</span>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Calendar */}
      <div className="bg-white rounded-2xl p-5 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <button onClick={() => setCurrentMonth(subMonths(currentMonth, 1))} className="p-2 hover:bg-gray-100 rounded-lg">
            &lt;
          </button>
          <h2 className="text-lg font-semibold">
            {format(currentMonth, 'yyyy年M月', { locale: zhCN })}
          </h2>
          <button onClick={() => setCurrentMonth(addMonths(currentMonth, 1))} className="p-2 hover:bg-gray-100 rounded-lg">
            &gt;
          </button>
        </div>

        <div className="grid grid-cols-7 gap-1 text-center text-sm mb-2">
          {['日', '一', '二', '三', '四', '五', '六'].map(d => (
            <div key={d} className="text-gray-400 font-medium py-1">{d}</div>
          ))}
        </div>

        <div className="grid grid-cols-7 gap-1">
          {calendarDays.map((day, idx) => {
            if (!day) return <div key={`pad-${idx}`} />;
            const dateStr = format(day, 'yyyy-MM-dd');
            const isPeriod = periodDaysSet.has(dateStr);
            const hasSymptom = dateStr in symptomDaysMap;
            const isToday = dateStr === format(new Date(), 'yyyy-MM-dd');

            return (
              <button
                key={dateStr}
                onClick={() => setSelectedDate(dateStr)}
                className={`relative p-2 rounded-lg text-sm transition-colors
                  ${isPeriod ? 'bg-pink-400 text-white font-semibold' : ''}
                  ${isToday && !isPeriod ? 'ring-2 ring-pink-300' : ''}
                  ${selectedDate === dateStr ? 'ring-2 ring-purple-500' : ''}
                  ${!isPeriod ? 'hover:bg-pink-50' : ''}
                `}
              >
                {day.getDate()}
                {hasSymptom && (
                  <span className="absolute bottom-0.5 left-1/2 -translate-x-1/2 w-1.5 h-1.5 rounded-full bg-yellow-400" />
                )}
              </button>
            );
          })}
        </div>

        <div className="flex gap-4 mt-4 text-xs text-gray-400">
          <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-pink-400" /> 经期</span>
          <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-full bg-yellow-400" /> 有症状</span>
        </div>
      </div>

      {/* Action buttons */}
      <div className="flex gap-3">
        {activeCycle ? (
          <button
            onClick={handleEndPeriod}
            className="flex-1 py-3 bg-gradient-to-r from-purple-500 to-pink-500 text-white rounded-xl font-semibold text-center shadow-sm"
          >
            结束经期
          </button>
        ) : (
          <button
            onClick={() => setShowStartModal(true)}
            className="flex-1 py-3 bg-gradient-to-r from-pink-500 to-rose-500 text-white rounded-xl font-semibold text-center shadow-sm"
          >
            记录经期开始
          </button>
        )}
        <button
          onClick={() => setShowSymptomModal(true)}
          className="flex-1 py-3 bg-white border-2 border-pink-300 text-pink-600 rounded-xl font-semibold text-center"
        >
          记录症状
        </button>
      </div>

      {/* Recent cycles */}
      {cycles && cycles.length > 0 && (
        <div className="bg-white rounded-2xl p-5 shadow-sm">
          <h2 className="text-lg font-semibold mb-3">最近周期</h2>
          <div className="space-y-3">
            {cycles.slice(0, 6).map(cycle => (
              <div key={cycle.id} className="flex items-center justify-between py-2 border-b border-gray-50 last:border-0">
                <div>
                  <span className="font-medium text-gray-800">{cycle.start_date}</span>
                  {cycle.end_date && <span className="text-gray-400 mx-1">~</span>}
                  {cycle.end_date && <span className="text-gray-600">{cycle.end_date}</span>}
                  {!cycle.end_date && <span className="text-pink-500 ml-2 text-sm">进行中</span>}
                </div>
                <div className="flex items-center gap-3 text-sm">
                  {cycle.period_length && <span className="text-gray-500">{cycle.period_length}天</span>}
                  <span className={`px-2 py-0.5 rounded-full text-xs ${
                    cycle.flow_intensity === 'heavy' ? 'bg-pink-100 text-pink-700' :
                    cycle.flow_intensity === 'moderate' ? 'bg-pink-50 text-pink-500' :
                    'bg-gray-100 text-gray-500'
                  }`}>
                    {FLOW_OPTIONS.find(f => f.value === cycle.flow_intensity)?.label || cycle.flow_intensity}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Start Period Modal */}
      {showStartModal && (
        <div className="fixed inset-0 bg-black/50 flex items-end justify-center z-50">
          <div className="bg-white w-full max-w-lg rounded-t-2xl p-6 space-y-4">
            <h3 className="text-xl font-bold text-center">记录经期开始</h3>
            <div>
              <label className="block text-sm text-gray-600 mb-1">日期</label>
              <input type="date" value={selectedDate} onChange={e => setSelectedDate(e.target.value)}
                className="w-full border rounded-lg p-3" />
            </div>
            <div>
              <label className="block text-sm text-gray-600 mb-2">经量</label>
              <div className="flex gap-3">
                {FLOW_OPTIONS.map(opt => (
                  <button
                    key={opt.value}
                    onClick={() => setFlowIntensity(opt.value)}
                    className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors
                      ${flowIntensity === opt.value ? 'bg-pink-500 text-white' : 'bg-gray-100 text-gray-600'}`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex gap-3 pt-2">
              <button onClick={() => setShowStartModal(false)} className="flex-1 py-3 bg-gray-100 rounded-xl text-gray-600 font-medium">取消</button>
              <button onClick={handleStartPeriod} disabled={startMutation.isPending}
                className="flex-1 py-3 bg-pink-500 text-white rounded-xl font-semibold disabled:opacity-50">
                {startMutation.isPending ? '保存中...' : '确认'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Symptom Modal */}
      {showSymptomModal && (
        <div className="fixed inset-0 bg-black/50 flex items-end justify-center z-50">
          <div className="bg-white w-full max-w-lg rounded-t-2xl p-6 space-y-4">
            <h3 className="text-xl font-bold text-center">记录症状</h3>
            <div>
              <label className="block text-sm text-gray-600 mb-1">日期</label>
              <input type="date" value={selectedDate} onChange={e => setSelectedDate(e.target.value)}
                className="w-full border rounded-lg p-3" />
            </div>
            <div>
              <label className="block text-sm text-gray-600 mb-2">症状类型</label>
              <div className="flex flex-wrap gap-2">
                {SYMPTOM_TYPES.map(s => (
                  <button
                    key={s.value}
                    onClick={() => setSymptomForm(prev => ({ ...prev, symptom_type: s.value }))}
                    className={`px-3 py-1.5 rounded-full text-sm transition-colors
                      ${symptomForm.symptom_type === s.value ? 'bg-purple-500 text-white' : 'bg-gray-100 text-gray-600'}`}
                  >
                    {s.label}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label className="block text-sm text-gray-600 mb-2">严重程度: {symptomForm.severity}</label>
              <input
                type="range" min={1} max={5} value={symptomForm.severity}
                onChange={e => setSymptomForm(prev => ({ ...prev, severity: Number(e.target.value) }))}
                className="w-full accent-purple-500"
              />
              <div className="flex justify-between text-xs text-gray-400">
                <span>轻微</span><span>严重</span>
              </div>
            </div>
            <div>
              <label className="block text-sm text-gray-600 mb-1">备注</label>
              <input
                value={symptomForm.notes}
                onChange={e => setSymptomForm(prev => ({ ...prev, notes: e.target.value }))}
                className="w-full border rounded-lg p-3" placeholder="可选"
              />
            </div>
            <div className="flex gap-3 pt-2">
              <button onClick={() => setShowSymptomModal(false)} className="flex-1 py-3 bg-gray-100 rounded-xl text-gray-600 font-medium">取消</button>
              <button onClick={handleLogSymptom} disabled={symptomMutation.isPending}
                className="flex-1 py-3 bg-purple-500 text-white rounded-xl font-semibold disabled:opacity-50">
                {symptomMutation.isPending ? '保存中...' : '记录'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function WomensHealthPage() {
  return (
    <ProtectedRoute>
      <WomensHealthContent />
    </ProtectedRoute>
  );
}
