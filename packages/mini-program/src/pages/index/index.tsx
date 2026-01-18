/**
 * 首页 - 整合 AI 健康助手
 */
import { useState, useEffect } from 'react';
import { View, Text, Button, Input, ScrollView } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { 
  wechatLogin, 
  getTodayGarminData, 
  getDailyRecommendation, 
  getTodayRhinitis, 
  syncMyGarminData, 
  getTodayWorkouts, 
  getTodayDietSummary,
  getMorningBriefing,
  getAIRecommendation,
  getCurrentReminders,
  getDailySchedule
} from '../../services/api';
import { getToken } from '../../services/request';
import { 
  GarminData, 
  DailyRecommendation, 
  RhinitisRecord, 
  WorkoutSummary, 
  DailyDietSummary, 
  getStressLevel, 
  getSpO2Level,
  MorningBriefing,
  AIRecommendation,
  HealthReminder,
  ScheduleItem
} from '../../types';
import './index.scss';

interface HomeData {
  garmin: GarminData | null;
  recommendation: DailyRecommendation | null;
  rhinitis: RhinitisRecord | null;
  workouts: WorkoutSummary[];
  diet: DailyDietSummary | null;
  // AI 助手数据
  briefing: MorningBriefing | null;
  aiRecommendation: AIRecommendation | null;
  reminders: HealthReminder[];
  schedule: ScheduleItem[];
  loading: boolean;
}

