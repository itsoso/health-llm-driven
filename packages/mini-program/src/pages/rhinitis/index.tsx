/**
 * 每日打卡页 - 运动锻炼 + 鼻炎追踪
 */
import { useState, useEffect } from 'react';
import { View, Text, Input, Button, Textarea } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { get, post } from '../../services/request';
import './index.scss';

interface CheckinRecord {
  id?: number;
  checkin_date: string;
  // 运动锻炼
  running_distance?: number | null;
  running_duration?: number | null;
  squats_count?: number | null;
  leg_raises_count?: number | null;  // 踢腿次数
  // 鼻炎追踪
  sneeze_count?: number | null;
  sneeze_times?: { time: string; count: number }[];
  nasal_wash_count?: number | null;
  nasal_wash_times?: { time: string; type: 'wash' | 'soak' }[];
  // 其他
  notes?: string | null;
  created_at?: string;
}

type TabType = 'exercise' | 'rhinitis';

export default function Checkin() {
  const [loading, setLoading] = useState(true);
  const [savingRunning, setSavingRunning] = useState(false);
  const [savingSquats, setSavingSquats] = useState(false);
  const [savingLegRaises, setSavingLegRaises] = useState(false);
  const [savingSneeze, setSavingSneeze] = useState(false);
  const [savingNasalWash, setSavingNasalWash] = useState(false);
  const [record, setRecord] = useState<CheckinRecord | null>(null);
  const [activeTab, setActiveTab] = useState<TabType>('exercise');
  
  // 运动表单
  const [runningDistance, setRunningDistance] = useState('');
  const [runningDuration, setRunningDuration] = useState('');
  const [squatsCount, setSquatsCount] = useState('');

  // 鼻炎表单
  const [sneezeCount, setSneezeCount] = useState(0);
  const [sneezeTime, setSneezeTime] = useState('');

  useEffect(() => {
    loadData();
    // 设置当前时间
    const now = new Date();
    setSneezeTime(`${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}`);
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const data = await get<CheckinRecord>('/checkin/me/today').catch(() => null);
      setRecord(data);
      // 填充表单
      if (data) {
        setRunningDistance(data.running_distance?.toString() || '');
        setRunningDuration(data.running_duration?.toString() || '');
        setSquatsCount(data.squats_count?.toString() || '');
      }
    } catch (error) {
      console.error('加载数据失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const today = new Date().toISOString().split('T')[0];

  // 保存跑步
  const handleSaveRunning = async () => {
    if (!runningDistance && !runningDuration) {
      Taro.showToast({ title: '请输入跑步数据', icon: 'none' });
      return;
    }
    setSavingRunning(true);
    try {
      await post('/checkin/', {
        checkin_date: today,
        running_distance: runningDistance ? parseFloat(runningDistance) : null,
        running_duration: runningDuration ? parseInt(runningDuration) : null,
      });
      Taro.showToast({ title: '跑步打卡成功 ✓', icon: 'success' });
      loadData();
    } catch (error) {
      Taro.showToast({ title: '保存失败', icon: 'none' });
    } finally {
      setSavingRunning(false);
    }
  };

  // 保存深蹲
  const handleSaveSquats = async () => {
    if (!squatsCount) {
      Taro.showToast({ title: '请输入深蹲次数', icon: 'none' });
      return;
    }
    setSavingSquats(true);
    try {
      await post('/checkin/', {
        checkin_date: today,
        squats_count: parseInt(squatsCount),
      });
      Taro.showToast({ title: '深蹲打卡成功 ✓', icon: 'success' });
      loadData();
    } catch (error) {
      Taro.showToast({ title: '保存失败', icon: 'none' });
    } finally {
      setSavingSquats(false);
    }
  };

  // 保存踢腿
  const handleSaveLegRaises = async (count: number) => {
    setSavingLegRaises(true);
    try {
      // 累加踢腿次数
      const currentCount = record?.leg_raises_count || 0;
      await post('/checkin/', {
        checkin_date: today,
        leg_raises_count: currentCount + count,
      });
      Taro.showToast({ title: `踢腿+${count}次 ✓`, icon: 'success' });
      loadData();
    } catch (error) {
      Taro.showToast({ title: '保存失败', icon: 'none' });
    } finally {
      setSavingLegRaises(false);
    }
  };

  // 添加喷嚏记录
  const handleAddSneeze = async () => {
    if (sneezeCount <= 0) {
      Taro.showToast({ title: '请输入次数', icon: 'none' });
      return;
    }

    setSavingSneeze(true);
    try {
      const currentTimes = record?.sneeze_times || [];
      const newTimes = [...currentTimes, { time: sneezeTime, count: sneezeCount }];
      const totalCount = newTimes.reduce((sum, t) => sum + t.count, 0);

      await post('/checkin/', {
        checkin_date: today,
        sneeze_count: totalCount,
        sneeze_times: newTimes,
      });

      Taro.showToast({ title: '记录成功', icon: 'success' });
      setSneezeCount(0);
      loadData();
    } catch (error) {
      Taro.showToast({ title: '保存失败', icon: 'none' });
    } finally {
      setSavingSneeze(false);
    }
  };

  // 添加洗鼻记录
  const handleAddNasalWash = async (type: 'wash' | 'soak') => {
    setSavingNasalWash(true);
    try {
      const now = new Date();
      const time = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}`;
      const currentTimes = record?.nasal_wash_times || [];
      const newTimes = [...currentTimes, { time, type }];

      await post('/checkin/', {
        checkin_date: today,
        nasal_wash_count: newTimes.length,
        nasal_wash_times: newTimes,
      });

      Taro.showToast({ title: '记录成功', icon: 'success' });
      loadData();
    } catch (error) {
      Taro.showToast({ title: '保存失败', icon: 'none' });
    } finally {
      setSavingNasalWash(false);
    }
  };

  if (loading) {
    return (
      <View className="checkin-page loading">
        <View className="loading-spinner" />
        <Text className="loading-text">加载中...</Text>
      </View>
    );
  }

  const sneezeTimes = record?.sneeze_times || [];
  const nasalWashTimes = record?.nasal_wash_times || [];

  return (
    <View className="checkin-page">
      {/* Tab 切换 */}
      <View className="tab-bar">
        <View 
          className={`tab-item ${activeTab === 'exercise' ? 'active' : ''}`}
          onClick={() => setActiveTab('exercise')}
        >
          <Text className="tab-icon">💪</Text>
          <Text className="tab-text">运动锻炼</Text>
        </View>
        <View 
          className={`tab-item ${activeTab === 'rhinitis' ? 'active' : ''}`}
          onClick={() => setActiveTab('rhinitis')}
        >
          <Text className="tab-icon">🤧</Text>
          <Text className="tab-text">鼻炎追踪</Text>
        </View>
      </View>

      {/* 运动锻炼 Tab */}
      {activeTab === 'exercise' && (
        <View className="tab-content">
          {/* 今日完成统计 */}
          <View className="today-summary">
            <Text className="summary-title">📊 今日完成</Text>
            <View className="summary-items">
              <View className={`summary-item ${record?.running_distance ? 'done' : ''}`}>
                <Text className="item-icon">🏃</Text>
                <Text className="item-value">
                  {record?.running_distance ? `${record.running_distance}km` : '--'}
                </Text>
              </View>
              <View className={`summary-item ${record?.squats_count ? 'done' : ''}`}>
                <Text className="item-icon">🏋️</Text>
                <Text className="item-value">
                  {record?.squats_count ? `${record.squats_count}次` : '--'}
                </Text>
              </View>
              <View className={`summary-item ${record?.leg_raises_count ? 'done' : ''}`}>
                <Text className="item-icon">🦵</Text>
                <Text className="item-value">
                  {record?.leg_raises_count ? `${record.leg_raises_count}次` : '--'}
                </Text>
              </View>
            </View>
          </View>

          {/* 跑步 */}
          <View className="exercise-card">
            <View className="card-header">
              <Text className="card-icon">🏃</Text>
              <Text className="card-title">跑步</Text>
              {record?.running_distance && <Text className="done-badge">✓</Text>}
            </View>
            <View className="form-row">
              <View className="form-item">
                <Text className="form-label">距离 (km)</Text>
                <Input
                  type="digit"
                  value={runningDistance}
                  onInput={(e) => setRunningDistance(e.detail.value)}
                  placeholder="0.0"
                  className="form-input"
                />
                <View className="quick-btns">
                  <Text className="quick-btn" onClick={() => setRunningDistance('3')}>3</Text>
                  <Text className="quick-btn" onClick={() => setRunningDistance('5')}>5</Text>
                  <Text className="quick-btn" onClick={() => setRunningDistance('10')}>10</Text>
                </View>
              </View>
              <View className="form-item">
                <Text className="form-label">时长 (分钟)</Text>
                <Input
                  type="number"
                  value={runningDuration}
                  onInput={(e) => setRunningDuration(e.detail.value)}
                  placeholder="0"
                  className="form-input"
                />
                <View className="quick-btns">
                  <Text className="quick-btn" onClick={() => setRunningDuration('20')}>20</Text>
                  <Text className="quick-btn" onClick={() => setRunningDuration('30')}>30</Text>
                  <Text className="quick-btn" onClick={() => setRunningDuration('45')}>45</Text>
                </View>
              </View>
            </View>
            <Button 
              className="save-btn green"
              onClick={handleSaveRunning}
              loading={savingRunning}
            >
              保存跑步
            </Button>
          </View>

          {/* 深蹲 */}
          <View className="exercise-card">
            <View className="card-header">
              <Text className="card-icon">🏋️</Text>
              <Text className="card-title">深蹲</Text>
              {record?.squats_count && <Text className="done-badge">✓</Text>}
            </View>
            <View className="form-row single">
              <View className="form-item">
                <Text className="form-label">次数</Text>
                <Input
                  type="number"
                  value={squatsCount}
                  onInput={(e) => setSquatsCount(e.detail.value)}
                  placeholder="0"
                  className="form-input"
                />
                <View className="quick-btns">
                  <Text className="quick-btn" onClick={() => setSquatsCount('30')}>30</Text>
                  <Text className="quick-btn" onClick={() => setSquatsCount('50')}>50</Text>
                  <Text className="quick-btn" onClick={() => setSquatsCount('100')}>100</Text>
                </View>
              </View>
            </View>
            <Button 
              className="save-btn blue"
              onClick={handleSaveSquats}
              loading={savingSquats}
            >
              保存深蹲
            </Button>
          </View>

          {/* 踢腿 */}
          <View className="exercise-card">
            <View className="card-header">
              <Text className="card-icon">🦵</Text>
              <Text className="card-title">踢腿</Text>
              {record?.leg_raises_count && (
                <Text className="count-badge">{record.leg_raises_count}次</Text>
              )}
            </View>
            <Text className="card-desc">点击快速记录踢腿次数（累加）</Text>
            <View className="quick-action-row">
              <Button 
                className="quick-action-btn orange"
                onClick={() => handleSaveLegRaises(40)}
                loading={savingLegRaises}
              >
                +40 次
              </Button>
              <Button 
                className="quick-action-btn purple"
                onClick={() => handleSaveLegRaises(80)}
                loading={savingLegRaises}
              >
                +80 次
              </Button>
            </View>
          </View>
        </View>
      )}

      {/* 鼻炎追踪 Tab */}
      {activeTab === 'rhinitis' && (
        <View className="tab-content">
          {/* 今日统计 */}
          <View className="stats-row">
            <View className="stat-box">
              <Text className="stat-icon">🤧</Text>
              <Text className="stat-value">{record?.sneeze_count || 0}</Text>
              <Text className="stat-label">打喷嚏次数</Text>
            </View>
            <View className="stat-box">
              <Text className="stat-icon">💧</Text>
              <Text className="stat-value">{record?.nasal_wash_count || 0}</Text>
              <Text className="stat-label">洗鼻次数</Text>
            </View>
          </View>

          {/* 打喷嚏记录 */}
          <View className="form-card">
            <Text className="card-title">🤧 打喷嚏记录</Text>
            <View className="input-row">
              <Input
                type="number"
                value={sneezeCount > 0 ? sneezeCount.toString() : ''}
                onInput={(e) => setSneezeCount(parseInt(e.detail.value) || 0)}
                placeholder="次数"
                className="form-input small"
              />
              <Input
                type="text"
                value={sneezeTime}
                onInput={(e) => setSneezeTime(e.detail.value)}
                placeholder="时间"
                className="form-input small"
              />
              <Button 
                className="add-btn" 
                onClick={handleAddSneeze}
                loading={savingSneeze}
              >
                添加
              </Button>
            </View>
            
            {/* 记录列表 */}
            {sneezeTimes.length > 0 && (
              <View className="records-list">
                <Text className="list-title">今日记录</Text>
                <View className="tags">
                  {sneezeTimes.map((item, i) => (
                    <Text key={i} className="tag tag-amber">
                      {item.time} - {item.count}次
                    </Text>
                  ))}
                </View>
              </View>
            )}
          </View>

          {/* 洗鼻记录 */}
          <View className="form-card">
            <Text className="card-title">💧 洗鼻/泡鼻</Text>
            <View className="button-row">
              <Button 
                className="action-btn blue" 
                onClick={() => handleAddNasalWash('wash')}
                loading={savingNasalWash}
              >
                💧 洗鼻
              </Button>
              <Button 
                className="action-btn purple" 
                onClick={() => handleAddNasalWash('soak')}
                loading={savingNasalWash}
              >
                🫧 泡鼻
              </Button>
            </View>

            {/* 记录列表 */}
            {nasalWashTimes.length > 0 && (
              <View className="records-list">
                <Text className="list-title">今日记录</Text>
                <View className="tags">
                  {nasalWashTimes.map((item, i) => (
                    <Text 
                      key={i} 
                      className={`tag ${item.type === 'wash' ? 'tag-blue' : 'tag-purple'}`}
                    >
                      {item.time} - {item.type === 'wash' ? '💧洗鼻' : '🫧泡鼻'}
                    </Text>
                  ))}
                </View>
              </View>
            )}
          </View>
        </View>
      )}

      <View className="bottom-space" />
    </View>
  );
}
