/**
 * 每日打卡页 - 集成运动锻炼 + 鼻炎追踪
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
  tai_chi_duration?: number | null;
  ba_duan_jin_duration?: number | null;
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
  const [saving, setSaving] = useState(false);
  const [record, setRecord] = useState<CheckinRecord | null>(null);
  const [activeTab, setActiveTab] = useState<TabType>('exercise');
  
  // 运动表单
  const [exerciseForm, setExerciseForm] = useState({
    running_distance: '',
    running_duration: '',
    squats_count: '',
    tai_chi_duration: '',
    ba_duan_jin_duration: '',
    notes: '',
  });

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
      // 如果有已保存的数据，填充表单
      if (data) {
        setExerciseForm({
          running_distance: data.running_distance?.toString() || '',
          running_duration: data.running_duration?.toString() || '',
          squats_count: data.squats_count?.toString() || '',
          tai_chi_duration: data.tai_chi_duration?.toString() || '',
          ba_duan_jin_duration: data.ba_duan_jin_duration?.toString() || '',
          notes: data.notes || '',
        });
      }
    } catch (error) {
      console.error('加载数据失败:', error);
    } finally {
      setLoading(false);
    }
  };

  // 保存运动打卡
  const handleSaveExercise = async () => {
    setSaving(true);
    try {
      const today = new Date().toISOString().split('T')[0];
      await post('/checkin/', {
        checkin_date: today,
        running_distance: exerciseForm.running_distance ? parseFloat(exerciseForm.running_distance) : null,
        running_duration: exerciseForm.running_duration ? parseInt(exerciseForm.running_duration) : null,
        squats_count: exerciseForm.squats_count ? parseInt(exerciseForm.squats_count) : null,
        tai_chi_duration: exerciseForm.tai_chi_duration ? parseInt(exerciseForm.tai_chi_duration) : null,
        ba_duan_jin_duration: exerciseForm.ba_duan_jin_duration ? parseInt(exerciseForm.ba_duan_jin_duration) : null,
        notes: exerciseForm.notes || null,
      });
      Taro.showToast({ title: '保存成功', icon: 'success' });
      loadData();
    } catch (error) {
      Taro.showToast({ title: '保存失败', icon: 'none' });
    } finally {
      setSaving(false);
    }
  };

  // 添加喷嚏记录
  const handleAddSneeze = async () => {
    if (sneezeCount <= 0) {
      Taro.showToast({ title: '请输入次数', icon: 'none' });
      return;
    }

    setSaving(true);
    try {
      const today = new Date().toISOString().split('T')[0];
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
      setSaving(false);
    }
  };

  // 添加洗鼻记录
  const handleAddNasalWash = async (type: 'wash' | 'soak') => {
    setSaving(true);
    try {
      const today = new Date().toISOString().split('T')[0];
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
      setSaving(false);
    }
  };

  // 快捷输入
  const quickInput = (field: keyof typeof exerciseForm, value: string) => {
    setExerciseForm(prev => ({ ...prev, [field]: value }));
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
  const hasExerciseRecord = record?.running_distance || record?.running_duration || 
                           record?.squats_count || record?.tai_chi_duration || 
                           record?.ba_duan_jin_duration;

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
          {hasExerciseRecord && (
            <View className="done-card">
              <Text className="done-title">✅ 今日已打卡</Text>
              <View className="done-items">
                {record?.running_distance && (
                  <View className="done-item">
                    <Text>🏃 跑步 {record.running_distance}km</Text>
                  </View>
                )}
                {record?.running_duration && (
                  <View className="done-item">
                    <Text>⏱️ {record.running_duration}分钟</Text>
                  </View>
                )}
                {record?.squats_count && (
                  <View className="done-item">
                    <Text>🏋️ 深蹲 {record.squats_count}次</Text>
                  </View>
                )}
                {record?.tai_chi_duration && (
                  <View className="done-item">
                    <Text>🥋 太极拳 {record.tai_chi_duration}分钟</Text>
                  </View>
                )}
                {record?.ba_duan_jin_duration && (
                  <View className="done-item">
                    <Text>🧘 八段锦 {record.ba_duan_jin_duration}分钟</Text>
                  </View>
                )}
              </View>
            </View>
          )}

          {/* 跑步 */}
          <View className="form-card">
            <Text className="card-title">🏃 跑步</Text>
            <View className="form-row">
              <View className="form-item">
                <Text className="form-label">距离 (km)</Text>
                <Input
                  type="digit"
                  value={exerciseForm.running_distance}
                  onInput={(e) => setExerciseForm({...exerciseForm, running_distance: e.detail.value})}
                  placeholder="0.0"
                  className="form-input"
                />
                <View className="quick-btns">
                  <Text className="quick-btn" onClick={() => quickInput('running_distance', '3')}>3km</Text>
                  <Text className="quick-btn" onClick={() => quickInput('running_distance', '5')}>5km</Text>
                  <Text className="quick-btn" onClick={() => quickInput('running_distance', '10')}>10km</Text>
                </View>
              </View>
              <View className="form-item">
                <Text className="form-label">时长 (分钟)</Text>
                <Input
                  type="number"
                  value={exerciseForm.running_duration}
                  onInput={(e) => setExerciseForm({...exerciseForm, running_duration: e.detail.value})}
                  placeholder="0"
                  className="form-input"
                />
                <View className="quick-btns">
                  <Text className="quick-btn" onClick={() => quickInput('running_duration', '20')}>20</Text>
                  <Text className="quick-btn" onClick={() => quickInput('running_duration', '30')}>30</Text>
                  <Text className="quick-btn" onClick={() => quickInput('running_duration', '45')}>45</Text>
                </View>
              </View>
            </View>
          </View>

          {/* 力量训练 */}
          <View className="form-card">
            <Text className="card-title">🏋️ 深蹲</Text>
            <View className="form-row single">
              <View className="form-item">
                <Text className="form-label">次数</Text>
                <Input
                  type="number"
                  value={exerciseForm.squats_count}
                  onInput={(e) => setExerciseForm({...exerciseForm, squats_count: e.detail.value})}
                  placeholder="0"
                  className="form-input"
                />
                <View className="quick-btns">
                  <Text className="quick-btn" onClick={() => quickInput('squats_count', '30')}>30</Text>
                  <Text className="quick-btn" onClick={() => quickInput('squats_count', '50')}>50</Text>
                  <Text className="quick-btn" onClick={() => quickInput('squats_count', '100')}>100</Text>
                </View>
              </View>
            </View>
          </View>

          {/* 传统养生 */}
          <View className="form-card">
            <Text className="card-title">🥋 传统养生</Text>
            <View className="form-row">
              <View className="form-item">
                <Text className="form-label">太极拳 (分钟)</Text>
                <Input
                  type="number"
                  value={exerciseForm.tai_chi_duration}
                  onInput={(e) => setExerciseForm({...exerciseForm, tai_chi_duration: e.detail.value})}
                  placeholder="0"
                  className="form-input"
                />
                <View className="quick-btns">
                  <Text className="quick-btn" onClick={() => quickInput('tai_chi_duration', '15')}>15</Text>
                  <Text className="quick-btn" onClick={() => quickInput('tai_chi_duration', '30')}>30</Text>
                </View>
              </View>
              <View className="form-item">
                <Text className="form-label">八段锦 (分钟)</Text>
                <Input
                  type="number"
                  value={exerciseForm.ba_duan_jin_duration}
                  onInput={(e) => setExerciseForm({...exerciseForm, ba_duan_jin_duration: e.detail.value})}
                  placeholder="0"
                  className="form-input"
                />
                <View className="quick-btns">
                  <Text className="quick-btn" onClick={() => quickInput('ba_duan_jin_duration', '10')}>10</Text>
                  <Text className="quick-btn" onClick={() => quickInput('ba_duan_jin_duration', '20')}>20</Text>
                </View>
              </View>
            </View>
          </View>

          {/* 备注 */}
          <View className="form-card">
            <Text className="card-title">📝 备注</Text>
            <Textarea
              value={exerciseForm.notes}
              onInput={(e) => setExerciseForm({...exerciseForm, notes: e.detail.value})}
              placeholder="今天的感受..."
              className="form-textarea"
              maxlength={200}
            />
          </View>

          {/* 提交按钮 */}
          <Button 
            className="submit-btn"
            onClick={handleSaveExercise}
            loading={saving}
          >
            {saving ? '保存中...' : '✓ 保存打卡'}
          </Button>
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
                loading={saving}
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
                loading={saving}
              >
                💧 洗鼻
              </Button>
              <Button 
                className="action-btn purple" 
                onClick={() => handleAddNasalWash('soak')}
                loading={saving}
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
