/**
 * 首页 - 整合 AI 健康助手 (V2 优化版 + 性能监控)
 */
import { useState, useEffect } from 'react';
import { View, Text, Button, Input, ScrollView, Image } from '@tarojs/components';
import Taro from '@tarojs/taro';
import {
  wechatLogin,
  syncMyGarminData,
  quickAddWater
} from '../../services/api';
import { 
  getTodayGarminDataCached,
  getDailyRecommendationCached,
  getTodayRhinitisCached,
  getTodayWorkoutsCached,
  getTodayDietSummaryCached,
  getMorningBriefingCached,
  getAIRecommendationCached,
  getCurrentRemindersCached,
  getDailyScheduleCached,
  getPreWorkoutGuidanceCached,
  clearHomePageCache
} from '../../services/cachedApi';
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
import { performanceMonitor, pagePerformance } from '../../utils/performance';
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
  const [scheduleExpanded, setScheduleExpanded] = useState(false);
  const SCHEDULE_DEFAULT_COUNT = 5; // 默认显示5项日程
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
    // 仅处理时间更新
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
    // 性能监控：页面显示
    pagePerformance.pageStart('首页');
    
    // 统一在这里处理登录检查和数据加载
    checkLoginStatus();
  });

  const checkLoginStatus = async () => {
    const token = getToken();
    setIsLoggedIn(!!token);
    if (token) {
      const storedName = Taro.getStorageSync('user_name');
      setUserName(storedName || '自由是自律的泡沫用户');
      // loadHomeData 内部已经有防重复逻辑
      loadHomeData();
    }
  };

  // 处理提醒点击，跳转到对应打卡页面
  const handleReminderClick = async (reminder: HealthReminder) => {
    try {
      // 喝水提醒：直接调用 API 快速记录（与 Web 端保持一致）
      if (reminder.type === 'drink_water') {
        Taro.showLoading({ title: '记录中...' });
        try {
          await quickAddWater(250); // 默认一杯水 250ml
          Taro.hideLoading();
          Taro.showToast({
            title: '已记录 250ml 💧',
            icon: 'success',
            duration: 2000
          });
          // 刷新提醒列表
          const newReminders = await getCurrentRemindersCached();
          setHomeData(prev => ({
            ...prev,
            reminders: newReminders?.reminders || []
          }));
        } catch (e) {
          Taro.hideLoading();
          console.error('[喝水打卡] 失败:', e);
          Taro.showToast({
            title: '记录失败，请重试',
            icon: 'none',
            duration: 2000
          });
        }
        return;
      }

      const typeToPageMap: Record<string, string> = {
        'nasal_wash': '/pages/rhinitis/index',     // 洗鼻 → 鼻炎记录页
        'supplement': '/pages/supplements/index',  // 补剂 → 补剂记录页
        'exercise': '/pages/workout/index',        // 运动 → 运动记录页
        'weigh': '/pages/checkin/index',          // 称重 → 通用打卡页（暂无独立页面）
        'meal': '/pages/diet/index',              // 用餐 → 饮食记录页
      };

      const targetPage = typeToPageMap[reminder.type];
      if (!targetPage) {
        Taro.showToast({
          title: '暂无对应打卡页面',
          icon: 'none',
          duration: 2000
        });
        return;
      }

      // 检查目标页面是否在 tabBar 中
      const tabBarPages = [
        '/pages/index/index',
        '/pages/dashboard/index',
        '/pages/checkin/index',
        '/pages/settings/index'
      ];

      if (tabBarPages.includes(targetPage)) {
        // 使用 switchTab 跳转到 tabBar 页面
        await Taro.switchTab({ url: targetPage });
      } else {
        // 使用 navigateTo 跳转到普通页面
        await Taro.navigateTo({ url: targetPage });
      }
    } catch (error) {
      console.error('[提醒点击] 跳转失败:', error);
      Taro.showToast({
        title: '跳转失败，请重试',
        icon: 'none',
        duration: 2000
      });
    }
  };

  const loadHomeData = async () => {
    // 使用 ref 来防止重复加载
    if (homeData.loading) {
      console.log('[首页] 正在加载中，跳过重复请求');
      return;
    }
    
    // 性能监控：开始加载数据
    performanceMonitor.start('首页-总数据加载');
    setHomeData(prev => ({ ...prev, loading: true }));
    
    try {
      // ========== 第一批：关键数据（立即加载）==========
      // 用户最关心的核心健康数据
      performanceMonitor.start('首页-第一批加载');
      console.log('[首页] 🚀 第一批：加载关键数据（Garmin、提醒、运动）');
      
      const [
        garminData,
        remindersData,
        workoutsData
      ] = await Promise.allSettled([
        performanceMonitor.trackAPI('getTodayGarminData', () => getTodayGarminDataCached()),
        performanceMonitor.trackAPI('getCurrentReminders', () => getCurrentRemindersCached()),
        performanceMonitor.trackAPI('getTodayWorkouts', () => getTodayWorkoutsCached())
      ]);
      
      performanceMonitor.end('首页-第一批加载', {
        成功: [garminData, remindersData, workoutsData].filter(r => r.status === 'fulfilled').length,
        失败: [garminData, remindersData, workoutsData].filter(r => r.status === 'rejected').length
      });

      // 立即更新关键数据，让用户快速看到内容
      const workouts = workoutsData.status === 'fulfilled' ? workoutsData.value : [];
      setHomeData(prev => ({
        ...prev,
        garmin: garminData.status === 'fulfilled' ? garminData.value : null,
        reminders: remindersData.status === 'fulfilled' ? (remindersData.value?.reminders || []) : [],
        workouts,
        loading: false, // 关键数据加载完成，移除 loading 状态
      }));
      
      // 标记首屏数据加载完成
      pagePerformance.dataLoaded('首页');
      performanceMonitor.end('首页-总数据加载');
      
      // 如果今日没有运动记录，获取运动指导
      if (workouts.length === 0) {
        performanceMonitor.trackAPI('getPreWorkoutGuidance', () => getPreWorkoutGuidanceCached('running'))
          .then(workoutGuidance => {
            setHomeData(prev => ({ ...prev, workoutGuidance }));
          })
          .catch(e => console.error('获取运动指导失败:', e));
      }

      // ========== 第二批：重要数据（延迟 300ms）==========
      // 推荐和日程数据
      setTimeout(async () => {
        performanceMonitor.start('首页-第二批加载');
        console.log('[首页] 📊 第二批：加载重要数据（推荐、饮食、日程）');
        
        const [
          recommendationData,
          dietData,
          scheduleData
        ] = await Promise.allSettled([
          performanceMonitor.trackAPI('getDailyRecommendation', () => getDailyRecommendationCached()),
          performanceMonitor.trackAPI('getTodayDietSummary', () => getTodayDietSummaryCached()),
          performanceMonitor.trackAPI('getDailySchedule', () => getDailyScheduleCached())
        ]);
        
        performanceMonitor.end('首页-第二批加载', {
          成功: [recommendationData, dietData, scheduleData].filter(r => r.status === 'fulfilled').length,
          失败: [recommendationData, dietData, scheduleData].filter(r => r.status === 'rejected').length
        });

        setHomeData(prev => ({
          ...prev,
          recommendation: recommendationData.status === 'fulfilled' ? recommendationData.value : null,
          diet: dietData.status === 'fulfilled' ? dietData.value : null,
          schedule: scheduleData.status === 'fulfilled' ? (scheduleData.value?.schedule || []) : [],
        }));
      }, 300);

      // ========== 第三批：次要数据（延迟 800ms）==========
      // AI 分析和历史记录
      setTimeout(async () => {
        performanceMonitor.start('首页-第三批加载');
        console.log('[首页] 🤖 第三批：加载次要数据（简报、AI推荐、鼻炎）');
        
        const [
          briefingData,
          aiRecData,
          rhinitisData
        ] = await Promise.allSettled([
          performanceMonitor.trackAPI('getMorningBriefing', () => getMorningBriefingCached()),
          performanceMonitor.trackAPI('getAIRecommendation', () => getAIRecommendationCached()),
          performanceMonitor.trackAPI('getTodayRhinitis', () => getTodayRhinitisCached())
        ]);
        
        performanceMonitor.end('首页-第三批加载', {
          成功: [briefingData, aiRecData, rhinitisData].filter(r => r.status === 'fulfilled').length,
          失败: [briefingData, aiRecData, rhinitisData].filter(r => r.status === 'rejected').length
        });

        setHomeData(prev => ({
          ...prev,
          briefing: briefingData.status === 'fulfilled' ? briefingData.value : null,
          aiRecommendation: aiRecData.status === 'fulfilled' ? aiRecData.value : null,
          rhinitis: rhinitisData.status === 'fulfilled' ? rhinitisData.value : null,
        }));
        
        // 所有数据加载完成
        setTimeout(() => {
          pagePerformance.pageReady('首页');
          console.log('[首页] ✅ 所有数据加载完成');
        }, 100);
      }, 800);
      
    } catch (error) {
      console.error('[首页] 加载数据异常:', error);
      performanceMonitor.end('首页-总数据加载', { error: String(error) });
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
  const handleCheckinAction = async (checkinAction: string) => {
    if (!isLoggedIn) {
      Taro.showToast({ title: '请先登录', icon: 'none' });
      return;
    }

    try {
      // 喝水：直接调用 API 快速记录（与 Web 端保持一致）
      if (checkinAction === 'water') {
        Taro.showLoading({ title: '记录中...' });
        try {
          await quickAddWater(250);
          Taro.hideLoading();
          Taro.showToast({
            title: '已记录 250ml 💧',
            icon: 'success',
            duration: 2000
          });
          // 刷新提醒列表
          const newReminders = await getCurrentRemindersCached();
          setHomeData(prev => ({
            ...prev,
            reminders: newReminders?.reminders || []
          }));
        } catch (e) {
          Taro.hideLoading();
          console.error('[喝水打卡] 失败:', e);
          Taro.showToast({
            title: '记录失败，请重试',
            icon: 'none',
            duration: 2000
          });
        }
        return;
      }

      const actionMap: Record<string, string> = {
        'nasal_wash': '/pages/checkin/index',      // 洗鼻 → 通用打卡页
        'supplement': '/pages/supplements/index',  // 补剂 → 补剂记录页
        'exercise': '/pages/workout/index',        // 运动 → 运动记录页
        'weight': '/pages/checkin/index',          // 体重 → 通用打卡页（暂无独立页面）
        'diet': '/pages/diet/index',               // 饮食 → 饮食记录页
      };

      const targetPage = actionMap[checkinAction];
      if (!targetPage) {
        Taro.showToast({ title: '功能开发中', icon: 'none' });
        return;
      }

      // 检查目标页面是否在 tabBar 中
      const tabBarPages = [
        '/pages/index/index',
        '/pages/dashboard/index',
        '/pages/checkin/index',
        '/pages/settings/index'
      ];

      if (tabBarPages.includes(targetPage)) {
        await Taro.switchTab({ url: targetPage });
      } else {
        await Taro.navigateTo({ url: targetPage });
      }
    } catch (error) {
      console.error('[打卡跳转] 跳转失败:', error);
      Taro.showToast({
        title: '跳转失败，请重试',
        icon: 'none',
        duration: 2000
      });
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
            <Text className="feature-icon">⌚</Text>
            <Text className="feature-text">Garmin 数据同步</Text>
          </View>
          <View className="feature-item">
            <Text className="feature-icon">✨</Text>
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
          <View className="hero-glow-2"></View>
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
            <Text className="section-subtitle">点击立即打卡</Text>
          </View>
          <View 
            className="reminder-card clickable" 
            onClick={() => handleReminderClick(homeData.reminders[0])}
          >
            <Text className="reminder-emoji">{homeData.reminders[0].title.split(' ')[0] || '💊'}</Text>
            <View className="reminder-info">
              <Text className="reminder-title">{homeData.reminders[0].title.replace(/^[^\s]+\s/, '')}</Text>
              <Text className="reminder-desc">{homeData.reminders[0].message}</Text>
            </View>
            <View className="reminder-time-badge">
              <Text>{homeData.reminders[0].scheduled_time}</Text>
            </View>
            <View className="reminder-arrow">
              <Text>→</Text>
            </View>
          </View>
        </View>
      )}

      {/* 快捷功能 - 横向滚动卡片 */}
      <View className="section quick-section">
        <View className="section-header yellow">
          <Text className="section-icon">⚡</Text>
          <Text className="section-title">快捷功能</Text>
        </View>
        <ScrollView className="quick-scroll" scrollX enhanced showScrollbar={false}>
          <View className="quick-scroll-inner">
            <View className="quick-card" onClick={() => handleNavToPage('diet')}>
              <View className="quick-card-icon yellow">
                <Image className="quick-card-img" src={require('../../assets/icons/quick-diet.png')} />
              </View>
              <View className="quick-card-info">
                <Text className="quick-card-title">饮食记录</Text>
                <Text className="quick-card-desc">记录每餐摄入</Text>
              </View>
            </View>
            <View className="quick-card" onClick={() => Taro.navigateTo({ url: '/pages/workout-guidance/index' })}>
              <View className="quick-card-icon orange">
                <Image className="quick-card-img" src={require('../../assets/icons/quick-workout.png')} />
              </View>
              <View className="quick-card-info">
                <Text className="quick-card-title">运动指导</Text>
                <Text className="quick-card-desc">心率区间训练</Text>
              </View>
            </View>
            <View className="quick-card" onClick={() => Taro.navigateTo({ url: '/pages/chat/index' })}>
              <View className="quick-card-icon purple">
                <Text className="quick-card-emoji">💬</Text>
              </View>
              <View className="quick-card-info">
                <Text className="quick-card-title">健康问答</Text>
                <Text className="quick-card-desc">私人顾问</Text>
              </View>
            </View>
            <View className="quick-card" onClick={() => Taro.navigateTo({ url: '/pages/ai-insights/index' })}>
              <View className="quick-card-icon indigo">
                <Text className="quick-card-emoji">🧠</Text>
              </View>
              <View className="quick-card-info">
                <Text className="quick-card-title">AI洞察</Text>
                <Text className="quick-card-desc">智能复盘</Text>
              </View>
            </View>
            <View className="quick-card" onClick={() => Taro.navigateTo({ url: '/pages/diet-recommendation/index' })}>
              <View className="quick-card-icon purple">
                <Text className="quick-card-emoji">🍽️</Text>
              </View>
              <View className="quick-card-info">
                <Text className="quick-card-title">饮食推荐</Text>
                <Text className="quick-card-desc">智能配餐</Text>
              </View>
            </View>
            <View className="quick-card" onClick={() => handleQuickNav('dashboard')}>
              <View className="quick-card-icon blue">
                <Text className="quick-card-emoji">📊</Text>
              </View>
              <View className="quick-card-info">
                <Text className="quick-card-title">数据看板</Text>
                <Text className="quick-card-desc">健康趋势</Text>
              </View>
            </View>
            <View className="quick-card" onClick={() => handleNavToPage('supplements')}>
              <View className="quick-card-icon green">
                <Text className="quick-card-emoji">💊</Text>
              </View>
              <View className="quick-card-info">
                <Text className="quick-card-title">补剂记录</Text>
                <Text className="quick-card-desc">追踪补充</Text>
              </View>
            </View>
          </View>
        </ScrollView>
      </View>

      {/* 今日概览 - 紧凑深色玻璃风格 */}
      <View className="section">
        <View className="section-header yellow">
          <Text className="section-icon">✨</Text>
          <Text className="section-title">今日概览</Text>
        </View>
        <View className="overview-card" onClick={() => handleNavToPage('diet')}>
          {(() => {
            // 能量差计算
            const DEFAULT_BMR = 1600;
            const workoutCalories = homeData.workouts.reduce((sum, w) => sum + (w.calories || 0), 0);

            let totalOut: number;
            if (homeData?.garmin?.calories_total && homeData.garmin.calories_total > 0) {
              totalOut = homeData.garmin.calories_total;
            } else {
              totalOut = DEFAULT_BMR + workoutCalories;
            }

            const totalIn = homeData.diet?.total_calories || 0;
            const energyDiff = totalOut - totalIn;
            const maxVal = Math.max(totalOut, totalIn, 1);
            const isCreatingDeficit = energyDiff > 0;
            const deficitAmount = Math.abs(energyDiff);
            const KCAL_PER_GRAM_FAT = 7.7;
            const fatGrams = Math.round(deficitAmount / KCAL_PER_GRAM_FAT);

            return (
              <>
                {/* 顶部：脂肪数值 + 进度条 */}
                <View className="overview-top">
                  <View className="overview-fat">
                    <Text className={`fat-num ${isCreatingDeficit ? 'green' : 'red'}`}>
                      {isCreatingDeficit ? '-' : '+'}{fatGrams}
                    </Text>
                    <Text className="fat-unit">克脂肪</Text>
                    {isCreatingDeficit && <Text className="fat-check">✓</Text>}
                  </View>
                  <View className="overview-bars">
                    <View className="bar-row">
                      <Text className="bar-label">消耗</Text>
                      <View className="bar-track">
                        <View className="bar-fill red" style={{ width: `${Math.min((totalOut / maxVal) * 100, 100)}%` }} />
                      </View>
                      <Text className="bar-val red">{totalOut}</Text>
                    </View>
                    <View className="bar-row">
                      <Text className="bar-label">摄入</Text>
                      <View className="bar-track">
                        <View className="bar-fill green" style={{ width: `${Math.min((totalIn / maxVal) * 100, 100)}%` }} />
                      </View>
                      <Text className="bar-val green">{totalIn}</Text>
                    </View>
                  </View>
                </View>

                {/* 底部：营养素 + 餐食 */}
                <View className="overview-bottom">
                  <View className="nutrient-tag">
                    <Text className="tag-icon">🥩</Text>
                    <Text className="tag-val">{homeData.diet?.total_protein?.toFixed(0) || 0}g</Text>
                  </View>
                  <View className="nutrient-tag">
                    <Text className="tag-icon">🍚</Text>
                    <Text className="tag-val">{homeData.diet?.total_carbs?.toFixed(0) || 0}g</Text>
                  </View>
                  <View className="nutrient-tag">
                    <Text className="tag-icon">🧈</Text>
                    <Text className="tag-val">{homeData.diet?.total_fat?.toFixed(0) || 0}g</Text>
                  </View>
                  {homeData.diet && homeData.diet.meals_count > 0 ? (
                    homeData.diet.meals.slice(0, 2).map((m, idx) => (
                      <View key={idx} className="meal-tag">
                        <Text className="meal-name">{
                          m.meal_type === 'breakfast' ? '早' :
                          m.meal_type === 'lunch' ? '午' :
                          m.meal_type === 'dinner' ? '晚' : '加'
                        }</Text>
                        <Text className="meal-cal">{m.calories || 0}</Text>
                      </View>
                    ))
                  ) : null}
                  <View className="add-meal-btn" onClick={(e) => { e.stopPropagation(); handleNavToPage('diet'); }}>
                    <Text>+ 记录</Text>
                  </View>
                </View>
              </>
            );
          })()}
        </View>
      </View>

      {/* 今日运动 - 独立卡片 */}
      <View className="section">
        <View className="section-header yellow">
          <Text className="section-icon">🏃</Text>
          <Text className="section-title">今日运动</Text>
          <Text className="section-subtitle" onClick={() => handleNavToPage('workout')}>查看全部 →</Text>
        </View>
        <View className="workout-card">
          {homeData.workouts && homeData.workouts.length > 0 ? (
            <View className="workout-content" onClick={() => handleNavToPage('workout')}>
              <View className="workout-summary">
                <Text className="workout-total-cal">{homeData.workouts.reduce((sum, w) => sum + (w.calories || 0), 0)}</Text>
                <Text className="workout-total-unit">卡消耗</Text>
              </View>
              <View className="workout-items">
                {homeData.workouts.slice(0, 3).map((w, idx) => (
                  <View key={idx} className="workout-tag">
                    <Text className="tag-name">{w.workout_name || w.workout_type}</Text>
                    <Text className="tag-cal">{w.calories || 0}卡</Text>
                  </View>
                ))}
              </View>
            </View>
          ) : homeData.workoutGuidance ? (
            <View className="workout-guidance-mini">
              <View className="guidance-left">
                <Text className="guidance-label">今日建议</Text>
                <Text className="guidance-obj">{homeData.workoutGuidance.training_objective}</Text>
              </View>
              <View
                className="guidance-action"
                onClick={() => Taro.navigateTo({ url: '/pages/workout-guidance/index' })}
              >
                <Text>查看指导</Text>
              </View>
            </View>
          ) : (
            <View className="workout-empty-mini" onClick={() => handleNavToPage('workout')}>
              <Text className="empty-icon-mini">🏃‍♂️</Text>
              <Text className="empty-hint-mini">今日暂无运动记录</Text>
              <View className="empty-action">
                <Text>+ 记录运动</Text>
              </View>
            </View>
          )}
        </View>
      </View>

      {/* 健康简报 */}
      <View className="section">
        <View className="section-header gray">
          <Text className="section-icon">📋</Text>
          <Text className="section-title">健康简报</Text>
        </View>

        {/* 简报网格 - 移除问候语，直接显示指标卡片 */}
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
            <Text className="section-count">{homeData.schedule.length}项</Text>
          </View>
          <View className="timeline">
            <View className="timeline-line"></View>
            {(scheduleExpanded ? homeData.schedule : homeData.schedule.slice(0, SCHEDULE_DEFAULT_COUNT)).map((item, idx) => {
              const color = getCategoryColor(item.category);
              // 判断是否已过时间
              const now = new Date();
              const [hours, minutes] = item.time.split(':').map(Number);
              const itemTime = new Date();
              itemTime.setHours(hours, minutes, 0, 0);
              const isPast = itemTime < now;

              return (
                <View key={idx} className={`timeline-item color-${color} ${isPast ? 'past' : ''}`}>
                  <View className={`timeline-dot border-${color} ${isPast ? 'past' : ''}`}></View>
                  <View className={`timeline-card border-left-${color} ${isPast ? 'past' : ''}`}>
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
          {/* 展开/收起按钮 */}
          {homeData.schedule.length > SCHEDULE_DEFAULT_COUNT && (
            <View className="schedule-toggle" onClick={() => setScheduleExpanded(!scheduleExpanded)}>
              <Text className="toggle-text">
                {scheduleExpanded ? '收起' : `展开更多 (${homeData.schedule.length - SCHEDULE_DEFAULT_COUNT}项)`}
              </Text>
              <Text className={`toggle-icon ${scheduleExpanded ? 'expanded' : ''}`}>▼</Text>
            </View>
          )}
        </View>
      )}

      {/* 刷新按钮 */}
      <View className="refresh-area">
        <View 
          className="refresh-btn" 
          onClick={async () => {
            Taro.showLoading({ title: '同步中...' });
            try {
              // 同步 Garmin 数据
              await syncMyGarminData(1).catch(() => {});
              await new Promise(resolve => setTimeout(resolve, 500));
              
              // 清除所有首页缓存，确保获取最新数据
              console.log('[刷新] 清除缓存，重新加载数据');
              clearHomePageCache();
              
              // 重新加载数据
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
