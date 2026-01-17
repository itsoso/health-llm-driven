/**
 * AI 健康助手页面
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
        <View className="loading-spinner"></View>
        <Text className="loading-text">加载 AI 助手...</Text>
      </View>
    );
  }

  return (
    <ScrollView className="ai-assistant" scrollY>
      {/* 头部 */}
      <View className="header">
        <View className="header-left">
          <Text className="header-icon">🤖</Text>
          <View className="header-text">
            <Text className="header-title">AI 健康助手</Text>
            <Text className="header-subtitle">executor.life</Text>
          </View>
        </View>
        <View className="header-time">
          <Text className="time-value">{currentTime}</Text>
          <Text className="time-label">北京时间</Text>
        </View>
      </View>

      {/* 实时建议 - 最重要 */}
      {recommendation && recommendation.primary && (
        <View className="recommendation-card">
          <Text className="rec-icon">{recommendation.primary.icon}</Text>
          <View className="rec-content">
            <Text className="rec-title">{recommendation.primary.title}</Text>
            <Text className="rec-message">{recommendation.primary.message}</Text>
            {recommendation.secondary.length > 0 && (
              <View className="rec-secondary">
                {recommendation.secondary.map((item, idx) => (
                  <Text key={idx} className="sec-item">{item}</Text>
                ))}
              </View>
            )}
          </View>
        </View>
      )}

      {/* 当前提醒 */}
      {reminders.length > 0 && (
        <View className="section reminders-section">
          <Text className="section-title">🔔 当前提醒</Text>
          {reminders.map((reminder, idx) => (
            <View key={idx} className="reminder-item">
              <Text className="reminder-emoji">{reminder.title.split(' ')[0]}</Text>
              <View className="reminder-content">
                <Text className="reminder-title">{reminder.title.replace(/^[^\s]+\s/, '')}</Text>
                <Text className="reminder-msg">{reminder.message}</Text>
              </View>
              <Text className="reminder-time">{reminder.scheduled_time}</Text>
            </View>
          ))}
        </View>
      )}

      {/* 健康简报 */}
      {briefing && (
        <View className="section briefing-section">
          <Text className="section-title">📋 健康简报</Text>
          <Text className="greeting">{briefing.greeting}</Text>
          {briefing.sections.map((section, idx) => (
            <View key={idx} className={`briefing-block ${getStatusClass(section.status)}`}>
              <Text className="block-title">{section.title}</Text>
              {section.items.map((item, itemIdx) => (
                <Text key={itemIdx} className="block-item">• {item}</Text>
              ))}
            </View>
          ))}
        </View>
      )}

      {/* 今日日程 */}
      {schedule.length > 0 && (
        <View className="section schedule-section">
          <Text className="section-title">📅 今日日程</Text>
          <View className="schedule-list">
            {schedule.slice(0, 8).map((item, idx) => (
              <View key={idx} className={`schedule-item ${getCategoryClass(item.category)}`}>
                <Text className="sch-time">{item.time}</Text>
                <View className="sch-content">
                  <Text className="sch-activity">{item.activity}</Text>
                  <Text className="sch-tasks">{item.tasks.join(' · ')}</Text>
                </View>
              </View>
            ))}
          </View>
        </View>
      )}

      {/* 刷新按钮 */}
      <View className="refresh-btn" onClick={loadData}>
        <Text>🔄 刷新数据</Text>
      </View>

      <View className="footer">
        <Text>executor.life · AI 健康助手</Text>
      </View>
    </ScrollView>
  );
}
