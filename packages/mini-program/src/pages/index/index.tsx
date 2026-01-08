/**
 * 首页 - 登录/欢迎页
 */
import { useState, useEffect } from 'react';
import { View, Text, Button, Image } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { wechatLogin } from '../../services/api';
import { getToken } from '../../services/request';
import './index.scss';

export default function Index() {
  const [loading, setLoading] = useState(false);
  const [isLoggedIn, setIsLoggedIn] = useState(false);

  useEffect(() => {
    // 检查是否已登录
    const token = getToken();
    if (token) {
      setIsLoggedIn(true);
      // 已登录，跳转到数据页
      Taro.switchTab({ url: '/pages/dashboard/index' });
    }
  }, []);

  const handleLogin = async () => {
    setLoading(true);
    try {
      const result = await wechatLogin();
      
      Taro.showToast({
        title: result.is_new_user ? '欢迎新用户！' : '登录成功',
        icon: 'success',
      });

      // 跳转到数据页
      setTimeout(() => {
        Taro.switchTab({ url: '/pages/dashboard/index' });
      }, 1500);
    } catch (error: any) {
      Taro.showToast({
        title: error.message || '登录失败',
        icon: 'none',
      });
    } finally {
      setLoading(false);
    }
  };

  if (isLoggedIn) {
    return (
      <View className="index-page loading">
        <Text>加载中...</Text>
      </View>
    );
  }

  return (
    <View className="index-page">
      {/* Logo 区域 */}
      <View className="logo-section">
        <Image 
          className="logo-image" 
          src={require('../../assets/logo.png')} 
          mode="aspectFit"
        />
        <Text className="app-title">自律靠AI</Text>
        <Text className="app-subtitle">AI 驱动的个人健康管理助手</Text>
      </View>

      {/* 功能介绍 */}
      <View className="features-section">
        <View className="feature-item">
          <Text className="feature-icon">💡</Text>
          <Text className="feature-text">AI 健康建议</Text>
        </View>
        <View className="feature-item">
          <Text className="feature-icon">❤️</Text>
          <Text className="feature-text">心率监测分析</Text>
        </View>
        <View className="feature-item">
          <Text className="feature-icon">🤧</Text>
          <Text className="feature-text">鼻炎症状追踪</Text>
        </View>
        <View className="feature-item">
          <Text className="feature-icon">📊</Text>
          <Text className="feature-text">Garmin 数据同步</Text>
        </View>
      </View>

      {/* 登录按钮 */}
      <View className="login-section">
        <Button
          className="login-btn"
          onClick={handleLogin}
          loading={loading}
          disabled={loading}
        >
          {loading ? '登录中...' : '微信一键登录'}
        </Button>
        <Text className="login-tip">
          登录即表示同意《用户协议》和《隐私政策》
        </Text>
      </View>
    </View>
  );
}

