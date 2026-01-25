/**
 * AI 健康助手页面 - 优化版
 */
import { View, Text, ScrollView } from '@tarojs/components';
import { useState, useEffect } from 'react';
import Taro from '@tarojs/taro';
import { 
  getMorningBriefing, 
  getAIRecommendation, 
  getCurrentReminders,
  getDailySchedule
} from '../../services/api';
import { 
  MorningBriefing, 
  AIRecommendation, 
  HealthReminder,
  ScheduleItem 
} from '../../types';
import './index.scss';

export default function AIAssistant() {
  const [loading, setLoading] = useState(true);
  const [briefing, setBriefing] = useState<MorningBriefing | null>(null);
  const [recommendation, setRecommendation] = useState<AIRecommendation | null>(null);
  const [reminders, setReminders] = useState<HealthReminder[]>([]);
  const [schedule, setSchedule] = useState<ScheduleItem[]>([]);
  const [currentTime, setCurrentTime] = useState('');

  useEffect(() => {
    loadData();
    // 更新当前时间
    const updateTime = () => {
      const now = new Date();
      setCurrentTime(now.toLocaleTimeString('zh-CN', { 
        hour: '2-digit', 
        minute: '2-digit',
        hour12: false 
      }));
    };
    updateTime();
    const timer = setInterval(updateTime, 60000);
    return () => clearInterval(timer);
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [briefingData, recommendationData, remindersData, scheduleData] = await Promise.all([
        getMorningBriefing(),
        getAIRecommendation(),
        getCurrentReminders(),
        getDailySchedule()
      ]);
      
      setBriefing(briefingData);
      setRecommendation(recommendationData);
      setReminders(remindersData.reminders || []);
      setSchedule(scheduleData.schedule || []);
    } catch (error) {
      console.error('加载数据失败:', error);
      Taro.showToast({ title: '加载失败', icon: 'none' });
    } finally {
      setLoading(false);
    }
  };

  const getStatusClass = (status: string) => {
    switch (status) {
      case 'good': return 'status-good';
      case 'warning': return 'status-warning';
      case 'poor': return 'status-poor';
      default: return 'status-info';
    }
  };

  const getCategoryIcon = (category: string) => {
    const icons: Record<string, string> = {
      routine: '🌅',
      meal: '🍽️',
      work: '💼',
      exercise: '🏃',
      rest: '☕',
      leisure: '🎮',
      sleep: '😴',
    };
    return icons[category] || '📌';
  };

  const getCategoryClass = (category: string) => {
    const classes: Record<string, string> = {
      routine: 'cat-routine',
      meal: 'cat-meal',
      work: 'cat-work',
      exercise: 'cat-exercise',
      rest: 'cat-rest',
      leisure: 'cat-leisure',
      sleep: 'cat-sleep',
    };
    return classes[category] || 'cat-default';
  };

  if (loading) {
    return (
      <View className="ai-assistant loading">
        <View className="loading-container">
        <View className="loading-spinner"></View>
          <Text className="loading-text">正在分析您的健康数据...</Text>
        </View>
      </View>
    );
  }

  return (
    <ScrollView className="ai-assistant" scrollY>
      {/* 实时建议卡片 - 最醒目 */}
      {recommendation && recommendation.primary && (
        <View className="hero-card">
          <View className="hero-glow"></View>
          <View className="hero-content">
            <View className="hero-header">
              <Text className="hero-icon">{recommendation.primary.icon}</Text>
              <View className="hero-time">
                <Text className="time-value">{currentTime}</Text>
              </View>
            </View>
            <Text className="hero-title">{recommendation.primary.title}</Text>
            <Text className="hero-message">{recommendation.primary.message}</Text>
            {recommendation.secondary.length > 0 && (
              <View className="hero-tags">
                {recommendation.secondary.slice(0, 3).map((item, idx) => (
                  <View key={idx} className="hero-tag">
                    <Text>{item}</Text>
                  </View>
                ))}
              </View>
            )}
          </View>
        </View>
      )}

      {/* 当前提醒 */}
      {reminders.length > 0 && (
        <View className="section reminders-section">
          <View className="section-header">
            <Text className="section-icon">🔔</Text>
            <Text className="section-title">当前提醒</Text>
          </View>
          <View className="reminders-list">
          {reminders.map((reminder, idx) => (
              <View key={idx} className="reminder-card">
                <View className="reminder-left">
              <Text className="reminder-emoji">{reminder.title.split(' ')[0]}</Text>
                </View>
                <View className="reminder-center">
                <Text className="reminder-title">{reminder.title.replace(/^[^\s]+\s/, '')}</Text>
                <Text className="reminder-msg">{reminder.message}</Text>
              </View>
                <View className="reminder-right">
              <Text className="reminder-time">{reminder.scheduled_time}</Text>
                </View>
            </View>
          ))}
          </View>
        </View>
      )}

      {/* 健康简报 */}
      {briefing && (
        <View className="section briefing-section">
          <View className="section-header">
            <Text className="section-icon">📋</Text>
            <Text className="section-title">健康简报</Text>
          </View>
          <View className="greeting-box">
          <Text className="greeting">{briefing.greeting}</Text>
          </View>
          <View className="briefing-grid">
          {briefing.sections.map((section, idx) => (
              <View key={idx} className={`briefing-card ${getStatusClass(section.status)}`}>
                <Text className="card-title">{section.title}</Text>
                <View className="card-items">
              {section.items.map((item, itemIdx) => (
                    <Text key={itemIdx} className="card-item">• {item}</Text>
              ))}
                </View>
            </View>
          ))}
          </View>
        </View>
      )}

      {/* 今日日程 */}
      {schedule.length > 0 && (
        <View className="section schedule-section">
          <View className="section-header">
            <Text className="section-icon">📅</Text>
            <Text className="section-title">今日日程</Text>
          </View>
          <View className="timeline">
            {schedule.slice(0, 10).map((item, idx) => (
              <View key={idx} className={`timeline-item ${getCategoryClass(item.category)}`}>
                <View className="timeline-dot">
                  <Text className="dot-icon">{getCategoryIcon(item.category)}</Text>
                </View>
                <View className="timeline-content">
                  <View className="timeline-header">
                    <Text className="timeline-time">{item.time}</Text>
                    <Text className="timeline-activity">{item.activity}</Text>
                  </View>
                  {item.tasks.length > 0 && (
                    <Text className="timeline-tasks">{item.tasks.join(' · ')}</Text>
                  )}
                </View>
              </View>
            ))}
          </View>
        </View>
      )}

      {/* 刷新按钮 */}
      <View className="refresh-area">
      <View className="refresh-btn" onClick={loadData}>
          <Text className="refresh-icon">↻</Text>
          <Text className="refresh-text">刷新数据</Text>
      </View>
      </View>
    </ScrollView>
  );
}
