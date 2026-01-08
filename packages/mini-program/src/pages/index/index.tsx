/**
 * 首页 - 登录/欢迎页
 */
import { useState, useEffect } from 'react';
import { View, Text, Button, Image } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { wechatLogin } from '../../services/api';
import { getToken } from '../../services/request';
import logoImage from '../../assets/logo.png';
import './index.scss';

export default function Index() {
  const [loading, setLoading] = useState(false);
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [userName, setUserName] = useState('');

  useEffect(() => {
    checkLoginStatus();
  }, []);

  // 页面显示时重新检查登录状态
  Taro.useDidShow(() => {
    checkLoginStatus();
  });

  const checkLoginStatus = () => {
    const token = getToken();
    setIsLoggedIn(!!token);
    if (token) {
      const storedName = Taro.getStorageSync('user_name');
      setUserName(storedName || '自律靠AI用户');
    }
  };

  const handleLogin = async () => {
    setLoading(true);
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

  const handleQuickNav = (page: string) => {
    Taro.switchTab({ url: `/pages/${page}/index` });
  };

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

      {/* 功能介绍/快捷入口 */}
      <View className="features-section">
        <View className="feature-item" onClick={() => isLoggedIn && handleQuickNav('dashboard')}>
          <Text className="feature-icon">💡</Text>
          <Text className="feature-text">AI 健康建议</Text>
        </View>
        <View className="feature-item" onClick={() => isLoggedIn && handleQuickNav('dashboard')}>
          <Text className="feature-icon">❤️</Text>
          <Text className="feature-text">心率监测分析</Text>
        </View>
        <View className="feature-item" onClick={() => isLoggedIn && handleQuickNav('rhinitis')}>
          <Text className="feature-icon">🤧</Text>
          <Text className="feature-text">鼻炎症状追踪</Text>
        </View>
        <View className="feature-item" onClick={() => isLoggedIn && handleQuickNav('dashboard')}>
          <Text className="feature-icon">📊</Text>
          <Text className="feature-text">Garmin 数据同步</Text>
        </View>
      </View>

      {/* 登录按钮 - 仅未登录时显示 */}
      {!isLoggedIn && (
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
      )}

      {/* 已登录时显示快捷操作 */}
      {isLoggedIn && (
        <View className="logged-in-section">
          <Button
            className="action-btn"
            onClick={() => handleQuickNav('dashboard')}
          >
            查看今日数据
          </Button>
        </View>
      )}
    </View>
  );
}
