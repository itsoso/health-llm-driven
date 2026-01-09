/**
 * 华为手表绑定页面
 * 
 * OAuth 2.0 授权流程：
 * 1. 用户点击"绑定华为手表"
 * 2. 获取授权 URL 并跳转到华为登录页
 * 3. 用户完成授权后，华为回调到我们的页面
 * 4. 提交授权码完成绑定
 */
import { useState, useEffect } from 'react';
import { View, Text, Button } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { get, post, del, getSilent } from '../../services/request';
import './index.scss';

interface DeviceCredential {
  id: number;
  device_type: string;
  auth_type: string;
  is_valid: boolean;
  sync_enabled: boolean;
  last_sync_at: string | null;
  last_error: string | null;
  config: Record<string, any>;
}

export default function HuaweiBinding() {
  const [loading, setLoading] = useState(true);
  const [binding, setBinding] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [credential, setCredential] = useState<DeviceCredential | null>(null);
  const [syncDays, setSyncDays] = useState(7);

  useEffect(() => {
    loadCredential();
    
    // 检查是否是 OAuth 回调
    const pages = Taro.getCurrentPages();
    const currentPage = pages[pages.length - 1];
    const query = currentPage?.options || {};
    
    if (query.code && query.state) {
      handleOAuthCallback(query.code, query.state);
    }
  }, []);

  const loadCredential = async () => {
    setLoading(true);
    try {
      const data = await getSilent<DeviceCredential>('/devices/me/huawei');
      setCredential(data);
    } catch (error) {
      // 404 表示未绑定
      setCredential(null);
    } finally {
      setLoading(false);
    }
  };

  // 开始 OAuth 授权
  const handleStartBinding = async () => {
    setBinding(true);
    try {
      // 获取当前页面路径作为回调地址
      // 注意：小程序中需要使用 web-view 跳转到 H5 页面完成授权
      // 这里先获取授权 URL
      const result = await get<{ auth_url: string; state: string }>('/devices/huawei/oauth/authorize', {
        redirect_uri: 'https://health.westwetlandtech.com/api/devices/huawei/oauth/callback'
      });
      
      // 显示提示
      Taro.showModal({
        title: '绑定华为手表',
        content: '即将跳转到华为登录页面完成授权。\n\n请在浏览器中完成登录和授权，授权成功后返回小程序刷新页面。',
        confirmText: '去授权',
        cancelText: '取消',
        success: (res) => {
          if (res.confirm) {
            // 复制授权链接到剪贴板（小程序无法直接跳转外部链接）
            Taro.setClipboardData({
              data: result.auth_url,
              success: () => {
                Taro.showToast({
                  title: '授权链接已复制',
                  icon: 'success',
                  duration: 2000
                });
              }
            });
          }
        }
      });
    } catch (error: any) {
      Taro.showToast({ 
        title: error.message || '获取授权链接失败', 
        icon: 'none' 
      });
    } finally {
      setBinding(false);
    }
  };

  // 处理 OAuth 回调（如果是 H5 版本）
  const handleOAuthCallback = async (code: string, state: string) => {
    Taro.showLoading({ title: '正在绑定...', mask: true });
    try {
      await post('/devices/huawei/oauth/callback', { code, state });
      Taro.hideLoading();
      Taro.showToast({ title: '绑定成功', icon: 'success' });
      loadCredential();
    } catch (error: any) {
      Taro.hideLoading();
      Taro.showToast({ 
        title: error.message || '绑定失败', 
        icon: 'none',
        duration: 3000 
      });
    }
  };

  // 测试连接
  const handleTestConnection = async () => {
    Taro.showLoading({ title: '测试中...', mask: true });
    try {
      const result = await post<{ success: boolean; message: string }>('/devices/huawei/test-connection');
      Taro.hideLoading();
      if (result.success) {
        Taro.showToast({ title: '连接正常 ✓', icon: 'success' });
      } else {
        Taro.showToast({ title: result.message || '连接失败', icon: 'none' });
      }
      loadCredential();
    } catch (error: any) {
      Taro.hideLoading();
      Taro.showToast({ title: error.message || '测试失败', icon: 'none' });
    }
  };

  // 同步数据
  const handleSync = async () => {
    setSyncing(true);
    Taro.showLoading({ title: `同步最近${syncDays}天...`, mask: true });
    try {
      const result = await post<{ success: boolean; message: string; synced_days: number }>(
        '/devices/huawei/sync',
        { days: syncDays }
      );
      Taro.hideLoading();
      if (result.success) {
        Taro.showToast({ 
          title: `同步成功 ${result.synced_days} 天`, 
          icon: 'success' 
        });
      } else {
        Taro.showToast({ title: result.message, icon: 'none' });
      }
      loadCredential();
    } catch (error: any) {
      Taro.hideLoading();
      Taro.showToast({ title: error.message || '同步失败', icon: 'none' });
    } finally {
      setSyncing(false);
    }
  };

  // 解除绑定
  const handleUnbind = () => {
    Taro.showModal({
      title: '确认解绑',
      content: '解绑后将无法自动同步华为手表数据，确定解绑吗？',
      success: async (res) => {
        if (res.confirm) {
          try {
            await del('/devices/huawei');
            Taro.showToast({ title: '已解绑', icon: 'success' });
            setCredential(null);
          } catch (error) {
            Taro.showToast({ title: '解绑失败', icon: 'none' });
          }
        }
      }
    });
  };

  // 切换同步开关
  const handleToggleSync = async (enabled: boolean) => {
    try {
      await post(`/devices/huawei/toggle-sync?enabled=${enabled}`);
      Taro.showToast({ 
        title: enabled ? '已开启自动同步' : '已关闭自动同步', 
        icon: 'success' 
      });
      loadCredential();
    } catch (error) {
      Taro.showToast({ title: '操作失败', icon: 'none' });
    }
  };

  if (loading) {
    return (
      <View className="huawei-page loading">
        <View className="loading-spinner" />
        <Text className="loading-text">加载中...</Text>
      </View>
    );
  }

  return (
    <View className="huawei-page">
      {/* 状态卡片 */}
      <View className="status-card">
        <View className="status-icon">
          {credential ? (credential.is_valid ? '⌚' : '⚠️') : '📱'}
        </View>
        <View className="status-info">
          <Text className="status-title">
            {credential 
              ? (credential.is_valid ? '华为手表已绑定' : '授权已失效') 
              : '未绑定华为手表'}
          </Text>
          <Text className="status-desc">
            {credential 
              ? (credential.last_sync_at 
                  ? `上次同步: ${new Date(credential.last_sync_at).toLocaleString()}` 
                  : '尚未同步')
              : '绑定后可自动同步运动健康数据'}
          </Text>
        </View>
      </View>

      {/* 已绑定状态 */}
      {credential && (
        <View className="bound-section">
          {/* 状态信息 */}
          {credential.last_error && (
            <View className="error-box">
              <Text className="error-icon">⚠️</Text>
              <Text className="error-text">{credential.last_error}</Text>
            </View>
          )}

          {/* 手动同步 */}
          <View className="sync-section">
            <Text className="section-title">手动同步</Text>
            <View className="sync-days-row">
              {[1, 3, 7, 14, 30].map(days => (
                <View 
                  key={days}
                  className={`day-btn ${syncDays === days ? 'active' : ''}`}
                  onClick={() => setSyncDays(days)}
                >
                  <Text>{days}天</Text>
                </View>
              ))}
            </View>
            <Button 
              className="sync-btn"
              onClick={handleSync}
              loading={syncing}
              disabled={syncing || !credential.is_valid}
            >
              {syncing ? '同步中...' : `🔄 同步最近${syncDays}天数据`}
            </Button>
          </View>

          {/* 操作按钮 */}
          <View className="action-row">
            <Button 
              className="action-btn test" 
              onClick={handleTestConnection}
            >
              🔍 测试连接
            </Button>
            <Button 
              className="action-btn unbind" 
              onClick={handleUnbind}
            >
              🗑️ 解除绑定
            </Button>
          </View>

          {/* 重新授权（如果失效） */}
          {!credential.is_valid && (
            <View className="reauth-section">
              <Text className="reauth-tip">授权已失效，请重新授权</Text>
              <Button 
                className="reauth-btn"
                onClick={handleStartBinding}
                loading={binding}
              >
                🔄 重新授权
              </Button>
            </View>
          )}
        </View>
      )}

      {/* 未绑定状态 */}
      {!credential && (
        <View className="unbind-section">
          <View className="feature-list">
            <Text className="feature-title">绑定后可同步</Text>
            <View className="feature-item">
              <Text className="feature-icon">❤️</Text>
              <Text className="feature-text">心率数据</Text>
            </View>
            <View className="feature-item">
              <Text className="feature-icon">🚶</Text>
              <Text className="feature-text">步数与距离</Text>
            </View>
            <View className="feature-item">
              <Text className="feature-icon">😴</Text>
              <Text className="feature-text">睡眠记录</Text>
            </View>
            <View className="feature-item">
              <Text className="feature-icon">🔥</Text>
              <Text className="feature-text">卡路里消耗</Text>
            </View>
            <View className="feature-item">
              <Text className="feature-icon">💨</Text>
              <Text className="feature-text">血氧饱和度</Text>
            </View>
            <View className="feature-item">
              <Text className="feature-icon">😰</Text>
              <Text className="feature-text">压力监测</Text>
            </View>
          </View>

          <View className="tip-box">
            <Text className="tip-icon">💡</Text>
            <Text className="tip-text">
              需要华为手表配合华为运动健康 App 使用。点击绑定后将跳转到华为授权页面完成授权。
            </Text>
          </View>

          <Button 
            className="bind-btn"
            onClick={handleStartBinding}
            loading={binding}
            disabled={binding}
          >
            {binding ? '获取授权中...' : '⌚ 绑定华为手表'}
          </Button>
        </View>
      )}
    </View>
  );
}
