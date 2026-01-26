/**
 * 体重记录页面
 */
import { useState, useEffect } from 'react';
import { View, Text, ScrollView, Input } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { createWeightRecord, getWeightRecords, getWeightStats } from '../../services/api';
import type { WeightRecord, WeightStats } from '../../types';
import './index.scss';

export default function WeightPage() {
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [records, setRecords] = useState<WeightRecord[]>([]);
  const [stats, setStats] = useState<WeightStats | null>(null);
  const [formData, setFormData] = useState({
    weight: '',
    bodyFat: '',
    notes: '',
  });

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      const [recordsData, statsData] = await Promise.allSettled([
        getWeightRecords(90),
        getWeightStats(30),
      ]);

      if (recordsData.status === 'fulfilled') {
        setRecords(recordsData.value);
      }
      if (statsData.status === 'fulfilled') {
        setStats(statsData.value);
      }
    } catch (e) {
      console.error('加载数据失败:', e);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async () => {
    if (submitting) return;
    if (!formData.weight) {
      Taro.showToast({ title: '请输入体重', icon: 'none' });
      return;
    }

    const weight = parseFloat(formData.weight);
    if (isNaN(weight) || weight < 20 || weight > 300) {
      Taro.showToast({ title: '请输入有效体重(20-300kg)', icon: 'none' });
      return;
    }

    try {
      setSubmitting(true);
      await createWeightRecord({
        weight,
        body_fat_percentage: formData.bodyFat ? parseFloat(formData.bodyFat) : null,
        notes: formData.notes || null,
      });
      Taro.showToast({ title: '记录成功', icon: 'success' });
      setShowForm(false);
      setFormData({ weight: '', bodyFat: '', notes: '' });
      loadData();
    } catch (e) {
      console.error('保存失败:', e);
      Taro.showToast({ title: '保存失败', icon: 'none' });
    } finally {
      setSubmitting(false);
    }
  };

  // 获取最近一次记录
  const latestRecord = records.length > 0 ? records[0] : null;

  // 计算变化
  const weightChange = stats?.weight_change;
  const changeText = weightChange
    ? (weightChange > 0 ? `+${weightChange.toFixed(1)}` : weightChange.toFixed(1))
    : '--';
  const changeColor = weightChange
    ? (weightChange > 0 ? 'red' : 'green')
    : '';

  if (loading) {
    return (
      <View className="weight-page loading">
        <View className="loading-spinner" />
        <Text className="loading-text">加载中...</Text>
      </View>
    );
  }

  return (
    <View className="weight-page">
      <ScrollView className="weight-scroll" scrollY>
        {/* 当前体重卡片 */}
        <View className="current-card">
          <View className="current-header">
            <Text className="current-title">当前体重</Text>
            {latestRecord && (
              <Text className="current-date">{latestRecord.record_date}</Text>
            )}
          </View>

          <View className="current-body">
            <View className="current-weight">
              <Text className="weight-value">
                {latestRecord?.weight?.toFixed(1) || '--'}
              </Text>
              <Text className="weight-unit">kg</Text>
            </View>

            {latestRecord?.body_fat_percentage && (
              <View className="body-fat-tag">
                <Text className="fat-label">体脂率</Text>
                <Text className="fat-value">{latestRecord.body_fat_percentage}%</Text>
              </View>
            )}
          </View>

          <View className="add-btn" onClick={() => setShowForm(true)}>
            <Text>+ 记录体重</Text>
          </View>
        </View>

        {/* 统计卡片 */}
        {stats && (
          <View className="stats-card">
            <Text className="card-title">近30天统计</Text>
            <View className="stats-grid">
              <View className="stat-item">
                <Text className={`stat-value ${changeColor}`}>{changeText}</Text>
                <Text className="stat-label">变化/kg</Text>
              </View>
              <View className="stat-item">
                <Text className="stat-value">{stats.lowest_weight?.toFixed(1) || '--'}</Text>
                <Text className="stat-label">最低/kg</Text>
              </View>
              <View className="stat-item">
                <Text className="stat-value">{stats.highest_weight?.toFixed(1) || '--'}</Text>
                <Text className="stat-label">最高/kg</Text>
              </View>
              <View className="stat-item">
                <Text className="stat-value">{stats.total_records || 0}</Text>
                <Text className="stat-label">记录次数</Text>
              </View>
            </View>
          </View>
        )}

        {/* 历史记录 */}
        <View className="history-section">
          <Text className="card-title">历史记录</Text>
          {records.length > 0 ? (
            <View className="history-list">
              {records.slice(0, 30).map((record, idx) => {
                // 计算与上一条的差值
                const prevRecord = records[idx + 1];
                const diff = prevRecord
                  ? record.weight - prevRecord.weight
                  : null;
                const diffText = diff !== null
                  ? (diff > 0 ? `+${diff.toFixed(1)}` : diff.toFixed(1))
                  : '';
                const diffColor = diff !== null
                  ? (diff > 0 ? 'red' : diff < 0 ? 'green' : '')
                  : '';

                return (
                  <View key={record.id} className="history-item">
                    <View className="history-left">
                      <Text className="history-date">{record.record_date}</Text>
                      {record.body_fat_percentage && (
                        <Text className="history-fat">体脂 {record.body_fat_percentage}%</Text>
                      )}
                    </View>
                    <View className="history-right">
                      <Text className="history-weight">{record.weight.toFixed(1)} kg</Text>
                      {diffText && (
                        <Text className={`history-diff ${diffColor}`}>{diffText}</Text>
                      )}
                    </View>
                  </View>
                );
              })}
            </View>
          ) : (
            <View className="empty-state">
              <Text className="empty-icon">📊</Text>
              <Text className="empty-text">暂无记录</Text>
            </View>
          )}
        </View>

        <View className="bottom-spacer" />
      </ScrollView>

      {/* 录入弹窗 */}
      {showForm && (
        <View className="modal-mask" onClick={() => setShowForm(false)}>
          <View className="modal-content" onClick={(e) => e.stopPropagation()}>
            <Text className="modal-title">记录体重</Text>

            <View className="form-group">
              <Text className="form-label">体重 (kg) *</Text>
              <Input
                className="form-input"
                type="digit"
                placeholder="请输入体重"
                value={formData.weight}
                onInput={(e) => setFormData({ ...formData, weight: e.detail.value })}
              />
            </View>

            <View className="form-group">
              <Text className="form-label">体脂率 (%)</Text>
              <Input
                className="form-input"
                type="digit"
                placeholder="选填"
                value={formData.bodyFat}
                onInput={(e) => setFormData({ ...formData, bodyFat: e.detail.value })}
              />
            </View>

            <View className="form-group">
              <Text className="form-label">备注</Text>
              <Input
                className="form-input"
                type="text"
                placeholder="选填"
                value={formData.notes}
                onInput={(e) => setFormData({ ...formData, notes: e.detail.value })}
              />
            </View>

            <View className="modal-actions">
              <View className="modal-btn cancel" onClick={() => setShowForm(false)}>
                <Text>取消</Text>
              </View>
              <View
                className={`modal-btn confirm ${submitting ? 'disabled' : ''}`}
                onClick={handleSubmit}
              >
                <Text>{submitting ? '保存中...' : '保存'}</Text>
              </View>
            </View>
          </View>
        </View>
      )}
    </View>
  );
}
