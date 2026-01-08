/**
 * 鼻炎追踪页
 */
import { useState, useEffect } from 'react';
import { View, Text, Input, Button } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { getTodayRhinitis, saveRhinitisRecord } from '../../services/api';
import type { RhinitisRecord } from '@health-app/shared';
import './index.scss';

export default function Rhinitis() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [record, setRecord] = useState<RhinitisRecord | null>(null);
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
      const data = await getTodayRhinitis();
      setRecord(data);
    } catch (error) {
      console.error('加载数据失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleAddSneeze = async () => {
    if (sneezeCount <= 0) {
      Taro.showToast({ title: '请输入次数', icon: 'none' });
      return;
    }

    setSaving(true);
    try {
      const currentTimes = record?.sneeze_times || [];
      const newTimes = [...currentTimes, { time: sneezeTime, count: sneezeCount }];
      const totalCount = newTimes.reduce((sum, t) => sum + t.count, 0);

      await saveRhinitisRecord({
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

  const handleAddNasalWash = async (type: 'wash' | 'soak') => {
    setSaving(true);
    try {
      const now = new Date();
      const time = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}`;
      const currentTimes = record?.nasal_wash_times || [];
      const newTimes = [...currentTimes, { time, type }];

      await saveRhinitisRecord({
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

  if (loading) {
    return (
      <View className="rhinitis-page loading">
        <Text>加载中...</Text>
      </View>
    );
  }

  const sneezeTimes = record?.sneeze_times || [];
  const nasalWashTimes = record?.nasal_wash_times || [];

  return (
    <View className="rhinitis-page">
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
      <View className="card">
        <Text className="card-title">🤧 打喷嚏记录</Text>
        <View className="input-row">
          <Input
            type="number"
            value={sneezeCount.toString()}
            onInput={(e) => setSneezeCount(parseInt(e.detail.value) || 0)}
            placeholder="次数"
            className="input"
          />
          <Input
            type="text"
            value={sneezeTime}
            onInput={(e) => setSneezeTime(e.detail.value)}
            placeholder="时间"
            className="input"
          />
          <Button 
            className="btn btn-primary" 
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
      <View className="card">
        <Text className="card-title">💧 洗鼻/泡鼻</Text>
        <View className="button-row">
          <Button 
            className="btn btn-blue" 
            onClick={() => handleAddNasalWash('wash')}
            loading={saving}
          >
            💧 洗鼻
          </Button>
          <Button 
            className="btn btn-purple" 
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
  );
}

