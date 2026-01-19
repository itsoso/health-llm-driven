/**
 * 设置/我的页面
 */
import { useState, useEffect } from 'react';
import { View, Text, Button, Image, Switch } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { clearToken, getToken, get, put } from '../../services/request';
import { 
  requestAllSubscriptions, 
  getSubscribeSettings, 
  isSubscribeAvailable,
  TEMPLATE_NAMES 
} from '../../services/subscribe';
import logoImage from '../../assets/logo.png';
import './index.scss';

interface UserInfo {
  id: number;
  name: string;
  username: string;
  email: string;
  is_admin: boolean;
}

interface GarminCredential {
  id: number;
  is_cn: boolean;
  last_sync_at: string | null;
  sync_enabled: boolean;
  credentials_valid: boolean;
}

interface DeviceCredential {
  id: number;
  device_type: string;
  is_valid: boolean;
  sync_enabled: boolean;
  last_sync_at: string | null;
}

interface NotificationSettings {
  enabled: boolean;
  wechat_enabled: boolean;
  template_ids: Record<string, string> | null;
  morning_briefing_enabled: boolean;
  reminder_enabled: boolean;
  health_alert_enabled: boolean;
}

export default function Settings() {
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [userName, setUserName] = useState('自由是自律的泡沫用户');
  const [isAdmin, setIsAdmin] = useState(false);
  const [hasGarmin, setHasGarmin] = useState(false);
  const [garminStatus, setGarminStatus] = useState<'none' | 'valid' | 'invalid'>('none');
  const [huaweiStatus, setHuaweiStatus] = useState<'none' | 'valid' | 'invalid'>('none');
  
  // 消息提醒设置
  const [notificationSettings, setNotificationSettings] = useState<NotificationSettings | null>(null);
  const [subscribeAvailable] = useState(isSubscribeAvailable());

  useEffect(() => {
    const token = getToken();
    setIsLoggedIn(!!token);
    
    if (token) {
      loadUserInfo();
      loadGarminStatus();
      loadHuaweiStatus();
      loadNotificationSettings();
    }
    
    // 从本地存储获取用户名（备用）
    const storedName = Taro.getStorageSync('user_name');
    if (storedName) {
      setUserName(storedName);
    }
  }, []);

  const loadNotificationSettings = async () => {
    try {
      const settings = await getSubscribeSettings();
      if (settings) {
        setNotificationSettings(settings as NotificationSettings);
      }
    } catch (error) {
      console.error('获取通知设置失败:', error);
    }
  };

  // 开启消息提醒
  const handleEnableNotifications = async () => {
    Taro.showLoading({ title: '请求授权中...' });
    
    try {
      const result = await requestAllSubscriptions();
      Taro.hideLoading();
      
      if (result.success) {
        Taro.showToast({
          title: `已开启${result.acceptedTemplates.length}项提醒`,
          icon: 'success',
        });
        // 重新加载设置
        loadNotificationSettings();
      } else if (result.error) {
        Taro.showToast({
          title: result.error,
          icon: 'none',
        });
      }
    } catch (error) {
      Taro.hideLoading();
      Taro.showToast({
        title: '授权失败，请重试',
        icon: 'none',
      });
    }
  };

  // 切换通知总开关
  const handleToggleNotification = async (enabled: boolean) => {
    try {
      await put('/wechat/subscribe/settings', { enabled });
      setNotificationSettings(prev => prev ? { ...prev, enabled } : null);
      Taro.showToast({
        title: enabled ? '已开启通知' : '已关闭通知',
        icon: 'success',
      });
    } catch (error) {
      Taro.showToast({
        title: '设置失败',
        icon: 'none',
      });
    }
  };

  const loadUserInfo = async () => {
    try {
      const userInfo = await get<UserInfo>('/auth/me');
      setUserName(userInfo.name || userInfo.username || '自由是自律的泡沫用户');
      setIsAdmin(userInfo.is_admin);
      Taro.setStorageSync('user_name', userInfo.name || userInfo.username);
    } catch (error) {
      console.error('获取用户信息失败:', error);
    }
  };

  const loadGarminStatus = async () => {
    try {
      const credential = await get<GarminCredential>('/auth/garmin/credentials');
      setHasGarmin(true);
      setGarminStatus(credential.credentials_valid ? 'valid' : 'invalid');
    } catch (error) {
      setHasGarmin(false);
      setGarminStatus('none');
    }
  };

  const loadHuaweiStatus = async () => {
    try {
      const credential = await get<DeviceCredential>('/devices/me/huawei');
      setHuaweiStatus(credential.is_valid ? 'valid' : 'invalid');
    } catch (error) {
      setHuaweiStatus('none');
    }
  };

  const handleGoToHuawei = () => {
    Taro.navigateTo({ url: '/pages/huawei/index' });
  };

  const getHuaweiStatusText = () => {
    switch (huaweiStatus) {
      case 'valid': return '已绑定 ✓';
      case 'invalid': return '授权失效';
      case 'none': return '未绑定';
    }
  };

  const getHuaweiStatusClass = () => {
    switch (huaweiStatus) {
      case 'valid': return 'status-success';
      case 'invalid': return 'status-warning';
      case 'none': return 'status-none';
    }
  };

  const handleLogout = () => {
    Taro.showModal({
      title: '提示',
      content: '确定要退出登录吗？',
      success: (res) => {
        if (res.confirm) {
          clearToken();
          Taro.removeStorageSync('user_name');
          Taro.switchTab({ url: '/pages/index/index' });
        }
      },
    });
  };

  const handleGoToGarmin = () => {
    Taro.navigateTo({ url: '/pages/garmin/index' });
  };

  const handleGoToAdmin = () => {
    Taro.navigateTo({ url: '/pages/admin/index' });
  };

  const handleAbout = () => {
    Taro.showModal({
      title: '关于自由是自律的泡沫',
      content: 'AI驱动的个人健康管理助手\n\n功能特点：\n• Garmin 数据同步\n• AI 健康建议\n• 心率监测分析\n• 运动打卡追踪\n\n版本：v1.0.0',
      showCancel: false,
    });
  };

  const getGarminStatusText = () => {
    switch (garminStatus) {
      case 'valid': return '已绑定 ✓';
      case 'invalid': return '凭证失效';
      case 'none': return '未绑定';
    }
  };

  const getGarminStatusClass = () => {
    switch (garminStatus) {
      case 'valid': return 'status-success';
      case 'invalid': return 'status-warning';
      case 'none': return 'status-none';
    }
  };

  return (
    <View className="settings-page">
      {/* 用户信息 */}
      <View className="user-card">
        <Image 
          className="avatar-image" 
          src={logoImage} 
          mode="aspectFit"
        />
        <View className="user-info">
          <View className="user-name-row">
            <Text className="user-name">{userName}</Text>
            {isAdmin && <Text className="admin-badge">管理员</Text>}
          </View>
          <Text className="user-status">{isLoggedIn ? '已登录' : '未登录'}</Text>
        </View>
      </View>

      {/* 个人资料 - 重要入口放在最前面 */}
      <View className="menu-section profile-section">
        <View className="menu-item highlight" onClick={() => Taro.navigateTo({ url: '/pages/profile/index' })}>
          <Text className="menu-icon">👤</Text>
          <Text className="menu-text">个人资料</Text>
          <Text className="menu-desc">完善资料，获得更精准的AI建议</Text>
          <Text className="menu-arrow">›</Text>
        </View>
      </View>

      {/* 消息提醒设置 */}
      <View className="menu-section">
        <Text className="section-label">消息提醒</Text>
        
        {/* 未开启订阅时显示开启按钮 */}
        {(!notificationSettings?.wechat_enabled || !notificationSettings?.template_ids) ? (
          <View className="menu-item highlight" onClick={handleEnableNotifications}>
            <Text className="menu-icon">🔔</Text>
            <Text className="menu-text">开启消息提醒</Text>
            <Text className="menu-desc">接收健康提醒、早间简报等通知</Text>
            <Text className="menu-arrow">›</Text>
          </View>
        ) : (
          <>
            {/* 已开启订阅时显示开关 */}
            <View className="menu-item">
              <Text className="menu-icon">🔔</Text>
              <Text className="menu-text">消息通知</Text>
              <Switch 
                checked={notificationSettings?.enabled ?? false}
                onChange={(e) => handleToggleNotification(e.detail.value)}
                color="#7C3AED"
              />
            </View>
            
            {/* 显示已订阅的模板 */}
            {notificationSettings?.template_ids && Object.keys(notificationSettings.template_ids).length > 0 && (
              <View className="menu-item sub-item">
                <Text className="menu-icon">📋</Text>
                <Text className="menu-text">已订阅</Text>
                <Text className="menu-status status-success">
                  {Object.keys(notificationSettings.template_ids).length}项
                </Text>
              </View>
            )}
            
            {/* 重新授权按钮 */}
            <View className="menu-item" onClick={handleEnableNotifications}>
              <Text className="menu-icon">➕</Text>
              <Text className="menu-text">添加更多订阅</Text>
              <Text className="menu-arrow">›</Text>
            </View>
          </>
        )}
      </View>

      {/* 设备绑定 */}
      <View className="menu-section">
        <Text className="section-label">设备绑定</Text>
        <View className="menu-item" onClick={handleGoToGarmin}>
          <Text className="menu-icon">⌚</Text>
          <Text className="menu-text">Garmin 绑定</Text>
          <Text className={`menu-status ${getGarminStatusClass()}`}>
            {getGarminStatusText()}
          </Text>
          <Text className="menu-arrow">›</Text>
        </View>

        <View className="menu-item" onClick={handleGoToHuawei}>
          <Text className="menu-icon">📱</Text>
          <Text className="menu-text">华为手表</Text>
          <Text className={`menu-status ${getHuaweiStatusClass()}`}>
            {getHuaweiStatusText()}
          </Text>
          <Text className="menu-arrow">›</Text>
        </View>
      </View>

      {/* AI 功能 */}
      <View className="menu-section">
        <Text className="section-label">AI 功能</Text>
        <View className="menu-item" onClick={() => Taro.switchTab({ url: '/pages/index/index' })}>
          <Text className="menu-icon">🤖</Text>
          <Text className="menu-text">AI 健康助手</Text>
          <Text className="menu-desc">智能日程 · 实时建议</Text>
          <Text className="menu-arrow">›</Text>
        </View>

        <View className="menu-item" onClick={() => Taro.switchTab({ url: '/pages/dashboard/index' })}>
          <Text className="menu-icon">💡</Text>
          <Text className="menu-text">AI 健康建议</Text>
          <Text className="menu-arrow">›</Text>
        </View>
      </View>

      {/* 功能列表 */}
      <View className="menu-section">
        <Text className="section-label">健康功能</Text>
        <View className="menu-item" onClick={() => Taro.navigateTo({ url: '/pages/heart-rate/index' })}>
          <Text className="menu-icon">❤️</Text>
          <Text className="menu-text">心率追踪</Text>
          <Text className="menu-arrow">›</Text>
        </View>

        <View className="menu-item" onClick={() => Taro.navigateTo({ url: '/pages/workout/index' })}>
          <Text className="menu-icon">🏃</Text>
          <Text className="menu-text">运动记录</Text>
          <Text className="menu-arrow">›</Text>
        </View>

        <View className="menu-item" onClick={() => Taro.navigateTo({ url: '/pages/diet/index' })}>
          <Text className="menu-icon">🍽️</Text>
          <Text className="menu-text">饮食记录</Text>
          <Text className="menu-arrow">›</Text>
        </View>

        <View className="menu-item" onClick={() => Taro.navigateTo({ url: '/pages/environment/index' })}>
          <Text className="menu-icon">🌤️</Text>
          <Text className="menu-text">环境健康</Text>
          <Text className="menu-arrow">›</Text>
        </View>

        <View className="menu-item" onClick={() => Taro.navigateTo({ url: '/pages/garmin-data/index' })}>
          <Text className="menu-icon">📊</Text>
          <Text className="menu-text">历史数据</Text>
          <Text className="menu-arrow">›</Text>
        </View>
      </View>

      {/* 管理员功能 */}
      {isAdmin && (
        <View className="menu-section admin-section">
          <Text className="section-label">管理员功能</Text>
          <View className="menu-item" onClick={handleGoToAdmin}>
            <Text className="menu-icon">👑</Text>
            <Text className="menu-text">管理后台</Text>
            <Text className="menu-arrow">›</Text>
          </View>
        </View>
      )}

      <View className="menu-section">
        <View className="menu-item" onClick={handleAbout}>
          <Text className="menu-icon">ℹ️</Text>
          <Text className="menu-text">关于我们</Text>
          <Text className="menu-arrow">›</Text>
        </View>

        <View className="menu-item">
          <Text className="menu-icon">💬</Text>
          <Text className="menu-text">意见反馈</Text>
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
        <Text>自由是自律的泡沫 v1.0.0 (正式版)</Text>
      </View>
    </View>
  );
}
