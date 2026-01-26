/**
 * 饮水记录页面
 */
import { useState, useEffect } from 'react';
import { View, Text, ScrollView } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { quickAddWater, getWaterRecordsByDate, getWaterStats, getWaterRecords } from '../../services/api';
import type { WaterRecord, WaterStats, WaterDailySummary } from '../../types';
import './index.scss';

const QUICK_AMOUNTS = [
  { amount: 200, label: '一杯水', icon: '🥛' },
  { amount: 250, label: '一杯茶', icon: '🍵' },
  { amount: 350, label: '一瓶水', icon: '🧴' },
  { amount: 500, label: '大瓶水', icon: '💧' },
];

function getBeijingToday(): string {
  const now = new Date();
  const utcTime = now.getTime() + now.getTimezoneOffset() * 60 * 1000;
  const beijingTime = new Date(utcTime + 8 * 60 * 60 * 1000);
  const year = beijingTime.getFullYear();
  const month = String(beijingTime.getMonth() + 1).padStart(2, '0');
  const day = String(beijingTime.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export default function WaterPage() {
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [todaySummary, setTodaySummary] = useState<WaterDailySummary | null>(null);
  const [stats, setStats] = useState<WaterStats | null>(null);
  const [recentRecords, setRecentRecords] = useState<WaterRecord[]>([]);
  const today = getBeijingToday();
  const DAILY_GOAL = 2000; // 每日目标 2000ml

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      const [summaryData, statsData, recordsData] = await Promise.allSettled([
        getWaterRecordsByDate(today),
        getWaterStats(7),
        getWaterRecords(50),
      ]);

      if (summaryData.status === 'fulfilled') {
        setTodaySummary(summaryData.value);
      }
      if (statsData.status === 'fulfilled') {
        setStats(statsData.value);
      }
      if (recordsData.status === 'fulfilled') {
        setRecentRecords(recordsData.value);
      }
    } catch (e) {
      console.error('加载数据失败:', e);
    } finally {
      setLoading(false);
    }
  };

  const handleQuickAdd = async (amount: number) => {
    if (submitting) return;
    try {
      setSubmitting(true);
      await quickAddWater(amount);
      Taro.showToast({ title: `已记录 ${amount}ml 💧`, icon: 'success' });
      loadData();
    } catch (e) {
      console.error('添加失败:', e);
      Taro.showToast({ title: '添加失败', icon: 'none' });
    } finally {
      setSubmitting(false);
    }
  };

  const todayAmount = todaySummary?.total_amount || 0;
  const progress = Math.min((todayAmount / DAILY_GOAL) * 100, 100);
  const remaining = Math.max(DAILY_GOAL - todayAmount, 0);

  if (loading) {
    return (
      <View className="water-page loading">
        <View className="loading-spinner" />
        <Text className="loading-text">加载中...</Text>
      </View>
    );
  }

  return (
    <ScrollView className="water-page" scrollY>
      {/* 今日进度卡片 */}
      <View className="progress-card">
        <View className="progress-header">
          <Text className="progress-title">今日饮水</Text>
          <Text className="progress-date">{today}</Text>
        </View>

        <View className="progress-circle-container">
          <View className="progress-circle">
            <View className="progress-fill" style={{ height: `${progress}%` }} />
            <View className="progress-content">
              <Text className="progress-amount">{todayAmount}</Text>
              <Text className="progress-unit">ml</Text>
            </View>
          </View>
        </View>

        <View className="progress-info">
          <View className="info-item">
            <Text className="info-label">目标</Text>
            <Text className="info-value">{DAILY_GOAL}ml</Text>
          </View>
          <View className="info-item">
            <Text className="info-label">完成</Text>
            <Text className="info-value highlight">{progress.toFixed(0)}%</Text>
          </View>
          <View className="info-item">
            <Text className="info-label">还需</Text>
            <Text className="info-value">{remaining}ml</Text>
          </View>
        </View>
      </View>

      {/* 快速添加 */}
      <View className="quick-section">
        <Text className="section-title">快速记录</Text>
        <View className="quick-grid">
          {QUICK_AMOUNTS.map((item) => (
            <View
              key={item.amount}
              className={`quick-btn ${submitting ? 'disabled' : ''}`}
              onClick={() => handleQuickAdd(item.amount)}
            >
              <Text className="quick-icon">{item.icon}</Text>
              <Text className="quick-label">{item.label}</Text>
              <Text className="quick-amount">{item.amount}ml</Text>
            </View>
          ))}
        </View>
      </View>

      {/* 统计 */}
      {stats && (
        <View className="stats-section">
          <Text className="section-title">近7天统计</Text>
          <View className="stats-grid">
            <View className="stat-item">
              <Text className="stat-value">{stats.avg_daily_amount?.toFixed(0) || 0}</Text>
              <Text className="stat-label">日均/ml</Text>
            </View>
            <View className="stat-item">
              <Text className="stat-value">{stats.max_daily_amount || 0}</Text>
              <Text className="stat-label">最高/ml</Text>
            </View>
            <View className="stat-item">
              <Text className="stat-value">{stats.days_meeting_goal || 0}</Text>
              <Text className="stat-label">达标天数</Text>
            </View>
            <View className="stat-item">
              <Text className="stat-value">{stats.total_amount || 0}</Text>
              <Text className="stat-label">总量/ml</Text>
            </View>
          </View>
        </View>
      )}

      {/* 今日记录 */}
      {todaySummary && todaySummary.records && todaySummary.records.length > 0 && (
        <View className="records-section">
          <Text className="section-title">今日记录</Text>
          <View className="records-list">
            {todaySummary.records.map((record, idx) => (
              <View key={record.id || idx} className="record-item">
                <View className="record-left">
                  <Text className="record-time">{record.drink_time?.slice(0, 5) || '--:--'}</Text>
                  <Text className="record-type">{record.drink_type || '水'}</Text>
                </View>
                <Text className="record-amount">+{record.amount}ml</Text>
              </View>
            ))}
          </View>
        </View>
      )}

      {/* 底部间距 */}
      <View className="bottom-spacer" />
    </ScrollView>
  );
}
