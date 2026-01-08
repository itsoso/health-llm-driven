/**
 * 设置/我的页面
 */
import { useState, useEffect } from 'react';
import { View, Text, Button } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { clearToken, getToken } from '../../services/request';
import './index.scss';

export default function Settings() {
  const [isLoggedIn, setIsLoggedIn] = useState(false);

  useEffect(() => {
    const token = getToken();
    setIsLoggedIn(!!token);
  }, []);

  const handleLogout = () => {
    Taro.showModal({
      title: '提示',
      content: '确定要退出登录吗？',
      success: (res) => {
        if (res.confirm) {
          clearToken();
          Taro.redirectTo({ url: '/pages/index/index' });
        }
      },
    });
  };

  const handleBindGarmin = () => {
    Taro.showModal({
      title: '绑定 Garmin',
      content: '请在 PC 端网页版中绑定您的 Garmin 账号，绑定后数据将自动同步到小程序。',
      showCancel: false,
    });
  };

  return (
    <View className="settings-page">
      {/* 用户信息 */}
      <View className="user-card">
        <View className="avatar">
          <Text className="avatar-text">🧬</Text>
        </View>
        <View className="user-info">
          <Text className="user-name">健康管理用户</Text>
          <Text className="user-status">已登录</Text>
        </View>
      </View>

      {/* 功能列表 */}
      <View className="menu-section">
        <View className="menu-item" onClick={handleBindGarmin}>
          <Text className="menu-icon">⌚</Text>
          <Text className="menu-text">绑定 Garmin</Text>
          <Text className="menu-arrow">›</Text>
        </View>
        
        <View className="menu-item">
          <Text className="menu-icon">📊</Text>
          <Text className="menu-text">数据同步</Text>
          <Text className="menu-desc">在 PC 端操作</Text>
        </View>

        <View className="menu-item">
          <Text className="menu-icon">🔔</Text>
          <Text className="menu-text">提醒设置</Text>
          <Text className="menu-arrow">›</Text>
        </View>
      </View>

      <View className="menu-section">
        <View className="menu-item">
          <Text className="menu-icon">📖</Text>
          <Text className="menu-text">使用帮助</Text>
          <Text className="menu-arrow">›</Text>
        </View>

        <View className="menu-item">
          <Text className="menu-icon">💬</Text>
          <Text className="menu-text">意见反馈</Text>
          <Text className="menu-arrow">›</Text>
        </View>

        <View className="menu-item">
          <Text className="menu-icon">ℹ️</Text>
          <Text className="menu-text">关于我们</Text>
          <Text className="menu-arrow">›</Text>
        </View>
      </View>

      {/* 退出登录 */}
      {isLoggedIn && (
        <View className="logout-section">
          <Button className="logout-btn" onClick={handleLogout}>
            退出登录
          </Button>
        </View>
      )}

      {/* 版本信息 */}
      <View className="version-info">
        <Text>健康管理 v1.0.0</Text>
      </View>
    </View>
  );
}

