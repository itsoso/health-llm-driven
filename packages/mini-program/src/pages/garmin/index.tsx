/**
 * Garmin 绑定与同步页面
 */
import { useState, useEffect } from 'react';
import { View, Text, Input, Button, Switch } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { get, getSilent, post, del, getToken } from '../../services/request';
import './index.scss';

interface GarminCredential {
  id: number;
  is_cn: boolean;
  last_sync_at: string | null;
  sync_enabled: boolean;
  credentials_valid: boolean;
}

interface TestConnectionResponse {
  success: boolean;
  mfa_required: boolean;
  message: string;
  mfa_session_id?: string;
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
  
  // MFA 两步验证
  const [showMFA, setShowMFA] = useState(false);
  const [mfaCode, setMfaCode] = useState('');
  const [mfaSessionId, setMfaSessionId] = useState<string | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [mfaContext, setMfaContext] = useState<'test' | 'sync' | null>(null); // MFA验证的上下文
  const [pendingSyncDays, setPendingSyncDays] = useState<number | null>(null); // 待同步的天数
  const [authenticatedSessionId, setAuthenticatedSessionId] = useState<string | null>(null); // MFA验证成功后的session_id

  useEffect(() => {
    loadCredential();
  }, []);

  const loadCredential = async () => {
    setLoading(true);
    try {
      // 使用静默请求，避免404时显示错误toast
      const data = await getSilent<GarminCredential>('/auth/garmin/credentials');
      setCredential(data);
      if (data) {
        setIsCN(data.is_cn);
      }
    } catch (error) {
      // 404 表示未配置凭证，这是正常情况
      setCredential(null);
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
    setMfaContext('test'); // 设置为测试连接场景
    try {
      const result = await post<TestConnectionResponse>('/auth/garmin/test-connection', {
        garmin_email: email,
        garmin_password: password,
        is_cn: isCN,
      });
      
      if (result.success) {
        Taro.showToast({ title: '连接成功 ✓', icon: 'success' });
      } else if (result.mfa_required && result.mfa_session_id) {
        // 需要两步验证
        setMfaSessionId(result.mfa_session_id);
        setShowMFA(true);
        Taro.showToast({ 
          title: '需要两步验证', 
          icon: 'none',
          duration: 2000 
        });
      } else {
        Taro.showToast({ 
          title: result.message || '连接失败', 
          icon: 'none',
          duration: 3000 
        });
      }
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
  
  // 验证 MFA 验证码
  const handleVerifyMFA = async () => {
    if (!mfaCode || mfaCode.length !== 6) {
      Taro.showToast({ title: '请输入6位验证码', icon: 'none' });
      return;
    }
    
    if (!mfaSessionId) {
      Taro.showToast({ title: '验证状态已过期，请重新测试连接', icon: 'none' });
      setShowMFA(false);
      return;
    }
    
    setVerifying(true);
    try {
      const result = await post<{ success: boolean; message: string; session_id?: string }>('/auth/garmin/verify-mfa', {
        mfa_code: mfaCode,
        mfa_session_id: mfaSessionId,
      });
      
      if (result.success) {
        // 保存验证成功后的session_id
        const verifiedSessionId = result.session_id || null;
        if (verifiedSessionId) {
          setAuthenticatedSessionId(verifiedSessionId);
        }
        
        const isSyncContext = mfaContext === 'sync';
        
        if (isSyncContext) {
          // 同步场景：验证成功后自动触发同步
          Taro.showToast({ title: '验证成功，开始同步...', icon: 'success' });
          setShowMFA(false);
          setMfaCode('');
          setMfaSessionId(null);
          
          // 自动触发同步
          const syncDays = pendingSyncDays || 7;
          setPendingSyncDays(null);
          setMfaContext(null);
          
          // 延迟一下，让用户看到成功消息
          setTimeout(() => {
            if (!syncing) {
              handleSyncWithProgress(syncDays, verifiedSessionId);
            }
          }, 500);
        } else {
          // 测试连接场景
          Taro.showToast({ title: '验证成功 ✓', icon: 'success' });
          setShowMFA(false);
          setMfaCode('');
          setMfaSessionId(null);
        }
      } else {
        Taro.showToast({ 
          title: result.message || '验证失败', 
          icon: 'none',
          duration: 3000 
        });
      }
    } catch (error: any) {
      Taro.showToast({ 
        title: error.message || '验证失败', 
        icon: 'none',
        duration: 3000 
      });
    } finally {
      setVerifying(false);
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

  // 流式同步数据（带进度和MFA支持）
  const handleSyncWithProgress = async (days: number, sessionId: string | null = null) => {
    if (syncing) {
      Taro.showToast({ title: '同步已在进行中', icon: 'none' });
      return;
    }
    
    setSyncing(true);
    setMfaContext('sync');
    setPendingSyncDays(days);
    
    // 使用传入的sessionId，如果没有则使用状态中的authenticatedSessionId
    const mfaSessionIdToUse = sessionId || authenticatedSessionId;
    
    try {
      // 构建URL，如果有mfaSessionIdToUse则传递
      let url = `/auth/garmin/sync-stream?days=${days}`;
      if (mfaSessionIdToUse) {
        url += `&mfa_session_id=${encodeURIComponent(mfaSessionIdToUse)}`;
      }
      
      Taro.showLoading({ title: '正在连接Garmin...' });
      
      // 使用Taro.request处理SSE流
      const token = getToken();
      if (!token) {
        throw new Error('未登录');
      }
      
      // 小程序环境不支持SSE，使用普通POST请求
      // 如果有sessionId，通过URL参数传递；否则直接调用同步接口
      try {
        // 如果有sessionId，使用带sessionId的同步接口
        if (mfaSessionIdToUse) {
          // 使用带mfa_session_id的同步接口
          await post('/auth/garmin/sync', { days, mfa_session_id: mfaSessionIdToUse });
        } else {
          // 普通同步
          await post('/auth/garmin/sync', { days });
        }
        Taro.hideLoading();
        Taro.showToast({ 
          title: '同步完成 ✓', 
          icon: 'success',
          duration: 2000
        });
        loadCredential();
      } catch (syncError: any) {
        Taro.hideLoading();
        
        // 检查是否是MFA错误
        const errorMsg = syncError.message || '';
        const errorDetail = (syncError as any)?.detail || '';
        const fullErrorMsg = errorMsg + ' ' + errorDetail;
        
        if (fullErrorMsg.includes('两步验证') || fullErrorMsg.includes('MFA') || fullErrorMsg.includes('two-factor') || fullErrorMsg.includes('mfa_required')) {
          // 需要MFA，显示提示信息
          Taro.showModal({
            title: '需要两步验证',
            content: '您的Garmin账号需要两步验证。请先修改凭证并完成验证，然后再进行同步。',
            showCancel: false,
            confirmText: '去修改',
            success: (res) => {
              if (res.confirm) {
                setShowForm(true);
              }
            }
          });
        } else {
          Taro.showToast({ 
            title: errorMsg || '同步失败', 
            icon: 'none',
            duration: 3000
          });
        }
      }
    } catch (error: any) {
      Taro.hideLoading();
      Taro.showToast({ 
        title: error.message || '同步失败', 
        icon: 'none',
        duration: 3000
      });
    } finally {
      setSyncing(false);
      setMfaContext(null);
      setPendingSyncDays(null);
    }
  };
  
  // 同步数据
  const handleSync = async () => {
    handleSyncWithProgress(syncDays, authenticatedSessionId);
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

          {/* MFA 两步验证 */}
          {showMFA && (
            <View className="mfa-section">
              <View className="mfa-header">
                <Text className="mfa-icon">🔐</Text>
                <Text className="mfa-title">两步验证</Text>
              </View>
              <Text className="mfa-desc">
                您的Garmin账号已开启两步验证{'\n'}
                请打开验证器应用（或查看邮件/短信）输入6位验证码{'\n'}
                验证码每30秒更新一次
              </Text>
              <Input
                type="number"
                maxlength={6}
                value={mfaCode}
                onInput={(e) => setMfaCode(e.detail.value)}
                placeholder="请输入6位验证码"
                className="mfa-input"
              />
              <View className="mfa-actions">
                <Button 
                  className="mfa-btn cancel"
                  onClick={() => {
                    setShowMFA(false);
                    setMfaCode('');
                    setMfaSessionId(null);
                  }}
                >
                  取消
                </Button>
                <Button 
                  className="mfa-btn verify"
                  onClick={handleVerifyMFA}
                  loading={verifying}
                  disabled={verifying || mfaCode.length !== 6}
                >
                  ✓ 验证
                </Button>
              </View>
            </View>
          )}

          <View className="form-actions">
            <Button 
              className="form-btn test"
              onClick={handleTestConnection}
              loading={saving}
              disabled={saving || !email || !password || showMFA}
            >
              🔍 测试连接
            </Button>
            <Button 
              className="form-btn save"
              onClick={handleSave}
              loading={saving}
              disabled={saving || !email || !password || showMFA}
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