export default function Index() {
  const [loginLoading, setLoginLoading] = useState(false);
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [userName, setUserName] = useState('');
  const [inputNickname, setInputNickname] = useState('');
  const [inputInviteCode, setInputInviteCode] = useState('');
  const [currentTime, setCurrentTime] = useState('');
  const [homeData, setHomeData] = useState<HomeData>({
    garmin: null,
    recommendation: null,
    rhinitis: null,
    workouts: [],
    diet: null,
    briefing: null,
    aiRecommendation: null,
    reminders: [],
    schedule: [],
    loading: false,
  });

  useEffect(() => {
    checkLoginStatus();
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

  Taro.useDidShow(() => {
    const token = getToken();
    if (token) {
      loadHomeData();
    } else {
      checkLoginStatus();
    }
  });

  const checkLoginStatus = async () => {
    const token = getToken();
    setIsLoggedIn(!!token);
    if (token) {
      const storedName = Taro.getStorageSync('user_name');
      setUserName(storedName || '自律靠AI用户');
      loadHomeData();
    }
  };

  const loadHomeData = async () => {
    setHomeData(prev => ({ ...prev, loading: true }));
    
    try {
      const [
        garminData, 
        recommendationData, 
        rhinitisData, 
        workoutsData, 
        dietData,
        briefingData,
        aiRecData,
        remindersData,
        scheduleData
      ] = await Promise.allSettled([
        getTodayGarminData(),
        getDailyRecommendation(),
        getTodayRhinitis(),
        getTodayWorkouts(),
        getTodayDietSummary(),
        getMorningBriefing(),
        getAIRecommendation(),
        getCurrentReminders(),
        getDailySchedule()
      ]);

      setHomeData({
        garmin: garminData.status === 'fulfilled' ? garminData.value : null,
        recommendation: recommendationData.status === 'fulfilled' ? recommendationData.value : null,
        rhinitis: rhinitisData.status === 'fulfilled' ? rhinitisData.value : null,
        workouts: workoutsData.status === 'fulfilled' ? workoutsData.value : [],
        diet: dietData.status === 'fulfilled' ? dietData.value : null,
        briefing: briefingData.status === 'fulfilled' ? briefingData.value : null,
        aiRecommendation: aiRecData.status === 'fulfilled' ? aiRecData.value : null,
        reminders: remindersData.status === 'fulfilled' ? (remindersData.value?.reminders || []) : [],
        schedule: scheduleData.status === 'fulfilled' ? (scheduleData.value?.schedule || []) : [],
        loading: false,
      });
    } catch (error) {
      console.error('[首页] 加载数据异常:', error);
      setHomeData(prev => ({ ...prev, loading: false }));
    }
  };

  const handleLogin = async () => {
    setLoginLoading(true);
    try {
      const result = await wechatLogin(
        inputNickname || undefined, 
        inputInviteCode.trim() || undefined
      );
      
      if (!result.is_approved) {
        Taro.showModal({
          title: '注册成功',
          content: result.message || '请等待管理员审核通过后即可使用',
          showCancel: false,
        });
        setInputNickname('');
        setInputInviteCode('');
        setLoginLoading(false);
        return;
      }

      Taro.showToast({
        title: result.is_new_user ? '欢迎新用户！' : '登录成功',
        icon: 'success',
      });

      setIsLoggedIn(true);
      if (result.nickname) {
        setUserName(result.nickname);
      }
      setInputNickname('');
      setInputInviteCode('');
      loadHomeData();
    } catch (error: any) {
      Taro.showToast({
        title: error.message || '登录失败',
        icon: 'none',
      });
    } finally {
      setLoginLoading(false);
    }
  };

  const handleNavToPage = (page: string) => {
    if (!isLoggedIn) {
      Taro.showToast({ title: '请先登录', icon: 'none' });
      return;
    }
    Taro.navigateTo({ url: `/pages/${page}/index` });
  };

  const handleQuickNav = (page: string) => {
    if (!isLoggedIn) {
      Taro.showToast({ title: '请先登录', icon: 'none' });
      return;
    }
    Taro.switchTab({ url: `/pages/${page}/index` });
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
      routine: '🌅', meal: '🍽️', work: '💼', exercise: '🏃',
      rest: '☕', leisure: '🎮', sleep: '😴',
    };
    return icons[category] || '📌';
  };

  const getCategoryClass = (category: string) => {
    const classes: Record<string, string> = {
      routine: 'cat-routine', meal: 'cat-meal', work: 'cat-work',
      exercise: 'cat-exercise', rest: 'cat-rest', leisure: 'cat-leisure', sleep: 'cat-sleep',
    };
    return classes[category] || 'cat-default';
  };

  // 获取心率状态
  const getHeartRateStatus = () => {
    const hr = homeData.garmin?.resting_heart_rate;
    if (!hr) return { text: '暂无数据', color: '#9CA3AF' };
    if (hr < 60) return { text: '偏低', color: '#3B82F6' };
    if (hr <= 80) return { text: '正常', color: '#10B981' };
    return { text: '偏高', color: '#F59E0B' };
  };

  const hrStatus = getHeartRateStatus();

  // 未登录页面
  if (!isLoggedIn) {
    return (
      <View className="index-page login-page">
        <View className="login-header">
          <Text className="login-title">🏥 健康自律靠AI</Text>
          <Text className="login-subtitle">AI 驱动的个人健康管理助手</Text>
        </View>
        
        <View className="login-card">
          <Input
            className="login-input"
            type="text"
            placeholder="输入您的昵称（可选）"
            value={inputNickname}
            onInput={(e) => setInputNickname(e.detail.value)}
            maxlength={20}
          />
          <Input
            className="login-input"
            type="text"
            placeholder="请输入邀请码（必填）"
            value={inputInviteCode}
            onInput={(e) => setInputInviteCode(e.detail.value.toUpperCase())}
            maxlength={20}
          />
          <Button
            className="login-btn"
            onClick={handleLogin}
            loading={loginLoading}
            disabled={loginLoading}
          >
            {loginLoading ? '登录中...' : '微信一键登录'}
          </Button>
          <Text className="login-tip">
            登录即表示同意《用户协议》和《隐私政策》
          </Text>
        </View>

        <View className="login-features">
          <View className="feature-item">
            <Text className="feature-icon">📊</Text>
            <Text className="feature-text">Garmin 数据同步</Text>
          </View>
          <View className="feature-item">
            <Text className="feature-icon">🤖</Text>
            <Text className="feature-text">AI 健康分析</Text>
          </View>
          <View className="feature-item">
            <Text className="feature-icon">🎯</Text>
            <Text className="feature-text">个性化建议</Text>
          </View>
        </View>
      </View>
    );
  }

  // 已登录 - AI 健康助手首页
  return (
    <ScrollView className="index-page ai-home" scrollY>
      {/* 加载状态 */}
      {homeData.loading && (
        <View className="loading-overlay">
          <View className="loading-spinner"></View>
          <Text className="loading-text">AI 正在分析...</Text>
        </View>
      )}

      {/* AI 实时建议卡片 - Hero */}
      {homeData.aiRecommendation?.primary && (
        <View className="hero-card">
          <View className="hero-glow"></View>
          <View className="hero-content">
            <View className="hero-header">
              <Text className="hero-icon">{homeData.aiRecommendation.primary.icon}</Text>
              <View className="hero-time">
                <Text className="time-value">{currentTime}</Text>
                <Text className="time-greeting">Hi, {userName}</Text>
              </View>
            </View>
            <Text className="hero-title">{homeData.aiRecommendation.primary.title}</Text>
            <Text className="hero-message">{homeData.aiRecommendation.primary.message}</Text>
            {homeData.aiRecommendation.secondary.length > 0 && (
              <View className="hero-tags">
                {homeData.aiRecommendation.secondary.slice(0, 3).map((item, idx) => (
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
      {homeData.reminders.length > 0 && (
        <View className="section reminders-section">
          <View className="section-header">
            <Text className="section-icon">🔔</Text>
            <Text className="section-title">当前提醒</Text>
          </View>
          <View className="reminders-list">
            {homeData.reminders.slice(0, 3).map((reminder, idx) => (
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

      {/* 快捷功能入口 */}
      <View className="section quick-actions">
        <View className="section-header">
          <Text className="section-icon">⚡</Text>
          <Text className="section-title">快捷功能</Text>
        </View>
        <View className="actions-grid">
          <View className="action-item" onClick={() => handleQuickNav('checkin')}>
            <Text className="action-icon">✅</Text>
            <Text className="action-label">每日打卡</Text>
          </View>
          <View className="action-item" onClick={() => handleNavToPage('diet')}>
            <Text className="action-icon">🍽️</Text>
            <Text className="action-label">饮食记录</Text>
          </View>
          <View className="action-item" onClick={() => handleNavToPage('workout')}>
            <Text className="action-icon">🏃</Text>
            <Text className="action-label">运动训练</Text>
          </View>
          <View className="action-item" onClick={() => handleNavToPage('garmin-data')}>
            <Text className="action-icon">📊</Text>
            <Text className="action-label">健康数据</Text>
          </View>
        </View>
      </View>

      {/* 健康简报 */}
      {homeData.briefing && (
        <View className="section briefing-section">
          <View className="section-header">
            <Text className="section-icon">📋</Text>
            <Text className="section-title">健康简报</Text>
          </View>
          <View className="greeting-box">
            <Text className="greeting">{homeData.briefing.greeting}</Text>
          </View>
          <View className="briefing-grid">
            {homeData.briefing.sections.slice(0, 4).map((section, idx) => (
              <View key={idx} className={`briefing-card ${getStatusClass(section.status)}`}>
                <Text className="card-title">{section.title}</Text>
                <View className="card-items">
                  {section.items.slice(0, 2).map((item, itemIdx) => (
                    <Text key={itemIdx} className="card-item">• {item}</Text>
                  ))}
                </View>
              </View>
            ))}
          </View>
        </View>
      )}

      {/* 今日数据概览 */}
      <View className="section stats-section">
        <View className="section-header">
          <Text className="section-icon">📈</Text>
          <Text className="section-title">今日数据</Text>
        </View>
        <View className="stats-grid">
          {/* 心率 */}
          <View className="stat-card" onClick={() => handleNavToPage('heart-rate')}>
            <Text className="stat-icon">❤️</Text>
            <View className="stat-info">
              {homeData.garmin?.resting_heart_rate ? (
                <>
                  <Text className="stat-value">{homeData.garmin.resting_heart_rate}</Text>
                  <Text className="stat-unit">bpm</Text>
                </>
              ) : (
                <Text className="stat-empty">--</Text>
              )}
            </View>
            <Text className="stat-label">静息心率</Text>
          </View>

          {/* 步数 */}
          <View className="stat-card" onClick={() => handleNavToPage('garmin-data')}>
            <Text className="stat-icon">👟</Text>
            <View className="stat-info">
              {homeData.garmin?.steps ? (
                <Text className="stat-value">{homeData.garmin.steps.toLocaleString()}</Text>
              ) : (
                <Text className="stat-empty">--</Text>
              )}
            </View>
            <Text className="stat-label">步数</Text>
          </View>

          {/* 身体电量 */}
          <View className="stat-card" onClick={() => handleNavToPage('garmin-data')}>
            <Text className="stat-icon">🔋</Text>
            <View className="stat-info">
              {(homeData.garmin?.body_battery_current ?? homeData.garmin?.body_battery_most_charged) ? (
                <>
                  <Text className="stat-value">
                    {homeData.garmin?.body_battery_current ?? homeData.garmin?.body_battery_most_charged}
                  </Text>
                  <Text className="stat-unit">
                    /{homeData.garmin?.body_battery_most_charged ?? homeData.garmin?.body_battery_charged ?? 100}
                  </Text>
                </>
              ) : (
                <Text className="stat-empty">--</Text>
              )}
            </View>
            <Text className="stat-label">身体电量</Text>
          </View>

          {/* 压力 */}
          <View className="stat-card" onClick={() => handleNavToPage('garmin-data')}>
            <Text className="stat-icon">😰</Text>
            <View className="stat-info">
              {(homeData.garmin?.stress_level ?? homeData.garmin?.stress_avg) ? (
                <Text className="stat-value">
                  {homeData.garmin?.stress_level ?? homeData.garmin?.stress_avg}
                </Text>
              ) : (
                <Text className="stat-empty">--</Text>
              )}
            </View>
            <Text className="stat-label">压力指数</Text>
          </View>
        </View>
      </View>

      {/* 今日日程 */}
      {homeData.schedule.length > 0 && (
        <View className="section schedule-section">
          <View className="section-header">
            <Text className="section-icon">📅</Text>
            <Text className="section-title">今日日程</Text>
          </View>
          <View className="timeline">
            {homeData.schedule.slice(0, 6).map((item, idx) => (
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

      {/* 刷新区域 */}
      <View className="refresh-area">
        <View 
          className="refresh-btn" 
          onClick={async () => {
            Taro.showLoading({ title: '同步中...' });
            try {
              await syncMyGarminData(1).catch(() => {});
              await new Promise(resolve => setTimeout(resolve, 500));
              await loadHomeData();
              Taro.showToast({ title: '刷新成功', icon: 'success', duration: 1000 });
            } finally {
              Taro.hideLoading();
            }
          }}
        >
          <Text className="refresh-icon">↻</Text>
          <Text className="refresh-text">同步并刷新</Text>
        </View>
      </View>
    </ScrollView>
  );
}
