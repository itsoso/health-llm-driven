/**
 * Garmin 绑定与同步页面
 */
import { useState, useEffect } from 'react';
import { View, Text, Input, Button, Switch } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { get, post, del } from '../../services/request';
import './index.scss';

interface GarminCredential {
  id: number;
  is_cn: boolean;
  last_sync_at: string | null;
  sync_enabled: boolean;
  credentials_valid: boolean;
}

export default function Garmin() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [credential, setCredential] = useState<GarminCredential | null>(null);
  const [showForm, setShowForm] = useState(false);
  
  // 表单
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isCN, setIsCN] = useState(false);
  const [syncDays, setSyncDays] = useState(7);

  useEffect(() => {
    loadCredential();
  }, []);

  const loadCredential = async () => {
    setLoading(true);
    try {
      const data = await get<GarminCredential>('/auth/garmin/credentials').catch(() => null);
      setCredential(data);
      if (data) {
        setIsCN(data.is_cn);
      }
    } catch (error) {
      console.error('加载凭证失败:', error);
    } finally {
      setLoading(false);
    }
  };

  // 测试连接
  const handleTestConnection = async () => {
    if (!email || !password) {
      Taro.showToast({ title: '请输入账号密码', icon: 'none' });
      return;
    }
    
    setSaving(true);
    try {
      await post('/auth/garmin/test-connection', {
        garmin_email: email,
        garmin_password: password,
        is_cn: isCN,
      });
      Taro.showToast({ title: '连接成功 ✓', icon: 'success' });
    } catch (error: any) {
      Taro.showToast({ 
        title: error.message || '连接失败', 
        icon: 'none',
        duration: 3000 
      });
    } finally {
      setSaving(false);
    }
  };

  // 保存凭证
  const handleSave = async () => {
    if (!email || !password) {
      Taro.showToast({ title: '请输入账号密码', icon: 'none' });
      return;
    }
    
    setSaving(true);
    try {
      await post('/auth/garmin/credentials', {
        garmin_email: email,
        garmin_password: password,
        is_cn: isCN,
      });
      Taro.showToast({ title: '保存成功 ✓', icon: 'success' });
      setShowForm(false);
      setEmail('');
      setPassword('');
      loadCredential();
    } catch (error: any) {
      Taro.showToast({ 
        title: error.message || '保存失败', 
        icon: 'none' 
      });
    } finally {
      setSaving(false);
    }
  };

  // 删除凭证
  const handleDelete = () => {
    Taro.showModal({
      title: '确认删除',
      content: '删除后将无法自动同步Garmin数据，确定删除吗？',
      success: async (res) => {
        if (res.confirm) {
          try {
            await del('/auth/garmin/credentials');
            Taro.showToast({ title: '已删除', icon: 'success' });
            setCredential(null);
          } catch (error) {
            Taro.showToast({ title: '删除失败', icon: 'none' });
          }
        }
      },
    });
  };

  // 同步数据
  const handleSync = async () => {
    setSyncing(true);
    try {
      Taro.showLoading({ title: `同步最近${syncDays}天...` });
      // 使用 /auth/garmin/sync 接口，传入 { days: N }
      await post('/auth/garmin/sync', { days: syncDays });
      Taro.hideLoading();
      Taro.showToast({ title: '同步完成 ✓', icon: 'success' });
      loadCredential();
    } catch (error: any) {
      Taro.hideLoading();
      Taro.showToast({ 
        title: error.message || '同步失败', 
        icon: 'none',
        duration: 3000
      });
    } finally {
      setSyncing(false);
    }
  };

  // 切换同步开关
  const handleToggleSync = async (enabled: boolean) => {
    try {
      await post('/auth/garmin/toggle-sync', { sync_enabled: enabled });
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
      <View className="garmin-page loading">
        <View className="loading-spinner" />
        <Text className="loading-text">加载中...</Text>
      </View>
    );
  }

  return (
    <View className="garmin-page">
      {/* 状态卡片 */}
      <View className="status-card">
        <View className="status-icon">
          {credential ? (credential.credentials_valid ? '✅' : '⚠️') : '⌚'}
        </View>
        <View className="status-info">
          <Text className="status-title">
            {credential 
              ? (credential.credentials_valid ? 'Garmin已绑定' : '凭证已失效') 
              : '未绑定Garmin'}
          </Text>
          <Text className="status-desc">
            {credential 
              ? (credential.last_sync_at 
                  ? `上次同步: ${new Date(credential.last_sync_at).toLocaleString()}` 
                  : '尚未同步')
              : '绑定后可自动同步运动数据'}
          </Text>
        </View>
      </View>

      {/* 已绑定状态 */}
      {credential && !showForm && (
        <View className="bound-section">
          {/* 自动同步开关 */}
          <View className="setting-item">
            <View className="setting-info">
              <Text className="setting-label">自动同步</Text>
              <Text className="setting-desc">每2小时自动同步数据</Text>
            </View>
            <Switch 
              checked={credential.sync_enabled} 
              onChange={(e) => handleToggleSync(e.detail.value)}
              color="#667eea"
            />
          </View>

          {/* 中国区开关 */}
          <View className="setting-item">
            <View className="setting-info">
              <Text className="setting-label">中国区账号</Text>
              <Text className="setting-desc">使用Garmin中国服务器</Text>
            </View>
            <Text className={`region-badge ${credential.is_cn ? 'cn' : 'global'}`}>
              {credential.is_cn ? '🇨🇳 中国' : '🌍 国际'}
            </Text>
          </View>

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
              disabled={syncing}
            >
              {syncing ? '同步中...' : `🔄 同步最近${syncDays}天数据`}
            </Button>
          </View>

          {/* 操作按钮 */}
          <View className="action-row">
            <Button className="action-btn edit" onClick={() => setShowForm(true)}>
              ✏️ 修改凭证
            </Button>
            <Button className="action-btn delete" onClick={handleDelete}>
              🗑️ 解除绑定
            </Button>
          </View>
        </View>
      )}

      {/* 绑定表单 */}
      {(!credential || showForm) && (
        <View className="form-section">
          <Text className="form-title">
            {credential ? '修改Garmin凭证' : '绑定Garmin账号'}
          </Text>
          
          <View className="form-item">
            <Text className="form-label">Garmin邮箱</Text>
            <Input
              type="text"
              value={email}
              onInput={(e) => setEmail(e.detail.value)}
              placeholder="请输入Garmin Connect邮箱"
              className="form-input"
            />
          </View>

          <View className="form-item">
            <Text className="form-label">Garmin密码</Text>
            <Input
              type="text"
              password
              value={password}
              onInput={(e) => setPassword(e.detail.value)}
              placeholder="请输入Garmin Connect密码"
              className="form-input"
            />
          </View>

          <View className="form-item switch-item">
            <View className="switch-info">
              <Text className="form-label">中国区账号</Text>
              <Text className="form-hint">在中国购买的Garmin设备请开启</Text>
            </View>
            <Switch 
              checked={isCN} 
              onChange={(e) => setIsCN(e.detail.value)}
              color="#667eea"
            />
          </View>

          <View className="tip-box">
            <Text className="tip-icon">💡</Text>
            <Text className="tip-text">
              您的凭证将被加密存储，仅用于同步Garmin数据。我们不会保存您的明文密码。
            </Text>
          </View>

          <View className="form-actions">
            <Button 
              className="form-btn test"
              onClick={handleTestConnection}
              loading={saving}
              disabled={saving || !email || !password}
            >
              🔍 测试连接
            </Button>
            <Button 
              className="form-btn save"
              onClick={handleSave}
              loading={saving}
              disabled={saving || !email || !password}
            >
              💾 保存凭证
            </Button>
          </View>

          {showForm && (
            <Button 
              className="cancel-btn"
              onClick={() => {
                setShowForm(false);
                setEmail('');
                setPassword('');
              }}
            >
              取消
            </Button>
          )}
        </View>
      )}
    </View>
  );
}
