/**
 * 首页 - 登录/欢迎页
 */
import { useState, useEffect } from 'react';
import { View, Text, Button, Image } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { wechatLogin, getTodayGarminData, getDailyRecommendation, getTodayRhinitis } from '../../services/api';
import { getToken } from '../../services/request';
import { GarminData, DailyRecommendation, RhinitisRecord } from '../../types';
import logoImage from '../../assets/logo.png';
import './index.scss';

interface HomeData {
  garmin: GarminData | null;
  recommendation: DailyRecommendation | null;
  rhinitis: RhinitisRecord | null;
  loading: boolean;
}

export default function Index() {
  const [loginLoading, setLoginLoading] = useState(false);
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [userName, setUserName] = useState('');
  const [homeData, setHomeData] = useState<HomeData>({
    garmin: null,
    recommendation: null,
    rhinitis: null,
    loading: false,
  });

  useEffect(() => {
    checkLoginStatus();
  }, []);

  // 页面显示时重新检查登录状态和刷新数据
  Taro.useDidShow(() => {
    checkLoginStatus();
  });

  const checkLoginStatus = async () => {
    const token = getToken();
    setIsLoggedIn(!!token);
    if (token) {
      const storedName = Taro.getStorageSync('user_name');
      setUserName(storedName || '自律靠AI用户');
      // 加载首页数据
      loadHomeData();
    }
  };

  const loadHomeData = async () => {
    setHomeData(prev => ({ ...prev, loading: true }));
    
    try {
      // 并行获取数据
      const [garminData, recommendationData, rhinitisData] = await Promise.allSettled([
        getTodayGarminData(),
        getDailyRecommendation(),
        getTodayRhinitis(),
      ]);

      setHomeData({
        garmin: garminData.status === 'fulfilled' ? garminData.value : null,
        recommendation: recommendationData.status === 'fulfilled' ? recommendationData.value : null,
        rhinitis: rhinitisData.status === 'fulfilled' ? rhinitisData.value : null,
        loading: false,
      });
    } catch (error) {
      console.error('加载首页数据失败:', error);
      setHomeData(prev => ({ ...prev, loading: false }));
    }
  };

  const handleLogin = async () => {
    setLoginLoading(true);
    try {
      const result = await wechatLogin();
      
      Taro.showToast({
        title: result.is_new_user ? '欢迎新用户！' : '登录成功',
        icon: 'success',
      });

      setIsLoggedIn(true);
      if (result.nickname) {
        setUserName(result.nickname);
      }

      // 加载首页数据
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

  const handleQuickNav = (page: string) => {
    if (!isLoggedIn) {
      Taro.showToast({
        title: '请先登录',
        icon: 'none',
      });
      return;
    }
    Taro.switchTab({ url: `/pages/${page}/index` });
  };

  // 获取心率状态
  const getHeartRateStatus = () => {
    const hr = homeData.garmin?.resting_heart_rate;
    if (!hr) return { text: '暂无数据', color: '#9CA3AF' };
    if (hr < 60) return { text: '偏低', color: '#3B82F6' };
    if (hr <= 80) return { text: '正常', color: '#10B981' };
    return { text: '偏高', color: '#F59E0B' };
  };

  // 获取建议摘要
  const getRecommendationSummary = () => {
    const rec = homeData.recommendation;
    if (!rec || rec.status !== 'success') {
      return '点击查看今日健康建议';
    }
    
    // 从 one_day 中获取优先建议
    const oneDay = rec.one_day;
    if (oneDay?.priority_recommendations && oneDay.priority_recommendations.length > 0) {
      const firstRec = oneDay.priority_recommendations[0];
      return firstRec.length > 18 ? firstRec.substring(0, 18) + '...' : firstRec;
    }
    
    // 如果有整体状态，显示整体状态
    if (oneDay?.overall_status) {
      const statusMap: Record<string, string> = {
        'excellent': '状态极佳 ✨',
        'good': '状态良好 👍',
        'fair': '状态一般',
        'poor': '需要关注 ⚠️',
      };
      return statusMap[oneDay.overall_status] || '点击查看详情';
    }
    
    return '点击查看今日健康建议';
  };

  // 获取鼻炎打卡状态
  const getRhinitisStatus = () => {
    const record = homeData.rhinitis;
    if (!record) return { done: false, text: '今日未打卡' };
    
    const hasSneeze = record.sneeze_count !== null && record.sneeze_count > 0;
    const hasWash = record.nasal_wash_done;
    
    if (hasSneeze || hasWash) {
      return { 
        done: true, 
        text: `喷嚏${record.sneeze_count || 0}次${hasWash ? '・已洗鼻' : ''}`
      };
    }
    return { done: true, text: '今日已打卡' };
  };

  // 获取Garmin同步状态
  const getGarminStatus = () => {
    const data = homeData.garmin;
    if (!data) return { synced: false, text: '暂无数据' };
    return { 
      synced: true, 
      text: `步数 ${data.steps?.toLocaleString() || 0}`
    };
  };

  const hrStatus = getHeartRateStatus();
  const rhinitisStatus = getRhinitisStatus();
  const garminStatus = getGarminStatus();

  return (
    <View className="index-page">
      {/* Logo 区域 */}
      <View className="logo-section">
        <Image 
          className="logo-image" 
          src={logoImage} 
          mode="aspectFit"
        />
        <Text className="app-title">自律靠AI</Text>
        <Text className="app-subtitle">
          {isLoggedIn ? `欢迎回来，${userName}` : 'AI 驱动的个人健康管理助手'}
        </Text>
      </View>

      {/* 功能卡片区域 */}
      <View className="features-section">
        {/* AI 健康建议 */}
        <View 
          className={`feature-card ${isLoggedIn ? 'active' : ''}`} 
          onClick={() => handleQuickNav('dashboard')}
        >
          <View className="card-header">
            <Text className="card-icon">💡</Text>
            <Text className="card-title">AI 健康建议</Text>
          </View>
          <View className="card-content">
            {isLoggedIn ? (
              homeData.loading ? (
                <Text className="card-value loading">加载中...</Text>
              ) : (
                <Text className="card-desc">{getRecommendationSummary()}</Text>
              )
            ) : (
              <Text className="card-desc">登录后查看</Text>
            )}
          </View>
        </View>

        {/* 心率监测 */}
        <View 
          className={`feature-card ${isLoggedIn ? 'active' : ''}`}
          onClick={() => handleQuickNav('dashboard')}
        >
          <View className="card-header">
            <Text className="card-icon">❤️</Text>
            <Text className="card-title">心率监测</Text>
          </View>
          <View className="card-content">
            {isLoggedIn ? (
              homeData.loading ? (
                <Text className="card-value loading">加载中...</Text>
              ) : homeData.garmin?.resting_heart_rate ? (
                <>
                  <Text className="card-value">{homeData.garmin.resting_heart_rate}</Text>
                  <Text className="card-unit">bpm</Text>
                  <Text className="card-status" style={{ color: hrStatus.color }}>{hrStatus.text}</Text>
                </>
              ) : (
                <Text className="card-desc">暂无心率数据</Text>
              )
            ) : (
              <Text className="card-desc">登录后查看</Text>
            )}
          </View>
        </View>

        {/* 鼻炎追踪 */}
        <View 
          className={`feature-card ${isLoggedIn ? 'active' : ''}`}
          onClick={() => handleQuickNav('rhinitis')}
        >
          <View className="card-header">
            <Text className="card-icon">🤧</Text>
            <Text className="card-title">鼻炎追踪</Text>
          </View>
          <View className="card-content">
            {isLoggedIn ? (
              homeData.loading ? (
                <Text className="card-value loading">加载中...</Text>
              ) : (
                <>
                  <View className={`status-badge ${rhinitisStatus.done ? 'done' : 'pending'}`}>
                    <Text>{rhinitisStatus.done ? '✓' : '○'}</Text>
                  </View>
                  <Text className="card-desc">{rhinitisStatus.text}</Text>
                </>
              )
            ) : (
              <Text className="card-desc">登录后查看</Text>
            )}
          </View>
        </View>

        {/* Garmin 数据 */}
        <View 
          className={`feature-card ${isLoggedIn ? 'active' : ''}`}
          onClick={() => handleQuickNav('dashboard')}
        >
          <View className="card-header">
            <Text className="card-icon">📊</Text>
            <Text className="card-title">Garmin 数据</Text>
          </View>
          <View className="card-content">
            {isLoggedIn ? (
              homeData.loading ? (
                <Text className="card-value loading">加载中...</Text>
              ) : garminStatus.synced ? (
                <>
                  <View className="status-badge done">
                    <Text>✓</Text>
                  </View>
                  <Text className="card-desc">{garminStatus.text}</Text>
                </>
              ) : (
                <Text className="card-desc">去设置同步</Text>
              )
            ) : (
              <Text className="card-desc">登录后查看</Text>
            )}
          </View>
        </View>
      </View>

      {/* 登录按钮 - 仅未登录时显示 */}
      {!isLoggedIn && (
        <View className="login-section">
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
      )}

      {/* 已登录时显示快速刷新 */}
      {isLoggedIn && (
        <View className="logged-in-section">
          <Button
            className="action-btn"
            onClick={() => handleQuickNav('dashboard')}
          >
            查看今日数据
          </Button>
          <Text 
            className="refresh-link" 
            onClick={() => loadHomeData()}
          >
            🔄 刷新数据
          </Text>
        </View>
      )}
    </View>
  );
}
