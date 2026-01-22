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
  getDailySchedule,
  getPreWorkoutGuidance
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
  ScheduleItem,
  PreWorkoutGuidance
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
  workoutGuidance: PreWorkoutGuidance | null;
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
    workoutGuidance: null,
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
      setUserName(storedName || '自由是自律的泡沫用户');
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

      // 如果今日没有运动记录，获取运动指导
      let workoutGuidance: PreWorkoutGuidance | null = null;
      const workouts = workoutsData.status === 'fulfilled' ? workoutsData.value : [];
      if (workouts.length === 0) {
        try {
          workoutGuidance = await getPreWorkoutGuidance('running');
        } catch (e) {
          console.error('获取运动指导失败:', e);
        }
      }

      setHomeData({
        garmin: garminData.status === 'fulfilled' ? garminData.value : null,
        recommendation: recommendationData.status === 'fulfilled' ? recommendationData.value : null,
        rhinitis: rhinitisData.status === 'fulfilled' ? rhinitisData.value : null,
        workouts,
        diet: dietData.status === 'fulfilled' ? dietData.value : null,
        briefing: briefingData.status === 'fulfilled' ? briefingData.value : null,
        aiRecommendation: aiRecData.status === 'fulfilled' ? aiRecData.value : null,
        reminders: remindersData.status === 'fulfilled' ? (remindersData.value?.reminders || []) : [],
        schedule: scheduleData.status === 'fulfilled' ? (scheduleData.value?.schedule || []) : [],
        workoutGuidance,
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

  // 处理打卡跳转
  const handleCheckinAction = (checkinAction: string) => {
    if (!isLoggedIn) {
      Taro.showToast({ title: '请先登录', icon: 'none' });
      return;
    }
    
    const actionMap: Record<string, string> = {
      'water': '/pages/water/index',
      'nasal_wash': '/pages/checkin/index',
      'supplement': '/pages/supplements/index',
      'exercise': '/pages/workout/index',
      'weight': '/pages/weight/index',
      'diet': '/pages/diet/index',
    };
    
    const targetPage = actionMap[checkinAction];
    if (targetPage) {
      if (targetPage.includes('/pages/checkin/') || targetPage.includes('/pages/workout/')) {
        Taro.navigateTo({ url: targetPage });
      } else {
        Taro.switchTab({ url: targetPage });
      }
    } else {
      Taro.showToast({ title: '功能开发中', icon: 'none' });
    }
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
          <Text className="login-title">自由是自律的泡沫</Text>
          <Text className="login-subtitle">个人健康管理助手</Text>
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
            <Text className="feature-text">智能健康分析</Text>
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
          <Text className="loading-text">正在分析...</Text>
        </View>
      )}

      {/* Hero 卡片 - AI 实时建议 */}
      {homeData.aiRecommendation?.primary && (
        <View className="hero-card">
          <View className="hero-glow"></View>
          <View className="hero-content">
            <View className="hero-header">
              <View className="hero-badge">
                <Text className="badge-icon">{homeData.aiRecommendation?.primary?.icon || '🌙'}</Text>
                <Text className="badge-text">今日建议</Text>
              </View>
              <View className="hero-time-box">
                <Text className="hero-time">{currentTime}</Text>
                <Text className="hero-user">Hi, {userName}</Text>
              </View>
            </View>
            <View className="hero-body">
              <Text className="hero-title">{homeData.aiRecommendation?.primary?.title}</Text>
              <Text className="hero-desc">{homeData.aiRecommendation?.primary?.message}</Text>
            </View>
            <View className="hero-actions">
              {/* 主建议的打卡按钮 */}
              {homeData.aiRecommendation?.primary?.checkin_action && (
                <View 
                  className="hero-action-btn primary"
                  onClick={() => handleCheckinAction(homeData.aiRecommendation!.primary!.checkin_action!)}
                >
                  <Text className="btn-check">✓</Text>
                  <Text>立即打卡</Text>
                </View>
              )}
              {/* 次要建议的打卡按钮 */}
              {homeData.aiRecommendation?.secondary?.slice(0, 2).map((item, idx) => {
                const itemText = typeof item === 'string' ? item : item.text;
                const itemAction = typeof item === 'object' ? item.checkin_action : undefined;
                const isPrimary = idx === 0 && !homeData.aiRecommendation?.primary?.checkin_action;
                
                return (
                  <View 
                    key={idx} 
                    className={`hero-action-btn ${isPrimary ? 'primary' : 'secondary'}`}
                    onClick={itemAction ? () => handleCheckinAction(itemAction) : undefined}
                  >
                    {isPrimary && <Text className="btn-check">✓</Text>}
                    <Text>{itemText}</Text>
                  </View>
                );
              })}
            </View>
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
          <View className="quick-item" onClick={() => Taro.navigateTo({ url: '/pages/workout-guidance/index' })}>
            <View className="quick-icon-wrap orange">
              <Image className="quick-icon-img" src={require('../../assets/icons/quick-workout.png')} />
            </View>
            <Text className="quick-label">运动指导</Text>
          </View>
          <View className="quick-item" onClick={() => handleNavToPage('review')}>
            <View className="quick-icon-wrap green">
              <Text className="quick-icon-emoji">📝</Text>
            </View>
            <Text className="quick-label">每日复盘</Text>
          </View>
        </View>
      </View>

      {/* 运动/饮食/能量平衡 三卡片 */}
      <View className="section">
        <View className="energy-cards">
          {/* 今日运动 */}
          <View className="energy-card">
            <View className="energy-header" onClick={() => handleNavToPage('workout')}>
              <Text className="energy-icon">🏃</Text>
              <Text className="energy-title">今日运动</Text>
            </View>
            {homeData.workouts && homeData.workouts.length > 0 ? (
              <View className="energy-content" onClick={() => handleNavToPage('workout')}>
                <View className="workout-list">
                  {homeData.workouts.slice(0, 2).map((w, idx) => (
                    <View key={idx} className="workout-item">
                      <Text className="workout-name">{w.workout_name || w.workout_type}</Text>
                      <Text className="workout-cal">{w.calories || 0}卡</Text>
                    </View>
                  ))}
                </View>
                <View className="workout-total">
                  <Text className="total-label">总消耗</Text>
                  <Text className="total-value orange">
                    {homeData.workouts.reduce((sum, w) => sum + (w.calories || 0), 0)}卡
                  </Text>
                </View>
              </View>
            ) : homeData.workoutGuidance ? (
              <View className="energy-content workout-guidance">
                <View className="guidance-objective">
                  <Text className="guidance-icon">🎯</Text>
                  <Text className="guidance-text">{homeData.workoutGuidance.training_objective}</Text>
                </View>
                <View className="guidance-zones">
                  <Text className="zones-label">心率区间</Text>
                  <View className="zone-item">
                    <Text className="zone-name">燃脂区</Text>
                    <Text className="zone-value">
                      {homeData.workoutGuidance.heart_rate_zones.zone2_fat_burn[0]}-
                      {homeData.workoutGuidance.heart_rate_zones.zone2_fat_burn[1]} bpm
                    </Text>
                  </View>
                </View>
                <View 
                  className="guidance-btn"
                  onClick={(e) => {
                    e.stopPropagation();
                    Taro.navigateTo({ url: '/pages/workout-guidance/index' });
                  }}
                >
                  <Text className="btn-text">查看完整指导 →</Text>
                </View>
              </View>
            ) : (
              <View className="energy-empty" onClick={() => handleNavToPage('workout')}>
                <Text className="empty-icon">🏃‍♂️</Text>
                <Text className="empty-text">今日暂无运动记录</Text>
                <Text className="empty-hint">记录运动以追踪消耗热量</Text>
              </View>
            )}
          </View>

          {/* 今日饮食 */}
          <View className="energy-card" onClick={() => handleQuickNav('diet')}>
            <View className="energy-header">
              <Text className="energy-icon">🍽️</Text>
              <Text className="energy-title">今日饮食</Text>
            </View>
            {homeData.diet && homeData.diet.meals_count > 0 ? (
              <View className="energy-content">
                <View className="diet-calories">
                  <Text className="cal-value green">{homeData.diet.total_calories}</Text>
                  <Text className="cal-unit">大卡</Text>
                </View>
                <Text className="diet-label">摄入热量</Text>
                <View className="nutrient-row">
                  <View className="nutrient-item blue">
                    <Text className="nutrient-value">{homeData.diet.total_protein?.toFixed(0) || 0}g</Text>
                    <Text className="nutrient-name">蛋白质</Text>
                  </View>
                  <View className="nutrient-item yellow">
                    <Text className="nutrient-value">{homeData.diet.total_carbs?.toFixed(0) || 0}g</Text>
                    <Text className="nutrient-name">碳水</Text>
                  </View>
                  <View className="nutrient-item red">
                    <Text className="nutrient-value">{homeData.diet.total_fat?.toFixed(0) || 0}g</Text>
                    <Text className="nutrient-name">脂肪</Text>
                  </View>
                </View>
                <View className="meal-list">
                  {homeData.diet.meals.slice(0, 2).map((m, idx) => (
                    <View key={idx} className="meal-item">
                      <Text className="meal-type">{
                        m.meal_type === 'breakfast' ? '早餐' :
                        m.meal_type === 'lunch' ? '午餐' :
                        m.meal_type === 'dinner' ? '晚餐' : '加餐'
                      }</Text>
                      <Text className="meal-cal">{m.calories || 0}卡</Text>
                    </View>
                  ))}
                </View>
              </View>
            ) : (
              <View className="energy-empty">
                <Text className="empty-icon">🥗</Text>
                <Text className="empty-text">今日暂无饮食记录</Text>
                <Text className="empty-hint">记录饮食以追踪摄入热量</Text>
              </View>
            )}
          </View>

          {/* 能量平衡 */}
          <View className="energy-card">
            <View className="energy-header">
              <Text className="energy-icon">⚖️</Text>
              <Text className="energy-title">能量平衡</Text>
            </View>
            {(() => {
              // 能量差计算：基础代谢消耗 + 锻炼消耗 - 饮食摄入
              const DEFAULT_BMR = 1600; // 默认基础代谢（大卡）
              
              // 计算运动消耗（从workouts数据）
              const workoutCalories = homeData.workouts.reduce((sum, w) => sum + (w.calories || 0), 0);
              
              // 如果有Garmin数据，使用Garmin数据；否则使用默认值+运动数据
              let bmr: number;
              let activeCalories: number;
              let totalOut: number;
              
              if (homeData?.garmin?.calories_total && homeData.garmin.calories_total > 0) {
                // 使用Garmin真实数据
                totalOut = homeData.garmin.calories_total;
                activeCalories = homeData.garmin.active_calories || 0;
                bmr = totalOut - activeCalories;
              } else {
                // Garmin数据为空，使用默认基础代谢 + 运动消耗
                bmr = DEFAULT_BMR;
                activeCalories = workoutCalories;
                totalOut = bmr + activeCalories;
              }
              
              const totalIn = homeData.diet?.total_calories || 0;
              
              // 能量差 = (基础代谢 + 锻炼消耗) - 饮食摄入 = 总消耗 - 总摄入
              // 正数表示有能量差（可以减肥），负数表示能量盈余（会增重）
              const energyDiff = totalOut - totalIn;
              const maxVal = Math.max(totalOut, totalIn, 1);
              
              // 判断是否在创造能量差
              const isCreatingDeficit = energyDiff > 0;
              const deficitAmount = Math.abs(energyDiff);
              
              // 脂肪转换：1kg脂肪 ≈ 7700大卡，1g脂肪 ≈ 7.7大卡
              const KCAL_PER_GRAM_FAT = 7.7;
              const fatGrams = Math.round(deficitAmount / KCAL_PER_GRAM_FAT);
              
              return (
                <View className="energy-content">
                  <View className="balance-value">
                    <Text className={`balance-num ${isCreatingDeficit ? 'green' : 'red'}`}>
                      {isCreatingDeficit ? '-' : '+'}{fatGrams}
                    </Text>
                    <Text className="balance-unit">克脂肪</Text>
                  </View>
                  <Text className={`balance-label ${isCreatingDeficit ? 'green-text' : 'red-text'}`}>
                    {isCreatingDeficit 
                      ? `✓ 能量差 ${deficitAmount.toFixed(0)} 大卡 ≈ 减脂 ${fatGrams}g` 
                      : energyDiff === 0 
                        ? '能量平衡，需要增加运动或减少摄入'
                        : `能量盈余 ${deficitAmount.toFixed(0)} 大卡 ≈ 增脂 ${fatGrams}g`
                    }
                  </Text>
                  
                  {/* 消耗进度条 */}
                  <View className="progress-section">
                    <View className="progress-header">
                      <Text className="progress-label">总消耗</Text>
                      <Text className="progress-value red">{totalOut} 大卡</Text>
                    </View>
                    <View className="progress-bar">
                      <View 
                        className="progress-fill red" 
                        style={{ width: `${Math.min((totalOut / maxVal) * 100, 100)}%` }}
                      />
                    </View>
                    <View className="progress-detail">
                      <Text className="detail-text">
                        基础代谢: {bmr.toFixed(0)} 大卡
                        {!homeData.garmin?.calories_total && ' (默认值)'}
                      </Text>
                      <Text className="detail-text">
                        活动消耗: {activeCalories.toFixed(0)} 大卡
                        {!homeData.garmin?.calories_total && ` (${homeData.workouts.length}次运动)`}
                      </Text>
                    </View>
                  </View>
                  
                  {/* 摄入进度条 */}
                  <View className="progress-section">
                    <View className="progress-header">
                      <Text className="progress-label">总摄入</Text>
                      <Text className="progress-value green">{totalIn} 大卡</Text>
                    </View>
                    <View className="progress-bar">
                      <View 
                        className="progress-fill green" 
                        style={{ width: `${Math.min((totalIn / maxVal) * 100, 100)}%` }}
                      />
                    </View>
                    <View className="progress-detail">
                      <Text className="detail-text">{homeData.diet?.meals_count || 0} 餐</Text>
                      <Text className="detail-text">{homeData.diet?.total_protein?.toFixed(0) || 0}g 蛋白质</Text>
                    </View>
                  </View>
                  
                  {/* 能量差提示 */}
                  {isCreatingDeficit ? (
                    <View className="balance-tip balance-tip-success">
                      <Text className="tip-text">
                        🎯 今日减脂约 {fatGrams}g（{deficitAmount.toFixed(0)}大卡），坚持7天可减约 {Math.round(fatGrams * 7)}g！
                      </Text>
                    </View>
                  ) : energyDiff < 0 ? (
                    <View className="balance-tip balance-tip-warning">
                      <Text className="tip-text">
                        ⚠️ 今日可能增脂 {fatGrams}g，建议增加运动或减少摄入。
                      </Text>
                    </View>
                  ) : (
                    <View className="balance-tip">
                      <Text className="tip-text">
                        💡 能量平衡中，建议增加运动来创造能量差。
                      </Text>
                    </View>
                  )}
                </View>
              );
            })()}
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
                <Text className="data-value">{homeData?.garmin?.total_sleep_duration ? (homeData.garmin.total_sleep_duration / 60).toFixed(1) : '--'}小时</Text>
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
                <Text className="data-value">{homeData?.garmin?.body_battery_most_charged ?? '--'}</Text>
              </View>
              <View className="data-row">
                <View className="dot orange"></View>
                <Text className="data-label">HRV:</Text>
                <Text className="data-value">{homeData.garmin?.hrv ?? '--'} ms</Text>
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
              <Text className="stat-value">{homeData?.garmin?.body_battery_current ?? '--'}</Text>
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
