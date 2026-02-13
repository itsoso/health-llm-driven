import { useState, useEffect, useMemo } from 'react';
import { View, Text, ScrollView, Picker } from '@tarojs/components';
import Taro from '@tarojs/taro';
import {
  startPeriod, endPeriod, getMyCycles, predictNextPeriod,
  logCycleSymptom, getCycleStats, getCycleCalendar,
} from '../../services/api';
import type { MenstrualCycleItem, CyclePrediction, CycleStats, CycleCalendar } from '../../types';
import './index.scss';

const FLOW_OPTIONS = [
  { value: 'light', label: '少量' },
  { value: 'moderate', label: '适中' },
  { value: 'heavy', label: '大量' },
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

export default function WomensHealthPage() {
  const now = new Date();
  const [loading, setLoading] = useState(true);
  const [cycles, setCycles] = useState<MenstrualCycleItem[]>([]);
  const [prediction, setPrediction] = useState<CyclePrediction | null>(null);
  const [stats, setStats] = useState<CycleStats | null>(null);
  const [calendar, setCalendar] = useState<CycleCalendar | null>(null);

  const [calYear, setCalYear] = useState(now.getFullYear());
  const [calMonth, setCalMonth] = useState(now.getMonth() + 1);

  const [showStartModal, setShowStartModal] = useState(false);
  const [showSymptomModal, setShowSymptomModal] = useState(false);
  const [startDate, setStartDate] = useState(formatDate(now));
  const [flowIntensity, setFlowIntensity] = useState('moderate');
  const [symptomDate, setSymptomDate] = useState(formatDate(now));
  const [symptomType, setSymptomType] = useState('cramps');
  const [severity, setSeverity] = useState(3);
  const [symptomNotes, setSymptomNotes] = useState('');

  function formatDate(d: Date): string {
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  }

  async function fetchData() {
    try {
      setLoading(true);
      const [cyclesData, predData, statsData, calData] = await Promise.all([
        getMyCycles(12),
        predictNextPeriod(),
        getCycleStats(),
        getCycleCalendar(calYear, calMonth),
      ]);
      setCycles(cyclesData);
      setPrediction(predData.prediction || null);
      setStats(statsData);
      setCalendar(calData);
    } catch (e) {
      console.error('[WomensHealth] fetch error:', e);
    } finally {
      setLoading(false);
    }
  }

  async function fetchCalendar() {
    try {
      const data = await getCycleCalendar(calYear, calMonth);
      setCalendar(data);
    } catch (e) {
      console.error('[WomensHealth] calendar error:', e);
    }
  }

  useEffect(() => { fetchData(); }, []);
  useEffect(() => { fetchCalendar(); }, [calYear, calMonth]);

  const activeCycle = cycles.find(c => !c.end_date);

  // Calendar days
  const calendarDays = useMemo(() => {
    const firstDay = new Date(calYear, calMonth - 1, 1).getDay();
    const daysInMonth = new Date(calYear, calMonth, 0).getDate();
    const padding: null[] = Array.from({ length: firstDay }, () => null);
    const days = Array.from({ length: daysInMonth }, (_, i) => i + 1);
    return [...padding, ...days];
  }, [calYear, calMonth]);

  const periodDaysSet = useMemo(() => new Set(calendar?.period_days || []), [calendar]);
  const symptomDaysMap = calendar?.symptom_days || {};

  function prevMonth() {
    if (calMonth === 1) { setCalYear(calYear - 1); setCalMonth(12); }
    else { setCalMonth(calMonth - 1); }
  }

  function nextMonth() {
    if (calMonth === 12) { setCalYear(calYear + 1); setCalMonth(1); }
    else { setCalMonth(calMonth + 1); }
  }

  async function handleStartPeriod() {
    try {
      Taro.showLoading({ title: '保存中...' });
      await startPeriod(startDate, flowIntensity);
      setShowStartModal(false);
      Taro.showToast({ title: '已记录', icon: 'success' });
      fetchData();
    } catch (e) {
      Taro.showToast({ title: '保存失败', icon: 'none' });
    } finally {
      Taro.hideLoading();
    }
  }

  async function handleEndPeriod() {
    if (!activeCycle) return;
    try {
      Taro.showLoading({ title: '保存中...' });
      await endPeriod(activeCycle.id, formatDate(new Date()));
      Taro.showToast({ title: '已记录', icon: 'success' });
      fetchData();
    } catch (e) {
      Taro.showToast({ title: '保存失败', icon: 'none' });
    } finally {
      Taro.hideLoading();
    }
  }

  async function handleLogSymptom() {
    try {
      Taro.showLoading({ title: '保存中...' });
      await logCycleSymptom({
        record_date: symptomDate,
        symptom_type: symptomType,
        severity,
        notes: symptomNotes || undefined,
      });
      setShowSymptomModal(false);
      setSymptomNotes('');
      Taro.showToast({ title: '已记录', icon: 'success' });
      fetchCalendar();
    } catch (e) {
      Taro.showToast({ title: '保存失败', icon: 'none' });
    } finally {
      Taro.hideLoading();
    }
  }

  if (loading) {
    return (
      <View className='wh-page loading'>
        <View className='loading-spinner' />
        <Text className='loading-text'>加载中...</Text>
      </View>
    );
  }

  return (
    <View className='wh-page'>
      <ScrollView scrollY className='wh-scroll'>
        {/* Prediction card */}
        {prediction && (
          <View className='prediction-card'>
            <Text className='card-title'>下次经期预测</Text>
            <View className='predict-row'>
              <View className='predict-item'>
                <Text className='predict-label'>预计开始</Text>
                <Text className='predict-value main'>{prediction.predicted_start}</Text>
              </View>
              <View className='predict-item'>
                <Text className='predict-label'>预计结束</Text>
                <Text className='predict-value'>{prediction.predicted_end}</Text>
              </View>
            </View>
            <View className='predict-row'>
              <View className='predict-item'>
                <Text className='predict-label'>平均周期</Text>
                <Text className='predict-value'>{prediction.avg_cycle_length}天</Text>
              </View>
              {prediction.avg_period_length && (
                <View className='predict-item'>
                  <Text className='predict-label'>平均经期</Text>
                  <Text className='predict-value'>{prediction.avg_period_length}天</Text>
                </View>
              )}
            </View>
          </View>
        )}

        {/* Stats card */}
        {stats && stats.total_cycles > 0 && (
          <View className='stats-card'>
            <View className='stat-item'>
              <Text className='stat-value'>{stats.total_cycles}</Text>
              <Text className='stat-label'>记录周期</Text>
            </View>
            {stats.avg_cycle_length && (
              <View className='stat-item'>
                <Text className='stat-value'>{stats.avg_cycle_length}</Text>
                <Text className='stat-label'>平均周期(天)</Text>
              </View>
            )}
            {stats.avg_period_length && (
              <View className='stat-item'>
                <Text className='stat-value'>{stats.avg_period_length}</Text>
                <Text className='stat-label'>平均经期(天)</Text>
              </View>
            )}
          </View>
        )}

        {/* Calendar */}
        <View className='calendar-card'>
          <View className='calendar-header'>
            <Text className='nav-btn' onClick={prevMonth}>&lt;</Text>
            <Text className='calendar-title'>{calYear}年{calMonth}月</Text>
            <Text className='nav-btn' onClick={nextMonth}>&gt;</Text>
          </View>
          <View className='weekday-row'>
            {['日', '一', '二', '三', '四', '五', '六'].map(d => (
              <Text key={d} className='weekday'>{d}</Text>
            ))}
          </View>
          <View className='days-grid'>
            {calendarDays.map((day, idx) => {
              if (day === null) return <View key={`pad-${idx}`} className='day-cell empty' />;
              const dateStr = `${calYear}-${String(calMonth).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
              const isPeriod = periodDaysSet.has(dateStr);
              const hasSymptom = dateStr in symptomDaysMap;
              const isToday = dateStr === formatDate(new Date());
              return (
                <View key={dateStr} className={`day-cell ${isPeriod ? 'period' : ''} ${isToday ? 'today' : ''}`}>
                  <Text className='day-num'>{day}</Text>
                  {hasSymptom && <View className='symptom-dot' />}
                </View>
              );
            })}
          </View>
          <View className='legend-row'>
            <View className='legend-item'><View className='legend-color period' /><Text className='legend-text'>经期</Text></View>
            <View className='legend-item'><View className='legend-color symptom' /><Text className='legend-text'>有症状</Text></View>
          </View>
        </View>

        {/* Actions */}
        <View className='actions-row'>
          {activeCycle ? (
            <View className='action-btn end' onClick={handleEndPeriod}>
              <Text className='action-text'>结束经期</Text>
            </View>
          ) : (
            <View className='action-btn start' onClick={() => setShowStartModal(true)}>
              <Text className='action-text'>记录经期开始</Text>
            </View>
          )}
          <View className='action-btn symptom' onClick={() => setShowSymptomModal(true)}>
            <Text className='action-text'>记录症状</Text>
          </View>
        </View>

        {/* Recent cycles */}
        {cycles.length > 0 && (
          <View className='section'>
            <Text className='section-title'>最近周期</Text>
            {cycles.slice(0, 6).map(cycle => (
              <View key={cycle.id} className='cycle-item'>
                <View className='cycle-dates'>
                  <Text className='cycle-start'>{cycle.start_date}</Text>
                  {cycle.end_date && <Text className='cycle-sep'>~</Text>}
                  {cycle.end_date && <Text className='cycle-end'>{cycle.end_date}</Text>}
                  {!cycle.end_date && <Text className='cycle-active'>进行中</Text>}
                </View>
                <View className='cycle-meta'>
                  {cycle.period_length && <Text className='cycle-days'>{cycle.period_length}天</Text>}
                  <Text className={`flow-badge ${cycle.flow_intensity}`}>
                    {FLOW_OPTIONS.find(f => f.value === cycle.flow_intensity)?.label || cycle.flow_intensity}
                  </Text>
                </View>
              </View>
            ))}
          </View>
        )}

        <View className='bottom-spacer' />
      </ScrollView>

      {/* Start Period Modal */}
      {showStartModal && (
        <View className='modal-mask'>
          <View className='modal-content'>
            <Text className='modal-title'>记录经期开始</Text>
            <View className='form-group'>
              <Text className='form-label'>日期</Text>
              <Picker mode='date' value={startDate} onChange={e => setStartDate(e.detail.value)}>
                <View className='form-input'>{startDate}</View>
              </Picker>
            </View>
            <View className='form-group'>
              <Text className='form-label'>经量</Text>
              <View className='flow-options'>
                {FLOW_OPTIONS.map(opt => (
                  <View
                    key={opt.value}
                    className={`flow-opt ${flowIntensity === opt.value ? 'active' : ''}`}
                    onClick={() => setFlowIntensity(opt.value)}
                  >
                    <Text className='flow-opt-text'>{opt.label}</Text>
                  </View>
                ))}
              </View>
            </View>
            <View className='modal-actions'>
              <View className='modal-btn cancel' onClick={() => setShowStartModal(false)}>
                <Text>取消</Text>
              </View>
              <View className='modal-btn confirm' onClick={handleStartPeriod}>
                <Text>确认</Text>
              </View>
            </View>
          </View>
        </View>
      )}

      {/* Symptom Modal */}
      {showSymptomModal && (
        <View className='modal-mask'>
          <View className='modal-content'>
            <Text className='modal-title'>记录症状</Text>
            <View className='form-group'>
              <Text className='form-label'>日期</Text>
              <Picker mode='date' value={symptomDate} onChange={e => setSymptomDate(e.detail.value)}>
                <View className='form-input'>{symptomDate}</View>
              </Picker>
            </View>
            <View className='form-group'>
              <Text className='form-label'>症状类型</Text>
              <View className='symptom-options'>
                {SYMPTOM_TYPES.map(s => (
                  <View
                    key={s.value}
                    className={`symptom-opt ${symptomType === s.value ? 'active' : ''}`}
                    onClick={() => setSymptomType(s.value)}
                  >
                    <Text className='symptom-opt-text'>{s.label}</Text>
                  </View>
                ))}
              </View>
            </View>
            <View className='form-group'>
              <Text className='form-label'>严重程度: {severity}</Text>
              <View className='severity-row'>
                {[1, 2, 3, 4, 5].map(v => (
                  <View
                    key={v}
                    className={`severity-btn ${severity === v ? 'active' : ''}`}
                    onClick={() => setSeverity(v)}
                  >
                    <Text>{v}</Text>
                  </View>
                ))}
              </View>
              <View className='severity-labels'>
                <Text className='severity-label'>轻微</Text>
                <Text className='severity-label'>严重</Text>
              </View>
            </View>
            <View className='modal-actions'>
              <View className='modal-btn cancel' onClick={() => setShowSymptomModal(false)}>
                <Text>取消</Text>
              </View>
              <View className='modal-btn confirm' onClick={handleLogSymptom}>
                <Text>记录</Text>
              </View>
            </View>
          </View>
        </View>
      )}
    </View>
  );
}
