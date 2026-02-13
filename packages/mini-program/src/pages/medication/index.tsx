/**
 * 用药管理页面
 */
import { useState, useEffect } from 'react';
import { View, Text, ScrollView, Input } from '@tarojs/components';
import Taro from '@tarojs/taro';
import {
  addMedication, getMyMedications, getTodayMedicationStatus,
  logMedication, getMedicationAdherence,
} from '../../services/api';
import type { MedicationItem, MedicationTodayStatus } from '../../types';
import './index.scss';

export default function MedicationPage() {
  const [loading, setLoading] = useState(true);
  const [todayStatus, setTodayStatus] = useState<MedicationTodayStatus[]>([]);
  const [medications, setMedications] = useState<MedicationItem[]>([]);
  const [adherence, setAdherence] = useState<any>(null);
  const [showForm, setShowForm] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [formData, setFormData] = useState({ name: '', dosage: '', frequency: '', timesPerDay: '1', reminderTimes: '', notes: '' });

  useEffect(() => { loadData(); }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      const [statusRes, medsRes, adhRes] = await Promise.allSettled([
        getTodayMedicationStatus(),
        getMyMedications(true),
        getMedicationAdherence(7),
      ]);
      if (statusRes.status === 'fulfilled') setTodayStatus(statusRes.value);
      if (medsRes.status === 'fulfilled') setMedications(medsRes.value);
      if (adhRes.status === 'fulfilled') setAdherence(adhRes.value);
    } catch (e) {
      console.error('加载用药数据失败:', e);
    } finally {
      setLoading(false);
    }
  };

  const handleAdd = async () => {
    if (submitting || !formData.name) {
      Taro.showToast({ title: '请输入药品名称', icon: 'none' });
      return;
    }
    try {
      setSubmitting(true);
      await addMedication({
        name: formData.name,
        dosage: formData.dosage || undefined,
        frequency: formData.frequency || undefined,
        times_per_day: parseInt(formData.timesPerDay) || 1,
        reminder_times: formData.reminderTimes ? formData.reminderTimes.split(',').map(t => t.trim()) : undefined,
        notes: formData.notes || undefined,
      });
      Taro.showToast({ title: '添加成功', icon: 'success' });
      setShowForm(false);
      setFormData({ name: '', dosage: '', frequency: '', timesPerDay: '1', reminderTimes: '', notes: '' });
      loadData();
    } catch (e) {
      Taro.showToast({ title: '添加失败', icon: 'none' });
    } finally {
      setSubmitting(false);
    }
  };

  const handleLog = async (medId: number, time: string, status: string) => {
    try {
      await logMedication({ medication_id: medId, taken_time: time, status });
      Taro.showToast({ title: status === 'taken' ? '已记录' : '已跳过', icon: 'success' });
      loadData();
    } catch (e) {
      Taro.showToast({ title: '记录失败', icon: 'none' });
    }
  };

  if (loading) {
    return (
      <View className="med-page loading">
        <View className="loading-spinner" />
        <Text className="loading-text">加载中...</Text>
      </View>
    );
  }

  return (
    <View className="med-page">
      <ScrollView className="med-scroll" scrollY>
        {/* 依从性概览 */}
        {adherence && (
          <View className="adherence-card">
            <View className="adherence-main">
              <Text className="adherence-rate" style={{
                color: adherence.adherence_rate >= 80 ? '#22c55e' : adherence.adherence_rate >= 50 ? '#eab308' : '#ef4444'
              }}>
                {adherence.adherence_rate}%
              </Text>
              <Text className="adherence-label">7日依从率</Text>
            </View>
            <View className="adherence-stats">
              <View className="stat">
                <Text className="stat-value">{adherence.total_taken}</Text>
                <Text className="stat-label">已服</Text>
              </View>
              <View className="stat">
                <Text className="stat-value">{adherence.total_skipped}</Text>
                <Text className="stat-label">跳过</Text>
              </View>
            </View>
          </View>
        )}

        {/* 今日用药 */}
        <View className="section">
          <Text className="section-title">今日用药</Text>
          {todayStatus.length === 0 ? (
            <View className="empty-state">
              <Text className="empty-text">暂无在服药品</Text>
            </View>
          ) : (
            todayStatus.map((med) => (
              <View key={med.medication_id} className="med-card">
                <View className="med-info">
                  <Text className="med-name">{med.name}</Text>
                  <Text className="med-dosage">{med.dosage || ''}</Text>
                  <Text className="med-progress">{med.taken_count}/{med.total_count}</Text>
                </View>
                <View className="med-actions">
                  {med.reminder_times.map((time, i) => {
                    const logged = med.logs.find(l => l.time === time);
                    return (
                      <View key={i} className="action-row">
                        {logged ? (
                          <View className={`action-badge ${logged.status}`}>
                            <Text>{time} {logged.status === 'taken' ? '已服' : '跳过'}</Text>
                          </View>
                        ) : (
                          <>
                            <View className="action-btn take" onClick={() => handleLog(med.medication_id, time, 'taken')}>
                              <Text>{time} 服用</Text>
                            </View>
                            <View className="action-btn skip" onClick={() => handleLog(med.medication_id, time, 'skipped')}>
                              <Text>跳过</Text>
                            </View>
                          </>
                        )}
                      </View>
                    );
                  })}
                </View>
              </View>
            ))
          )}
        </View>

        {/* 添加按钮 */}
        <View className="add-btn-wrap">
          <View className="add-btn" onClick={() => setShowForm(true)}>
            <Text>+ 添加药品</Text>
          </View>
        </View>

        <View className="bottom-spacer" />
      </ScrollView>

      {/* 添加弹窗 */}
      {showForm && (
        <View className="modal-mask" onClick={() => setShowForm(false)}>
          <View className="modal-content" onClick={(e) => e.stopPropagation()}>
            <Text className="modal-title">添加药品</Text>
            <View className="form-group">
              <Text className="form-label">药品名称 *</Text>
              <Input className="form-input" placeholder="如：布洛芬" value={formData.name}
                onInput={(e) => setFormData({ ...formData, name: e.detail.value })} />
            </View>
            <View className="form-group">
              <Text className="form-label">用量</Text>
              <Input className="form-input" placeholder="如：400mg" value={formData.dosage}
                onInput={(e) => setFormData({ ...formData, dosage: e.detail.value })} />
            </View>
            <View className="form-group">
              <Text className="form-label">频率</Text>
              <Input className="form-input" placeholder="如：每日2次" value={formData.frequency}
                onInput={(e) => setFormData({ ...formData, frequency: e.detail.value })} />
            </View>
            <View className="form-group">
              <Text className="form-label">每日次数</Text>
              <Input className="form-input" type="number" value={formData.timesPerDay}
                onInput={(e) => setFormData({ ...formData, timesPerDay: e.detail.value })} />
            </View>
            <View className="form-group">
              <Text className="form-label">提醒时间（逗号分隔）</Text>
              <Input className="form-input" placeholder="08:00, 20:00" value={formData.reminderTimes}
                onInput={(e) => setFormData({ ...formData, reminderTimes: e.detail.value })} />
            </View>
            <View className="modal-actions">
              <View className="modal-btn cancel" onClick={() => setShowForm(false)}>
                <Text>取消</Text>
              </View>
              <View className={`modal-btn confirm ${submitting ? 'disabled' : ''}`} onClick={handleAdd}>
                <Text>{submitting ? '添加中...' : '添加'}</Text>
              </View>
            </View>
          </View>
        </View>
      )}
    </View>
  );
}
