/**
 * 首页 - 整合 AI 健康助手 (V2 优化版)
 */
import { useState, useEffect } from 'react';
import { View, Text, Button, Input, ScrollView, Image } from '@tarojs/components';
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

  // 获取日程分类颜色
  const getCategoryColor = (category: string) => {
    const colors: Record<string, string> = {
      routine: 'orange', meal: 'emerald', work: 'blue', exercise: 'red',
      rest: 'indigo', leisure: 'pink', sleep: 'indigo',
    };
    return colors[category] || 'gray';
  };

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

  // 已登录 - AI 健康助手首页 V2
  return (
    <ScrollView className="index-page ai-home" scrollY>
      {/* 加载状态 */}
      {homeData.loading && (
        <View className="loading-overlay">
          <View className="loading-spinner"></View>
          <Text className="loading-text">AI 正在分析...</Text>
        </View>
      )}

      {/* Hero 卡片 - AI 实时建议 */}
      {homeData.aiRecommendation?.primary && (
        <View className="hero-card">
          <View className="hero-glow"></View>
          <View className="hero-content">
            <View className="hero-header">
              <View className="hero-badge">
                <Text className="badge-icon">{homeData.aiRecommendation.primary.icon || '🌙'}</Text>
                <Text className="badge-text">今日建议</Text>
              </View>
              <View className="hero-time-box">
                <Text className="hero-time">{currentTime}</Text>
                <Text className="hero-user">Hi, {userName}</Text>
              </View>
            </View>
            <View className="hero-body">
              <Text className="hero-title">{homeData.aiRecommendation.primary.title}</Text>
              <Text className="hero-desc">{homeData.aiRecommendation.primary.message}</Text>
            </View>
            {homeData.aiRecommendation.secondary.length > 0 && (
              <View className="hero-actions">
                {homeData.aiRecommendation.secondary.slice(0, 2).map((item, idx) => (
                  <View key={idx} className={`hero-action-btn ${idx === 0 ? 'primary' : 'secondary'}`}>
                    {idx === 0 && <Text className="btn-check">✓</Text>}
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
        <View className="section">
          <View className="section-header yellow">
            <Text className="section-icon">🔔</Text>
            <Text className="section-title">当前提醒</Text>
          </View>
          <View className="reminder-card">
            <Text className="reminder-emoji">{homeData.reminders[0].title.split(' ')[0] || '💊'}</Text>
            <View className="reminder-info">
              <Text className="reminder-title">{homeData.reminders[0].title.replace(/^[^\s]+\s/, '')}</Text>
              <Text className="reminder-desc">{homeData.reminders[0].message}</Text>
            </View>
            <View className="reminder-time-badge">
              <Text>{homeData.reminders[0].scheduled_time}</Text>
            </View>
          </View>
        </View>
      )}

      {/* 快捷功能 */}
      <View className="section">
        <View className="section-header yellow">
          <Text className="section-icon">⚡</Text>
          <Text className="section-title">快捷功能</Text>
        </View>
        <View className="quick-grid">
          <View className="quick-item" onClick={() => handleQuickNav('checkin')}>
            <View className="quick-icon-wrap blue">
              <Image className="quick-icon-img" src={require('../../assets/icons/quick-checkin.png')} />
            </View>
            <Text className="quick-label">每日打卡</Text>
          </View>
          <View className="quick-item" onClick={() => handleNavToPage('diet')}>
            <View className="quick-icon-wrap yellow">
              <Image className="quick-icon-img" src={require('../../assets/icons/quick-diet.png')} />
            </View>
            <Text className="quick-label">饮食记录</Text>
          </View>
          <View className="quick-item" onClick={() => handleNavToPage('workout')}>
            <View className="quick-icon-wrap orange">
              <Image className="quick-icon-img" src={require('../../assets/icons/quick-workout.png')} />
            </View>
            <Text className="quick-label">运动训练</Text>
          </View>
          <View className="quick-item" onClick={() => handleNavToPage('garmin-data')}>
            <View className="quick-icon-wrap purple">
              <Image className="quick-icon-img" src={require('../../assets/icons/quick-health.png')} />
            </View>
            <Text className="quick-label">健康数据</Text>
          </View>
        </View>
      </View>

      {/* 健康简报 */}
      <View className="section">
        <View className="section-header gray">
          <Text className="section-icon">📋</Text>
          <Text className="section-title">健康简报</Text>
        </View>
        
        {/* 问候语 */}
        {homeData.briefing && (
          <View className="greeting-card">
            <Text className="greeting-text">{homeData.briefing.greeting} 🌙</Text>
          </View>
        )}
        
        {/* 简报网格 */}
        <View className="briefing-grid">
          {/* 昨晚睡眠 */}
          <View className="briefing-card">
            <View className="briefing-header">
              <Text className="briefing-icon">😴</Text>
              <Text className="briefing-title">昨晚睡眠</Text>
            </View>
            <View className="briefing-content">
              <View className="data-row">
                <View className="dot indigo"></View>
                <Text className="data-label">分数:</Text>
                <Text className="data-value">{homeData.garmin?.sleep_score ?? '--'}分</Text>
              </View>
              <View className="data-row">
                <View className="dot indigo"></View>
                <Text className="data-label">时长:</Text>
                <Text className="data-value">{homeData.garmin?.total_sleep_duration ? (homeData.garmin.total_sleep_duration / 60).toFixed(1) : '--'}小时</Text>
              </View>
            </View>
          </View>

          {/* 身体状态 */}
          <View className="briefing-card">
            <View className="briefing-header">
              <Text className="briefing-icon">⚡</Text>
              <Text className="briefing-title">身体状态</Text>
            </View>
            <View className="briefing-content">
              <View className="data-row">
                <View className="dot orange"></View>
                <Text className="data-label">电量峰值:</Text>
                <Text className="data-value">{homeData.garmin?.body_battery_most_charged ?? '--'}</Text>
              </View>
              <View className="data-row">
                <View className="dot orange"></View>
                <Text className="data-label">静息心率:</Text>
                <Text className="data-value">{homeData.garmin?.resting_heart_rate ?? '--'} bpm</Text>
              </View>
            </View>
          </View>

          {/* 今日目标 */}
          <View className="briefing-card">
            <View className="briefing-header">
              <Text className="briefing-icon">🎯</Text>
              <Text className="briefing-title">今日目标</Text>
            </View>
            <View className="briefing-content">
              <View className="data-row">
                <View className="dot red"></View>
                <Text className="data-label">步数:</Text>
                <Text className="data-value">8000 步</Text>
              </View>
              <View className="data-row">
                <View className="dot red"></View>
                <Text className="data-label">饮水:</Text>
                <Text className="data-value">2000 ml</Text>
              </View>
            </View>
          </View>

          {/* 今日提醒 */}
          <View className="briefing-card">
            <View className="briefing-header">
              <Text className="briefing-icon">📋</Text>
              <Text className="briefing-title">今日提醒</Text>
            </View>
            <View className="briefing-content">
              <View className="data-row">
                <View className="dot blue"></View>
                <Text className="data-text">🫧 记得早晚洗鼻</Text>
              </View>
              <View className="data-row">
                <View className="dot blue"></View>
                <Text className="data-text">💧 保持充足饮水</Text>
              </View>
            </View>
          </View>
        </View>
      </View>

      {/* 今日数据 */}
      <View className="section">
        <View className="section-header gray">
          <Text className="section-icon">📈</Text>
          <Text className="section-title">今日数据</Text>
        </View>
        <View className="stats-grid">
          <View className="stat-card" onClick={() => handleNavToPage('heart-rate')}>
            <Text className="stat-icon red">❤️</Text>
            <View className="stat-value-row">
              <Text className="stat-value">{homeData.garmin?.resting_heart_rate ?? '--'}</Text>
              <Text className="stat-unit">bpm</Text>
            </View>
            <Text className="stat-label">静息心率</Text>
          </View>

          <View className="stat-card" onClick={() => handleNavToPage('garmin-data')}>
            <Text className="stat-icon gray">👟</Text>
            <View className="stat-value-row">
              <Text className="stat-value">{homeData.garmin?.steps?.toLocaleString() ?? '--'}</Text>
            </View>
            <Text className="stat-label">步数</Text>
          </View>

          <View className="stat-card" onClick={() => handleNavToPage('garmin-data')}>
            <Text className="stat-icon green">🔋</Text>
            <View className="stat-value-row">
              <Text className="stat-value">{homeData.garmin?.body_battery_current ?? '--'}</Text>
              <Text className="stat-unit">/100</Text>
            </View>
            <Text className="stat-label">身体电量</Text>
          </View>

          <View className="stat-card" onClick={() => handleNavToPage('garmin-data')}>
            <Text className="stat-icon yellow">
              {(() => {
                const stress = homeData.garmin?.stress_level ?? homeData.garmin?.stress_avg;
                if (!stress) return '😐';
                if (stress <= 25) return '🙂';
                if (stress <= 50) return '😐';
                if (stress <= 75) return '😟';
                return '😰';
              })()}
            </Text>
            <View className="stat-value-row">
              <Text className="stat-value">{homeData.garmin?.stress_level ?? homeData.garmin?.stress_avg ?? '--'}</Text>
            </View>
            <Text className="stat-label">压力指数</Text>
          </View>
        </View>
      </View>

      {/* 今日日程 */}
      {homeData.schedule.length > 0 && (
        <View className="section schedule-section">
          <View className="section-header gray">
            <Text className="section-icon">📅</Text>
            <Text className="section-title">今日日程</Text>
          </View>
          <View className="timeline">
            <View className="timeline-line"></View>
            {homeData.schedule.map((item, idx) => {
              const color = getCategoryColor(item.category);
              return (
                <View key={idx} className={`timeline-item color-${color}`}>
                  <View className={`timeline-dot border-${color}`}></View>
                  <View className={`timeline-card border-left-${color}`}>
                    <View className="card-top">
                      <View className="card-left">
                        <Text className={`card-time text-${color}`}>{item.time}</Text>
                        {item.tasks.length > 0 && (
                          <Text className="card-tasks">{item.tasks.join(' · ')}</Text>
                        )}
                      </View>
                      <View className="card-tag">
                        <Text>{item.activity}</Text>
                      </View>
                    </View>
                  </View>
                </View>
              );
            })}
          </View>
        </View>
      )}

      {/* 刷新按钮 */}
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
