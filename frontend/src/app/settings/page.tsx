'use client';

import { useState, useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import ProtectedRoute from '@/components/ProtectedRoute';
import {
  assistantOpenclawBindingApi,
  AssistantOpenClawBindingStatus,
  deviceApi,
  withingsApi,
} from '@/services/api';
import { formatDateTime } from '@/utils/timezone';

function extractErrorMsg(error: any, fallback: string): string {
  const detail = error?.response?.data?.detail;
  if (!detail) return error?.message || fallback;
  if (typeof detail === 'string') return detail;
  return JSON.stringify(detail);
}

// 使用相对路径，通过Next.js代理到后端
const API_BASE = '/api';

interface GarminCredential {
  id: number;
  garmin_email: string;
  is_cn: boolean;
  last_sync_at: string | null;
  sync_enabled: boolean;
}

function SettingsContent() {
  const router = useRouter();
  const { user, token, isAuthenticated, isLoading: authLoading, logout, refreshUser } = useAuth();
  const queryClient = useQueryClient();
  const garminSectionRef = useRef<HTMLDivElement>(null);
  const assistantOpenclawSectionRef = useRef<HTMLDivElement>(null);

  const [garminForm, setGarminForm] = useState({
    garmin_email: '',
    garmin_password: '',
    is_cn: false,
  });
  const [showGarminForm, setShowGarminForm] = useState(false);
  const [showGarminPassword, setShowGarminPassword] = useState(false);
  const [syncDays, setSyncDays] = useState(1);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [highlightGarmin, setHighlightGarmin] = useState(false);
  const [highlightAssistantOpenClaw, setHighlightAssistantOpenClaw] = useState(false);
  const [assistantOpenclawForm, setAssistantOpenclawForm] = useState({
    display_name: '我的 OpenClaw',
    gateway_url: 'http://127.0.0.1:28789',
    gateway_token: '',
    enabled: false,
  });
  
  // MFA 两步验证状态
  const [showMFA, setShowMFA] = useState(false);
  const [mfaCode, setMfaCode] = useState('');
  const [mfaSessionId, setMfaSessionId] = useState<string | null>(null);
  const [mfaContext, setMfaContext] = useState<'test' | 'sync' | null>(null); // MFA验证的上下文：测试连接或同步
  const [pendingSyncDays, setPendingSyncDays] = useState<number | null>(null); // 待同步的天数（如果是在同步场景）
  const [authenticatedSessionId, setAuthenticatedSessionId] = useState<string | null>(null); // MFA验证成功后的session_id，用于复用认证状态
  
  // Apple Watch 状态
  const [appleFile, setAppleFile] = useState<File | null>(null);

  // API Key 管理状态
  interface UserApiKey {
    id: number;
    name: string;
    api_key: string | null;
    scopes: string;
    is_active: boolean;
    last_used_at: string | null;
    created_at: string;
  }
  const [apiKeys, setApiKeys] = useState<UserApiKey[]>([]);
  const [showApiKeySection, setShowApiKeySection] = useState(false);
  const [newKeyName, setNewKeyName] = useState('');
  const [newlyCreatedKey, setNewlyCreatedKey] = useState<string | null>(null); // 新创建的Key，用于展示
  const [appleImportProgress, setAppleImportProgress] = useState<{
    isImporting: boolean;
    progress: number;
    message: string;
  }>({
    isImporting: false,
    progress: 0,
    message: '',
  });

  // 隐私设置状态
  interface PrivacySettings {
    weight: boolean;
    height: boolean;
    age: boolean;
    gender: boolean;
    city: boolean;
    location: boolean;
  }
  interface DetectedLocation {
    city: string | null;
    region: string | null;
    country: string | null;
  }
  interface ManualLocation {
    city: string | null;
    region: string | null;
    country: string | null;
  }
  interface UserProfile {
    privacy_settings: PrivacySettings;
    detected_location: DetectedLocation | null;
    manual_location: ManualLocation | null;
    use_manual_location: boolean;
    location_updated_at: string | null;
    city: string | null;
  }
  const [showPrivacySection, setShowPrivacySection] = useState(false);
  const [showQuickRecordSection, setShowQuickRecordSection] = useState(true);

  // Web登录绑定状态
  const [showBindForm, setShowBindForm] = useState(false);
  const [bindEmail, setBindEmail] = useState('');
  const [bindPassword, setBindPassword] = useState('');
  const [bindLoading, setBindLoading] = useState(false);
  // 修改密码
  const [showChangePassword, setShowChangePassword] = useState(false);
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [changePwdLoading, setChangePwdLoading] = useState(false);

  // 用户名编辑状态
  const [isEditingName, setIsEditingName] = useState(false);
  const [editName, setEditName] = useState('');

  // 同步进度状态
  const [syncProgress, setSyncProgress] = useState<{
    isSyncing: boolean;
    current: number;
    total: number;
    currentDate: string;
    synced: number;
    failed: number;
    message: string;
  }>({
    isSyncing: false,
    current: 0,
    total: 0,
    currentDate: '',
    synced: 0,
    failed: 0,
    message: '',
  });

  // 获取Garmin凭证
  const { data: garminCredential, isLoading: garminLoading } = useQuery({
    queryKey: ['garmin-credential'],
    queryFn: async () => {
      if (!token) return null;
      const res = await fetch(`${API_BASE}/auth/garmin/credentials`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (res.status === 404) return null;
      if (!res.ok) throw new Error('获取失败');
      return res.json() as Promise<GarminCredential>;
    },
    enabled: !!token,
  });

  const { data: assistantBinding, isLoading: assistantBindingLoading, refetch: refetchAssistantBinding } = useQuery({
    queryKey: ['assistant-openclaw-binding'],
    queryFn: async () => {
      const res = await assistantOpenclawBindingApi.getMe();
      return res.data as AssistantOpenClawBindingStatus;
    },
    enabled: !!token,
  });

  // 获取 Apple Watch 设备信息
  const { data: appleDevice, isLoading: appleLoading, refetch: refetchApple } = useQuery({
    queryKey: ['apple-device'],
    queryFn: async () => {
      try {
        const res = await deviceApi.getDeviceCredential('apple');
        return res.data;
      } catch (error: any) {
        if (error.response?.status === 404) return null;
        throw error;
      }
    },
    enabled: !!token,
  });

  // 获取 Withings 绑定状态
  const { data: withingsStatus, isLoading: withingsLoading, refetch: refetchWithings } = useQuery({
    queryKey: ['withings-status'],
    queryFn: async () => {
      try {
        const res = await withingsApi.getStatus();
        return res.data;
      } catch (error: any) {
        if (error.response?.status === 404) return null;
        throw error;
      }
    },
    enabled: !!token,
  });

  // Withings OAuth 授权
  const withingsAuthMutation = useMutation({
    mutationFn: async () => {
      const res = await withingsApi.getOAuthUrl();
      return res.data;
    },
    onSuccess: (data) => {
      if (data.auth_url) {
        window.open(data.auth_url, '_blank');
        setMessage({ type: 'success', text: '已打开 Withings 授权页面，请在新窗口中完成授权' });
      }
    },
    onError: (error: any) => {
      setMessage({ type: 'error', text: extractErrorMsg(error, '获取授权链接失败') });
    },
  });

  // Withings 手动同步
  const withingsSyncMutation = useMutation({
    mutationFn: (days: number) => withingsApi.syncData(days),
    onSuccess: (data) => {
      setMessage({ type: 'success', text: data.data.message || 'Withings 数据同步成功' });
      refetchWithings();
      queryClient.invalidateQueries({ queryKey: ['daily-health'] });
    },
    onError: (error: any) => {
      setMessage({ type: 'error', text: extractErrorMsg(error, '同步失败') });
    },
  });

  useEffect(() => {
    if (!assistantBinding) return;
    setAssistantOpenclawForm(prev => ({
      ...prev,
      display_name: assistantBinding.display_name || '我的 OpenClaw',
      gateway_url: assistantBinding.gateway_url || 'http://127.0.0.1:28789',
      gateway_token: '',
      enabled: assistantBinding.enabled,
    }));
  }, [assistantBinding]);

  const saveAssistantOpenclawMutation = useMutation({
    mutationFn: async () => {
      const payload: {
        display_name: string;
        gateway_url: string;
        enabled: boolean;
        gateway_token?: string;
      } = {
        display_name: assistantOpenclawForm.display_name.trim() || '我的 OpenClaw',
        gateway_url: assistantOpenclawForm.gateway_url.trim(),
        enabled: assistantOpenclawForm.enabled,
      };
      if (assistantOpenclawForm.gateway_token.trim()) {
        payload.gateway_token = assistantOpenclawForm.gateway_token.trim();
      }
      return assistantOpenclawBindingApi.update(payload);
    },
    onSuccess: async (res) => {
      setMessage({ type: 'success', text: res.data.message || 'OpenClaw 绑定已保存' });
      setAssistantOpenclawForm(prev => ({ ...prev, gateway_token: '' }));
      await refetchAssistantBinding();
    },
    onError: (error: any) => {
      setMessage({ type: 'error', text: extractErrorMsg(error, '保存 OpenClaw 绑定失败') });
    },
  });

  const testAssistantOpenclawMutation = useMutation({
    mutationFn: async () => {
      const payload: { gateway_url?: string; gateway_token?: string } = {};
      if (assistantOpenclawForm.gateway_url.trim()) {
        payload.gateway_url = assistantOpenclawForm.gateway_url.trim();
      }
      if (assistantOpenclawForm.gateway_token.trim()) {
        payload.gateway_token = assistantOpenclawForm.gateway_token.trim();
      }
      return assistantOpenclawBindingApi.test(payload);
    },
    onSuccess: (res) => {
      const result = res.data;
      setMessage({
        type: result.status === 'active' ? 'success' : 'error',
        text: `${result.message}${result.latency_ms ? `（${result.latency_ms}ms）` : ''}`,
      });
      refetchAssistantBinding();
    },
    onError: (error: any) => {
      setMessage({ type: 'error', text: extractErrorMsg(error, '测试 OpenClaw 连接失败') });
    },
  });

  const deleteAssistantOpenclawMutation = useMutation({
    mutationFn: async () => assistantOpenclawBindingApi.remove(),
    onSuccess: async () => {
      setMessage({ type: 'success', text: '已解绑智能助理专用 OpenClaw' });
      setAssistantOpenclawForm({
        display_name: '我的 OpenClaw',
        gateway_url: 'http://127.0.0.1:28789',
        gateway_token: '',
        enabled: false,
      });
      await refetchAssistantBinding();
    },
    onError: (error: any) => {
      setMessage({ type: 'error', text: extractErrorMsg(error, '解绑 OpenClaw 失败') });
    },
  });

  // 解绑 Withings
  const unbindWithingsMutation = useMutation({
    mutationFn: () => deviceApi.unbindDevice('withings'),
    onSuccess: () => {
      setMessage({ type: 'success', text: '已解绑 Withings' });
      refetchWithings();
    },
    onError: (error: any) => {
      setMessage({ type: 'error', text: extractErrorMsg(error, '解绑失败') });
    },
  });

  // 获取用户画像（隐私设置）
  const { data: userProfile, isLoading: profileLoading, refetch: refetchProfile } = useQuery({
    queryKey: ['user-profile'],
    queryFn: async () => {
      if (!token) return null;
      const res = await fetch(`${API_BASE}/profile/me`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (!res.ok) throw new Error('获取用户画像失败');
      return res.json() as Promise<UserProfile>;
    },
    enabled: !!token,
  });

  // 更新用户名
  const updateNameMutation = useMutation({
    mutationFn: async (name: string) => {
      const res = await fetch(`${API_BASE}/auth/me`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({ name }),
      });
      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || '更新失败');
      }
      return res.json();
    },
    onSuccess: () => {
      refreshUser();
      setIsEditingName(false);
      setMessage({ type: 'success', text: '用户名已更新' });
    },
    onError: (error: Error) => {
      setMessage({ type: 'error', text: error.message });
    },
  });

  // 更新用户画像（隐私设置）
  const updateProfileMutation = useMutation({
    mutationFn: async (data: { privacy_settings: PrivacySettings }) => {
      const res = await fetch(`${API_BASE}/profile/me`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify(data),
      });
      if (!res.ok) throw new Error('更新失败');
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['user-profile'] });
      setMessage({ type: 'success', text: '隐私设置已更新' });
    },
    onError: (error: Error) => {
      setMessage({ type: 'error', text: error.message });
    },
  });

  // 刷新位置
  const refreshLocationMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch(`${API_BASE}/profile/me/refresh-location`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (!res.ok) throw new Error('刷新位置失败');
      return res.json();
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['user-profile'] });
      if (data.success) {
        setMessage({ type: 'success', text: `位置已更新: ${data.location?.city || '未知'}` });
      } else {
        setMessage({ type: 'error', text: data.message || '无法获取位置' });
      }
    },
    onError: (error: Error) => {
      setMessage({ type: 'error', text: error.message });
    },
  });

  // 手工位置表单状态
  const [manualLocationForm, setManualLocationForm] = useState({
    city: '',
    region: '',
    country: '中国',
  });

  // 更新手工位置
  const updateManualLocationMutation = useMutation({
    mutationFn: async (data: { use_manual_location: boolean; city?: string; region?: string; country?: string }) => {
      const res = await fetch(`${API_BASE}/profile/me/manual-location`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify(data),
      });
      if (!res.ok) throw new Error('更新失败');
      return res.json();
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['user-profile'] });
      if (data.success) {
        setMessage({ type: 'success', text: data.use_manual_location ? '已切换为手工输入位置' : '已切换为IP自动定位' });
      }
    },
    onError: (error: Error) => {
      setMessage({ type: 'error', text: error.message });
    },
  });

  // 当用户画像加载完成时，初始化手工位置表单
  useEffect(() => {
    if (userProfile?.manual_location) {
      setManualLocationForm({
        city: userProfile.manual_location.city || '',
        region: userProfile.manual_location.region || '',
        country: userProfile.manual_location.country || '中国',
      });
    }
  }, [userProfile]);

  // 导入 Apple Health 文件
  const importAppleMutation = useMutation({
    mutationFn: async (file: File) => {
      setAppleImportProgress({ isImporting: true, progress: 0, message: '上传文件中...' });
      const result = await deviceApi.importAppleHealth(file);
      setAppleImportProgress({ isImporting: true, progress: 50, message: '解析数据中...' });
      return result;
    },
    onSuccess: (data) => {
      setAppleImportProgress({ isImporting: false, progress: 100, message: '导入成功！' });
      setMessage({ type: 'success', text: data.data.message || 'Apple Health 数据导入成功！' });
      setAppleFile(null);
      refetchApple();
      queryClient.invalidateQueries({ queryKey: ['apple-device'] });
      setTimeout(() => {
        setAppleImportProgress({ isImporting: false, progress: 0, message: '' });
      }, 3000);
    },
    onError: (error: any) => {
      setAppleImportProgress({ isImporting: false, progress: 0, message: '' });
      const errorMsg = extractErrorMsg(error, '导入失败，请重试');
      setMessage({ type: 'error', text: errorMsg });
    },
  });

  // 测试 Apple 连接
  const testAppleMutation = useMutation({
    mutationFn: () => deviceApi.testAppleConnection(),
    onSuccess: (data) => {
      setMessage({ type: 'success', text: data.data.message || '连接测试成功！' });
      refetchApple();
    },
    onError: (error: any) => {
      const errorMsg = extractErrorMsg(error, '测试失败');
      setMessage({ type: 'error', text: errorMsg });
    },
  });

  // 同步 Apple 数据
  const syncAppleMutation = useMutation({
    mutationFn: (days: number) => deviceApi.syncAppleData(days),
    onSuccess: (data) => {
      setMessage({ type: 'success', text: data.data.message || '同步成功！' });
      queryClient.invalidateQueries({ queryKey: ['garmin-data'] });
      queryClient.invalidateQueries({ queryKey: ['daily-health'] });
    },
    onError: (error: any) => {
      const errorMsg = extractErrorMsg(error, '同步失败');
      setMessage({ type: 'error', text: errorMsg });
    },
  });

  // 保存Garmin凭证
  const saveGarminMutation = useMutation({
    mutationFn: async (data: { garmin_email: string; garmin_password: string; is_cn: boolean }) => {
      const res = await fetch(`${API_BASE}/auth/garmin/credentials`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify(data),
      });
      
      // 检查响应内容类型
      const contentType = res.headers.get('content-type');
      if (!contentType || !contentType.includes('application/json')) {
        const text = await res.text();
        console.error('服务器返回非JSON响应:', text);
        throw new Error('服务器错误，请稍后重试');
      }
      
      const result = await res.json();
      if (!res.ok) {
        throw new Error(result.detail || '保存失败');
      }
      return result;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['garmin-credential'] });
      refreshUser();
      setShowGarminForm(false);
      setGarminForm({ garmin_email: '', garmin_password: '', is_cn: false });
      setMessage({ type: 'success', text: 'Garmin凭证保存成功！' });
    },
    onError: (error: Error) => {
      setMessage({ type: 'error', text: error.message });
    },
  });

  // 删除Garmin凭证
  const deleteGarminMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch(`${API_BASE}/auth/garmin/credentials`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` },
      });
      
      // 检查响应内容类型
      const contentType = res.headers.get('content-type');
      if (!contentType || !contentType.includes('application/json')) {
        const text = await res.text();
        console.error('服务器返回非JSON响应:', text);
        throw new Error('服务器错误，请稍后重试');
      }
      
      const result = await res.json();
      if (!res.ok) {
        throw new Error(result.detail || '删除失败');
      }
      return result;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['garmin-credential'] });
      refreshUser();
      setMessage({ type: 'success', text: 'Garmin凭证已删除' });
    },
    onError: (error: Error) => {
      setMessage({ type: 'error', text: error.message });
    },
  });

  // 切换同步状态
  const toggleSyncMutation = useMutation({
    mutationFn: async (enabled: boolean) => {
      const res = await fetch(`${API_BASE}/auth/garmin/toggle-sync?enabled=${enabled}`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
      });
      
      const contentType = res.headers.get('content-type');
      if (!contentType || !contentType.includes('application/json')) {
        const text = await res.text();
        console.error('服务器返回非JSON响应:', text);
        throw new Error('服务器错误，请稍后重试');
      }
      
      const result = await res.json();
      if (!res.ok) {
        throw new Error(result.detail || '操作失败');
      }
      return result;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['garmin-credential'] });
      setMessage({ type: 'success', text: data.message });
    },
    onError: (error: Error) => {
      setMessage({ type: 'error', text: error.message });
    },
  });

  // 测试Garmin连接
  const testConnectionMutation = useMutation({
    mutationFn: async (data: { garmin_email: string; garmin_password: string; is_cn: boolean }) => {
      const res = await fetch(`${API_BASE}/auth/garmin/test-connection`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify(data),
      });
      
      // 检查响应内容类型
      const contentType = res.headers.get('content-type');
      if (!contentType || !contentType.includes('application/json')) {
        const text = await res.text();
        console.error('服务器返回非JSON响应:', text);
        return { success: false, mfa_required: false, message: '服务器错误，请稍后重试' };
      }
      
      return res.json();
    },
    onSuccess: (data) => {
      if (data.success) {
        setMessage({ type: 'success', text: data.message });
        setShowMFA(false);
        setMfaCode('');
        setMfaSessionId(null);
        setMfaContext(null);
        setPendingSyncDays(null);
      } else if (data.mfa_required && data.mfa_session_id) {
        // 需要两步验证
        setMfaSessionId(data.mfa_session_id);
        setMfaContext('test'); // 标记为测试连接场景
        setShowMFA(true);
        setMessage({ type: 'error', text: '🔐 需要两步验证，请输入验证码' });
      } else {
        setMessage({ type: 'error', text: data.message });
      }
    },
    onError: (error: Error) => {
      setMessage({ type: 'error', text: error.message });
    },
  });
  
  // MFA验证
  const verifyMFAMutation = useMutation({
    mutationFn: async () => {
      if (!mfaSessionId) throw new Error('验证状态已过期');
      
      console.log('🔐 发送MFA验证请求:', { mfaSessionId, mfaCodeLength: mfaCode.length });
      
      const res = await fetch(`${API_BASE}/auth/garmin/verify-mfa`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          mfa_code: mfaCode,
          mfa_session_id: mfaSessionId,
        }),
      });
      
      const contentType = res.headers.get('content-type');
      if (!contentType || !contentType.includes('application/json')) {
        throw new Error('服务器错误');
      }
      
      return res.json();
    },
    onSuccess: (data) => {
      console.log('✅ MFA验证成功回调:', { success: data.success, session_id: data.session_id, mfaContext });
      if (data.success) {
        const isSyncContext = mfaContext === 'sync';
        
        // 保存验证成功后的session_id到闭包变量和状态
        const verifiedSessionId = data.session_id;
        if (verifiedSessionId) {
          setAuthenticatedSessionId(verifiedSessionId);
          console.log('✅ 保存已验证的MFA session_id:', verifiedSessionId);
        } else {
          console.warn('⚠️ MFA验证成功但未返回session_id');
        }
        
        if (isSyncContext) {
          // 同步场景：验证成功后自动触发同步
          setMessage({ type: 'success', text: '✅ 验证成功！正在开始同步...' });
          setShowMFA(false);
          setMfaCode('');
          setMfaSessionId(null);
          
          // 自动触发同步
          const syncDays = pendingSyncDays || 1;
          setPendingSyncDays(null);
          
          // 清除MFA上下文，防止重复触发
          setMfaContext(null);
          
          // 延迟一下，让用户看到成功消息
          // 直接使用闭包中的verifiedSessionId，不依赖状态更新
          setTimeout(() => {
            // 再次检查是否已经在同步中
            if (!syncProgress.isSyncing) {
              console.log('✅ MFA验证成功，自动触发同步:', syncDays, '天', '使用session_id:', verifiedSessionId);
              // 直接传递闭包中的verifiedSessionId，确保使用正确的值
              startSyncWithProgressWithSessionId(syncDays, verifiedSessionId);
            } else {
              console.log('⚠️ 同步已在进行中，跳过自动触发');
            }
          }, 500);
        } else {
          // 测试连接场景：提示可以保存凭证
          setMessage({ type: 'success', text: data.message || '✅ 验证成功！Garmin账号连接成功，可以保存凭证了。' });
          setShowMFA(false);
          setMfaCode('');
          setMfaSessionId(null);
          setMfaContext(null);
        }
        
        // 刷新凭证状态
        queryClient.invalidateQueries({ queryKey: ['garmin-credential'] });
      } else {
        // 改进错误提示
        let errorMsg = data.message;
        if (errorMsg.includes('Couldn\'t find ticket') || errorMsg.includes('验证失败')) {
          errorMsg = '❌ 验证码错误或已过期！请检查验证器应用中的最新验证码（每30秒更新一次）。';
        }
        setMessage({ type: 'error', text: errorMsg });
      }
    },
    onError: (error: Error) => {
      let errorMsg = error.message;
      // 如果是验证失败的错误，提供更友好的提示
      if (errorMsg.includes('Couldn\'t find ticket') || errorMsg.includes('验证失败')) {
        errorMsg = '❌ 验证码错误或已过期！请检查验证器应用中的最新验证码（每30秒更新一次）。';
      }
      setMessage({ type: 'error', text: errorMsg });
    },
  });

  // 流式同步Garmin数据（带进度）
  const startSyncWithProgress = async (days: number) => {
    startSyncWithProgressWithSessionId(days, authenticatedSessionId);
  };
  
  // 带session_id的同步函数（内部使用）
  const startSyncWithProgressWithSessionId = async (days: number, sessionId: string | null = null) => {
    if (!token) return;
    
    // 防止重复调用
    if (syncProgress.isSyncing) {
      console.log('⚠️ 同步已在进行中，忽略重复调用');
      return;
    }
    
    // 使用传入的sessionId，如果没有则使用状态中的authenticatedSessionId
    const mfaSessionIdToUse = sessionId || authenticatedSessionId;
    
    setMfaContext('sync'); // 设置MFA场景为同步
    setPendingSyncDays(days); // 记录待同步天数
    
    setSyncProgress({
      isSyncing: true,
      current: 0,
      total: days,
      currentDate: '',
      synced: 0,
      failed: 0,
      message: '正在连接Garmin...',
    });
    setMessage(null);
    
    try {
      // 构建URL，如果有mfaSessionIdToUse则传递
      let url = `${API_BASE}/auth/garmin/sync-stream?days=${days}`;
      if (mfaSessionIdToUse) {
        url += `&mfa_session_id=${mfaSessionIdToUse}`;
        console.log('✅ 使用已认证的MFA session进行同步:', mfaSessionIdToUse);
      } else {
        console.log('⚠️ 没有已认证的MFA session，将重新检测MFA');
      }
      
      const response = await fetch(url, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });
      
      if (!response.ok) {
        throw new Error('同步请求失败');
      }
      
      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('无法读取响应');
      }
      
      const decoder = new TextDecoder();
      
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        
        const text = decoder.decode(value);
        const lines = text.split('\n');
        
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              console.log('收到SSE消息:', data); // 调试日志
              
              if (data.type === 'progress') {
                setSyncProgress(prev => ({
                  ...prev,
                  current: data.current,
                  total: data.total,
                  currentDate: data.date || '',
                  synced: data.synced || prev.synced,
                  failed: data.failed || prev.failed,
                  message: data.message,
                }));
              } else if (data.type === 'complete') {
                setSyncProgress(prev => ({
                  ...prev,
                  isSyncing: false,
                  synced: data.synced,
                  failed: data.failed,
                  message: data.message,
                }));
                queryClient.invalidateQueries({ queryKey: ['garmin-credential'] });
                setMessage({ type: 'success', text: data.message });
              } else if (data.type === 'error') {
                setSyncProgress(prev => ({ ...prev, isSyncing: false }));
                console.log('收到错误消息:', data); // 调试日志
                // 检查是否是MFA错误
                if (data.mfa_required) {
                  console.log('检测到MFA要求:', { mfa_session_id: data.mfa_session_id, showGarminForm }); // 调试日志
                  if (data.mfa_session_id) {
                    setMfaSessionId(data.mfa_session_id);
                    setMfaContext('sync'); // 标记为同步场景
                    setPendingSyncDays(days); // 保存待同步的天数
                    setShowMFA(true);
                    console.log('设置MFA状态:', { showMFA: true, mfaSessionId: data.mfa_session_id, showGarminForm }); // 调试日志
                    setMessage({ type: 'error', text: '🔐 需要两步验证，请输入验证码' });
                  } else {
                    setMessage({ type: 'error', text: data.message || '需要两步验证，请先在设置页面完成MFA验证' });
                  }
                } else {
                  setMessage({ type: 'error', text: data.message });
                }
              }
            } catch (e) {
              // 忽略解析错误
            }
          }
        }
      }
    } catch (error: any) {
      setSyncProgress(prev => ({ ...prev, isSyncing: false }));
      const errorMsg = error.message || '同步失败';
      // 检查是否是MFA错误
      if (errorMsg.includes('两步验证') || errorMsg.includes('MFA') || errorMsg.includes('two-factor')) {
        setMessage({ type: 'error', text: '🔐 ' + errorMsg + ' 请先在设置页面完成MFA验证，然后再尝试同步。' });
      } else {
        setMessage({ type: 'error', text: errorMsg });
      }
    }
  };

  // 保留原来的同步方法作为备用
  const syncGarminMutation = useMutation({
    mutationFn: async (days: number) => {
      const res = await fetch(`${API_BASE}/auth/garmin/sync`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({ days }),
      });
      
      // 检查响应内容类型
      const contentType = res.headers.get('content-type');
      if (!contentType || !contentType.includes('application/json')) {
        const text = await res.text();
        console.error('服务器返回非JSON响应:', text);
        throw new Error('服务器错误，请稍后重试');
      }
      
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || '同步失败');
      }
      return data;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['garmin-credential'] });
      setMessage({ type: 'success', text: data.message });
    },
    onError: (error: Error) => {
      setMessage({ type: 'error', text: error.message });
    },
  });

  // API Key 管理函数
  const loadApiKeys = async () => {
    if (!token) return;
    try {
      const res = await fetch(`${API_BASE}/user-api-keys`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        setApiKeys(await res.json());
      }
    } catch (error) {
      console.error('获取 API Keys 失败:', error);
    }
  };

  const handleCreateApiKey = async () => {
    if (!token || !newKeyName.trim()) {
      setMessage({ type: 'error', text: 'API Key 名称不能为空' });
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/user-api-keys`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ name: newKeyName.trim() }),
      });

      if (res.ok) {
        const newKey = await res.json();
        // 保存新创建的Key用于展示
        if (newKey.api_key) {
          setNewlyCreatedKey(newKey.api_key);
          // 复制到剪贴板
          try {
            await navigator.clipboard.writeText(newKey.api_key);
            setMessage({ type: 'success', text: 'API Key 已创建并复制到剪贴板！请妥善保存，此密钥只显示一次。' });
          } catch {
            setMessage({ type: 'success', text: 'API Key 已创建！请复制保存，此密钥只显示一次。' });
          }
        } else {
          setMessage({ type: 'error', text: '创建成功但未返回密钥，请联系管理员' });
        }
        setNewKeyName('');
        loadApiKeys();
      } else {
        // 尝试解析错误响应
        let errorMessage = '创建失败';
        try {
          const error = await res.json();
          errorMessage = error.detail || errorMessage;
        } catch {
          errorMessage = `创建失败 (HTTP ${res.status})`;
        }
        setMessage({ type: 'error', text: errorMessage });
      }
    } catch (error: any) {
      console.error('创建 API Key 失败:', error);
      setMessage({ type: 'error', text: error.message || '网络错误，请检查连接' });
    }
  };

  const handleDeleteApiKey = async (keyId: number, keyName: string) => {
    if (!confirm(`确定要删除 API Key "${keyName}" 吗？删除后使用此 Key 的外部系统将无法访问您的数据。`)) {
      return;
    }
    if (!token) return;
    try {
      const res = await fetch(`${API_BASE}/user-api-keys/${keyId}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        setMessage({ type: 'success', text: 'API Key 已删除' });
        loadApiKeys();
      } else {
        setMessage({ type: 'error', text: '删除失败' });
      }
    } catch (error) {
      setMessage({ type: 'error', text: '删除失败' });
    }
  };

  // 展开 API Key 部分时加载数据
  useEffect(() => {
    if (showApiKeySection && token) {
      loadApiKeys();
    }
  }, [showApiKeySection, token]);

  // 未登录跳转
  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login');
    }
  }, [authLoading, isAuthenticated, router]);

  // 处理 URL hash 滚动到 Garmin 设置
  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (window.location.hash === '#garmin') {
      // 等待页面渲染完成后滚动
      const timer = setTimeout(() => {
        garminSectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        // 高亮显示 Garmin 区块
        setHighlightGarmin(true);
        // 3秒后取消高亮
        setTimeout(() => setHighlightGarmin(false), 3000);
      }, 500);
      return () => clearTimeout(timer);
    }
    if (window.location.hash === '#assistant-openclaw') {
      const timer = setTimeout(() => {
        assistantOpenclawSectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        setHighlightAssistantOpenClaw(true);
        setTimeout(() => setHighlightAssistantOpenClaw(false), 3000);
      }, 500);
      return () => clearTimeout(timer);
    }
  }, []);

  if (authLoading || !isAuthenticated) {
    return (
      <main className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 pt-4 pb-8 px-4">
        <div className="max-w-4xl mx-auto text-center py-20">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">加载中...</p>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 pt-4 pb-8 px-4">
      <div className="max-w-4xl mx-auto">
        {/* 消息提示 */}
        {message && (
          <div className={`mb-6 p-4 rounded-lg ${
            message.type === 'success'
              ? 'bg-green-50 border border-green-200 text-green-800'
              : 'bg-red-50 border border-red-200 text-red-800'
          }`}>
            {/* 如果消息已经以图标开头，不再添加额外图标 */}
            {!/^[✅❌⚠️🔐⏳]/.test(message.text) && (message.type === 'success' ? '✅ ' : '❌ ')}
            {message.text}
            <button
              onClick={() => setMessage(null)}
              className="float-right text-gray-500 hover:text-gray-700"
            >
              ✕
            </button>
          </div>
        )}

        {/* 用户信息卡片 */}
        <div className="bg-white rounded-xl shadow-lg p-6 mb-6 border border-gray-100">
          <h2 className="text-xl font-bold text-gray-900 mb-4 flex items-center gap-2">
            👤 账户信息
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="text-sm text-gray-500">用户名</label>
              <p className="text-gray-900 font-medium">{user?.username || '-'}</p>
            </div>
            <div>
              <label className="text-sm text-gray-500">邮箱</label>
              {user?.email ? (
                <p className="text-gray-900 font-medium">{user.email}</p>
              ) : (
                <div className="flex items-center gap-2">
                  <p className="text-gray-400">未绑定</p>
                  <button
                    onClick={() => setShowBindForm(!showBindForm)}
                    className="text-indigo-500 hover:text-indigo-600 text-sm"
                  >
                    绑定邮箱
                  </button>
                </div>
              )}
            </div>
            <div>
              <label className="text-sm text-gray-500">姓名</label>
              {isEditingName ? (
                <div className="flex items-center gap-2 mt-1">
                  <input
                    type="text"
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    className="flex-1 p-2 border border-gray-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                    placeholder="请输入姓名"
                    autoFocus
                  />
                  <button
                    onClick={() => {
                      if (editName.trim()) {
                        updateNameMutation.mutate(editName.trim());
                      }
                    }}
                    disabled={!editName.trim() || updateNameMutation.isPending}
                    className="px-3 py-2 bg-indigo-500 text-white rounded-lg hover:bg-indigo-600 disabled:opacity-50 text-sm"
                  >
                    {updateNameMutation.isPending ? '保存中...' : '保存'}
                  </button>
                  <button
                    onClick={() => {
                      setIsEditingName(false);
                      setEditName('');
                    }}
                    className="px-3 py-2 bg-gray-100 text-gray-600 rounded-lg hover:bg-gray-200 text-sm"
                  >
                    取消
                  </button>
                </div>
              ) : (
                <div className="flex items-center gap-2">
                  <p className="text-gray-900 font-medium">{user?.name || '-'}</p>
                  <button
                    onClick={() => {
                      setEditName(user?.name || '');
                      setIsEditingName(true);
                    }}
                    className="text-indigo-500 hover:text-indigo-600 text-sm"
                  >
                    ✏️ 编辑
                  </button>
                </div>
              )}
            </div>
            <div>
              <label className="text-sm text-gray-500">账户状态</label>
              <p className="text-green-600 font-medium">
                {user?.is_active ? '✓ 已激活' : '✗ 未激活'}
              </p>
            </div>
          </div>
          {/* 绑定Web登录表单 */}
          {showBindForm && !user?.email && (
            <div className="mt-4 pt-4 border-t">
              <h3 className="text-sm font-semibold text-gray-700 mb-3">绑定邮箱和密码（用于Web端登录）</h3>
              <div className="space-y-3">
                <div>
                  <label className="text-xs text-gray-500 mb-1 block">邮箱地址</label>
                  <input
                    type="email"
                    value={bindEmail}
                    onChange={(e) => setBindEmail(e.target.value)}
                    placeholder="请输入邮箱"
                    className="w-full p-2 border border-gray-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-sm"
                  />
                </div>
                <div>
                  <label className="text-xs text-gray-500 mb-1 block">设置密码（至少6位）</label>
                  <input
                    type="password"
                    value={bindPassword}
                    onChange={(e) => setBindPassword(e.target.value)}
                    placeholder="请设置登录密码"
                    className="w-full p-2 border border-gray-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-sm"
                  />
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={async () => {
                      if (!bindEmail.trim() || !bindPassword.trim()) {
                        setMessage({ type: 'error', text: '请填写邮箱和密码' });
                        return;
                      }
                      if (bindPassword.length < 6) {
                        setMessage({ type: 'error', text: '密码至少6位' });
                        return;
                      }
                      setBindLoading(true);
                      try {
                        const res = await fetch(`${API_BASE}/auth/bind-web-login`, {
                          method: 'POST',
                          headers: {
                            'Content-Type': 'application/json',
                            'Authorization': `Bearer ${token}`,
                          },
                          body: JSON.stringify({ email: bindEmail, password: bindPassword }),
                        });
                        const data = await res.json();
                        if (res.ok) {
                          setMessage({ type: 'success', text: '绑定成功！现在可以使用邮箱和密码在Web端登录' });
                          setShowBindForm(false);
                          setBindEmail('');
                          setBindPassword('');
                          refreshUser();
                        } else {
                          setMessage({ type: 'error', text: data.detail || '绑定失败' });
                        }
                      } catch {
                        setMessage({ type: 'error', text: '网络错误，请重试' });
                      } finally {
                        setBindLoading(false);
                      }
                    }}
                    disabled={bindLoading}
                    className="px-4 py-2 bg-indigo-500 text-white rounded-lg hover:bg-indigo-600 disabled:opacity-50 text-sm"
                  >
                    {bindLoading ? '绑定中...' : '确认绑定'}
                  </button>
                  <button
                    onClick={() => {
                      setShowBindForm(false);
                      setBindEmail('');
                      setBindPassword('');
                    }}
                    className="px-4 py-2 bg-gray-100 text-gray-600 rounded-lg hover:bg-gray-200 text-sm"
                  >
                    取消
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* 修改密码 */}
          {user?.email && (
            <div className="mt-4 pt-4 border-t">
              <button
                onClick={() => setShowChangePassword(!showChangePassword)}
                className="text-sm text-indigo-600 hover:text-indigo-800"
              >
                {showChangePassword ? '取消修改密码' : '修改密码'}
              </button>
              {showChangePassword && (
                <div className="mt-3 space-y-3">
                  <div>
                    <label className="text-xs text-gray-500 mb-1 block">当前密码</label>
                    <input
                      type="password"
                      value={oldPassword}
                      onChange={(e) => setOldPassword(e.target.value)}
                      placeholder="请输入当前密码"
                      className="w-full p-2 border border-gray-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-sm"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-gray-500 mb-1 block">新密码（至少6位）</label>
                    <input
                      type="password"
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      placeholder="请输入新密码"
                      className="w-full p-2 border border-gray-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-sm"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-gray-500 mb-1 block">确认新密码</label>
                    <input
                      type="password"
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      placeholder="请再次输入新密码"
                      className="w-full p-2 border border-gray-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-sm"
                    />
                  </div>
                  <button
                    onClick={async () => {
                      if (!oldPassword.trim()) {
                        setMessage({ type: 'error', text: '请输入当前密码' });
                        return;
                      }
                      if (newPassword.length < 6) {
                        setMessage({ type: 'error', text: '新密码至少6位' });
                        return;
                      }
                      if (newPassword !== confirmPassword) {
                        setMessage({ type: 'error', text: '两次输入的新密码不一致' });
                        return;
                      }
                      setChangePwdLoading(true);
                      try {
                        const res = await fetch(`${API_BASE}/auth/change-password`, {
                          method: 'POST',
                          headers: {
                            'Content-Type': 'application/json',
                            'Authorization': `Bearer ${token}`,
                          },
                          body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
                        });
                        const data = await res.json();
                        if (res.ok) {
                          setMessage({ type: 'success', text: '密码修改成功' });
                          setShowChangePassword(false);
                          setOldPassword('');
                          setNewPassword('');
                          setConfirmPassword('');
                        } else {
                          setMessage({ type: 'error', text: data.detail || '修改失败' });
                        }
                      } catch {
                        setMessage({ type: 'error', text: '网络错误，请重试' });
                      } finally {
                        setChangePwdLoading(false);
                      }
                    }}
                    disabled={changePwdLoading}
                    className="px-4 py-2 bg-indigo-500 text-white rounded-lg hover:bg-indigo-600 disabled:opacity-50 text-sm"
                  >
                    {changePwdLoading ? '修改中...' : '确认修改'}
                  </button>
                </div>
              )}
            </div>
          )}

          <div className="mt-4 pt-4 border-t">
            <button
              onClick={logout}
              className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors"
            >
              退出登录
            </button>
          </div>
        </div>

        <div
          ref={assistantOpenclawSectionRef}
          id="assistant-openclaw"
          className={`bg-white rounded-xl shadow-lg p-6 mb-6 border transition-all duration-500 ${
            highlightAssistantOpenClaw
              ? 'border-cyan-400 ring-4 ring-cyan-100 shadow-xl'
              : 'border-gray-100'
          }`}
        >
          <h2 className="text-xl font-bold text-gray-900 mb-4 flex items-center gap-2">
            🦀 智能助理专用 OpenClaw
            {highlightAssistantOpenClaw && (
              <span className="px-2 py-0.5 bg-cyan-100 text-cyan-700 text-xs rounded-full animate-pulse">
                请在此配置
              </span>
            )}
          </h2>

          <p className="text-gray-600 text-sm mb-4">
            该绑定仅作用于「智能助理」中的「我的 OpenClaw」模式，不会影响系统现有的 OpenClaw 功能。
          </p>

          <div className="rounded-lg border border-cyan-100 bg-cyan-50 p-4 text-sm text-cyan-900 mb-4 space-y-1">
            <div>允许地址：`127.0.0.1`、`localhost` 或系统白名单中的可信域名。</div>
            <div>推荐你当前使用：`http://127.0.0.1:28789`</div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">显示名称</label>
              <input
                type="text"
                value={assistantOpenclawForm.display_name}
                onChange={(e) => setAssistantOpenclawForm(prev => ({ ...prev, display_name: e.target.value }))}
                className="w-full p-3 border border-gray-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-cyan-500 focus:border-cyan-500"
                placeholder="我的 OpenClaw"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">网关地址</label>
              <input
                type="text"
                value={assistantOpenclawForm.gateway_url}
                onChange={(e) => setAssistantOpenclawForm(prev => ({ ...prev, gateway_url: e.target.value }))}
                className="w-full p-3 border border-gray-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-cyan-500 focus:border-cyan-500"
                placeholder="http://127.0.0.1:28789"
              />
            </div>
            <div className="md:col-span-2">
              <label className="block text-sm font-medium text-gray-700 mb-2">OpenClaw Token</label>
              <input
                type="password"
                value={assistantOpenclawForm.gateway_token}
                onChange={(e) => setAssistantOpenclawForm(prev => ({ ...prev, gateway_token: e.target.value }))}
                className="w-full p-3 border border-gray-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-cyan-500 focus:border-cyan-500"
                placeholder={assistantBinding?.configured ? '留空表示保留当前 Token' : '请输入你的 OpenClaw Token'}
              />
              {assistantBinding?.configured && assistantBinding.gateway_token_last4 && (
                <p className="mt-2 text-xs text-gray-500">当前已保存 Token 后四位：{assistantBinding.gateway_token_last4}</p>
              )}
            </div>
          </div>

          <div className="flex items-center justify-between gap-4 flex-wrap mb-5">
            <label className="inline-flex items-center gap-3 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={assistantOpenclawForm.enabled}
                onChange={(e) => setAssistantOpenclawForm(prev => ({ ...prev, enabled: e.target.checked }))}
                className="w-4 h-4 rounded border-gray-300 text-cyan-600 focus:ring-cyan-500"
              />
              启用「我的 OpenClaw」模式
            </label>
            <div className="text-sm text-gray-600">
              当前状态：
              <span className={`ml-2 inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${
                assistantBinding?.status === 'active'
                  ? 'bg-green-100 text-green-700'
                  : assistantBinding?.status === 'invalid'
                    ? 'bg-red-100 text-red-700'
                    : assistantBinding?.status === 'disabled'
                      ? 'bg-gray-100 text-gray-700'
                      : 'bg-amber-100 text-amber-700'
              }`}>
                {assistantBindingLoading
                  ? '加载中'
                  : assistantBinding?.status === 'active'
                    ? '可用'
                    : assistantBinding?.status === 'invalid'
                      ? '连接异常'
                      : assistantBinding?.status === 'disabled'
                        ? '已停用'
                        : '未配置'}
              </span>
            </div>
          </div>

          {(assistantBinding?.last_error || assistantBinding?.last_tested_at) && (
            <div className="mb-4 rounded-lg bg-gray-50 border border-gray-200 p-4 text-sm text-gray-700 space-y-1">
              {assistantBinding.last_tested_at && (
                <div>最近测试时间：{formatDateTime(assistantBinding.last_tested_at)}</div>
              )}
              {assistantBinding.last_error && (
                <div className="text-red-600">最近错误：{assistantBinding.last_error}</div>
              )}
            </div>
          )}

          <div className="flex flex-wrap gap-3">
            <button
              onClick={() => testAssistantOpenclawMutation.mutate()}
              disabled={!assistantOpenclawForm.gateway_url.trim() || testAssistantOpenclawMutation.isPending}
              className="px-4 py-2 bg-cyan-500 text-white rounded-lg hover:bg-cyan-600 disabled:opacity-50"
            >
              {testAssistantOpenclawMutation.isPending ? '测试中...' : '测试连接'}
            </button>
            <button
              onClick={() => saveAssistantOpenclawMutation.mutate()}
              disabled={!assistantOpenclawForm.gateway_url.trim() || saveAssistantOpenclawMutation.isPending}
              className="px-4 py-2 bg-indigo-500 text-white rounded-lg hover:bg-indigo-600 disabled:opacity-50"
            >
              {saveAssistantOpenclawMutation.isPending ? '保存中...' : '保存绑定'}
            </button>
            {assistantBinding?.configured && (
              <button
                onClick={() => {
                  if (confirm('确定要解绑这个智能助理专用 OpenClaw 吗？')) {
                    deleteAssistantOpenclawMutation.mutate();
                  }
                }}
                disabled={deleteAssistantOpenclawMutation.isPending}
                className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 disabled:opacity-50"
              >
                {deleteAssistantOpenclawMutation.isPending ? '解绑中...' : '解绑'}
              </button>
            )}
          </div>
        </div>

        {/* Garmin设置卡片 */}
        <div
          ref={garminSectionRef}
          id="garmin"
          className={`bg-white rounded-xl shadow-lg p-6 mb-6 border transition-all duration-500 ${
            highlightGarmin
              ? 'border-indigo-400 ring-4 ring-indigo-100 shadow-xl'
              : 'border-gray-100'
          }`}
        >
          <h2 className="text-xl font-bold text-gray-900 mb-4 flex items-center gap-2">
            ⌚ Garmin Connect 设置
            {highlightGarmin && (
              <span className="px-2 py-0.5 bg-indigo-100 text-indigo-600 text-xs rounded-full animate-pulse">
                请在此配置
              </span>
            )}
          </h2>

          <p className="text-gray-600 text-sm mb-4">
            配置您的Garmin Connect账号，系统将自动同步您的健康数据（心率、睡眠、运动等）。
            <br />
            <span className="text-orange-600">⚠️ 您的Garmin密码将被加密存储，仅用于同步数据。</span>
          </p>

          {/* 已配置状态 */}
          {garminCredential && !showGarminForm && (
            <div className={`rounded-lg p-4 border mb-4 ${
              garminCredential.sync_enabled 
                ? 'bg-green-50 border-green-200' 
                : 'bg-gray-50 border-gray-200'
            }`}>
              <div className="flex items-center justify-between">
                <div>
                  <p className={`font-medium ${garminCredential.sync_enabled ? 'text-green-800' : 'text-gray-600'}`}>
                    {garminCredential.sync_enabled ? '✅ 已配置Garmin账号' : '⏸️ 同步已暂停'}
                    {garminCredential.is_cn && (
                      <span className="ml-2 px-2 py-0.5 bg-orange-100 text-orange-700 text-xs rounded-full">
                        🇨🇳 中国版
                      </span>
                    )}
                  </p>
                  <p className={`text-sm mt-1 ${garminCredential.sync_enabled ? 'text-green-700' : 'text-gray-500'}`}>
                    账号: {garminCredential.garmin_email}
                    <span className="text-xs text-gray-400 ml-2">
                      ({garminCredential.is_cn ? 'garmin.cn' : 'garmin.com'})
                    </span>
                  </p>
                  {garminCredential.last_sync_at && (
                    <p className={`text-xs mt-1 ${garminCredential.sync_enabled ? 'text-green-600' : 'text-gray-400'}`}>
                      最后同步: {formatDateTime(garminCredential.last_sync_at)}
                    </p>
                  )}
                </div>
                <div className="flex gap-2 items-center">
                  {/* 同步开关 */}
                  <button
                    onClick={() => toggleSyncMutation.mutate(!garminCredential.sync_enabled)}
                    disabled={toggleSyncMutation.isPending}
                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                      garminCredential.sync_enabled ? 'bg-green-500' : 'bg-gray-300'
                    } ${toggleSyncMutation.isPending ? 'opacity-50' : ''}`}
                    title={garminCredential.sync_enabled ? '点击暂停同步' : '点击启用同步'}
                  >
                    <span
                      className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                        garminCredential.sync_enabled ? 'translate-x-6' : 'translate-x-1'
                      }`}
                    />
                  </button>
                  <span className={`text-xs ${garminCredential.sync_enabled ? 'text-green-600' : 'text-gray-400'}`}>
                    {garminCredential.sync_enabled ? '同步中' : '已暂停'}
                  </span>
                  <button
                    onClick={() => setShowGarminForm(true)}
                    className="px-3 py-1 bg-green-600 text-white rounded-lg hover:bg-green-700 text-sm"
                  >
                    修改
                  </button>
                  <button
                    onClick={() => {
                      if (confirm('确定要删除Garmin凭证吗？')) {
                        deleteGarminMutation.mutate();
                      }
                    }}
                    disabled={deleteGarminMutation.isPending}
                    className="px-3 py-1 bg-red-500 text-white rounded-lg hover:bg-red-600 text-sm disabled:opacity-50"
                  >
                    删除
                  </button>
                </div>
              </div>

              {/* 同步控制 */}
              <div className="mt-4 pt-4 border-t border-green-200">
                <div className="flex items-center gap-4 flex-wrap">
                  <label className="text-green-800 text-sm">同步天数:</label>
                  <select
                    value={syncDays}
                    onChange={(e) => setSyncDays(Number(e.target.value))}
                    disabled={syncProgress.isSyncing}
                    className="p-2 border border-green-300 rounded-lg text-gray-900 disabled:opacity-50"
                  >
                    <option value={1}>最近1天</option>
                    <option value={3}>最近3天</option>
                    <option value={7}>最近7天</option>
                    <option value={30}>最近30天</option>
                    <option value={90}>最近90天</option>
                    <option value={180}>最近180天</option>
                    <option value={365}>最近1年</option>
                    <option value={730}>最近2年</option>
                  </select>
                  <button
                    onClick={() => startSyncWithProgress(syncDays)}
                    disabled={syncProgress.isSyncing}
                    className="px-4 py-2 bg-gradient-to-r from-indigo-500 to-purple-600 text-white rounded-lg hover:from-indigo-600 hover:to-purple-700 disabled:opacity-50 flex items-center gap-2"
                  >
                    {syncProgress.isSyncing ? (
                      <>
                        <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                        </svg>
                        <span>同步中...</span>
                      </>
                    ) : (
                      <>🔄 立即同步</>
                    )}
                  </button>
                </div>
                
                {/* 同步进度条 */}
                {syncProgress.isSyncing && (
                  <div className="mt-4 space-y-2">
                    <div className="flex justify-between text-sm text-green-700">
                      <span>{syncProgress.message}</span>
                      <span>{syncProgress.current} / {syncProgress.total}</span>
                    </div>
                    <div className="w-full bg-green-200 rounded-full h-3 overflow-hidden">
                      <div
                        className="bg-gradient-to-r from-indigo-500 to-purple-600 h-3 rounded-full transition-all duration-300 ease-out"
                        style={{ width: `${syncProgress.total > 0 ? (syncProgress.current / syncProgress.total) * 100 : 0}%` }}
                      />
                    </div>
                    <div className="flex gap-4 text-xs text-gray-600">
                      <span className="text-green-600">✓ 成功: {syncProgress.synced}</span>
                      {syncProgress.failed > 0 && (
                        <span className="text-red-500">✗ 失败: {syncProgress.failed}</span>
                      )}
                      {syncProgress.currentDate && (
                        <span className="text-gray-500">当前: {syncProgress.currentDate}</span>
                      )}
                    </div>
                  </div>
                )}

                {/* MFA 两步验证区域（同步时显示） */}
                {showMFA && mfaSessionId && !showGarminForm && (
                  <div className="mt-4 p-4 bg-indigo-50 border border-indigo-200 rounded-lg">
                    <div className="flex items-center gap-2 mb-3">
                      <span className="text-2xl">🔐</span>
                      <h4 className="font-semibold text-indigo-900">两步验证</h4>
                    </div>
                    <div className="text-sm text-indigo-700 mb-3 space-y-2">
                      <p className="font-medium">如何获取验证码：</p>
                      <div className="space-y-2">
                        <div>
                          <p className="font-semibold text-indigo-800">方式1：验证器应用（推荐）</p>
                          <ol className="list-decimal list-inside space-y-1 ml-2 text-xs">
                            <li>打开手机上的验证器应用（如Google Authenticator、Microsoft Authenticator等）</li>
                            <li>找到您的Garmin账号</li>
                            <li>查看显示的6位数字验证码（每30秒自动更新）</li>
                          </ol>
                        </div>
                        <div>
                          <p className="font-semibold text-indigo-800">方式2：邮件验证码</p>
                          <p className="text-xs ml-2">如果您的账号配置为通过邮件接收验证码，请检查您的邮箱（包括垃圾邮件文件夹）</p>
                        </div>
                        <div>
                          <p className="font-semibold text-indigo-800">方式3：短信验证码</p>
                          <p className="text-xs ml-2">如果您的账号配置为通过短信接收验证码，请检查您的手机短信</p>
                        </div>
                      </div>
                      <div className="mt-3 p-2 bg-blue-50 border border-blue-200 rounded text-xs text-blue-800">
                        <strong>💡 提示：</strong>
                        <ul className="list-disc list-inside mt-1 space-y-0.5">
                          <li>验证码格式通常是6位数字</li>
                          <li>如果验证失败，请检查验证码是否正确且未过期</li>
                          <li>验证码可能有时间限制，请尽快输入</li>
                        </ul>
                      </div>
                    </div>
                    <div className="flex gap-3 items-center">
                      <input
                        type="text"
                        maxLength={6}
                        value={mfaCode}
                        onChange={(e) => setMfaCode(e.target.value.replace(/\D/g, ''))}
                        className="w-40 p-3 border-2 border-indigo-300 rounded-lg text-gray-900 text-center text-xl font-bold tracking-widest focus:border-indigo-500 focus:outline-none"
                        placeholder="000000"
                      />
                      <button
                        onClick={() => verifyMFAMutation.mutate()}
                        disabled={mfaCode.length !== 6 || verifyMFAMutation.isPending}
                        className="px-4 py-2 bg-gradient-to-r from-green-500 to-emerald-600 text-white rounded-lg hover:from-green-600 hover:to-emerald-700 disabled:opacity-50"
                      >
                        {verifyMFAMutation.isPending ? '验证中...' : '✓ 验证'}
                      </button>
                      <button
                        onClick={() => {
                          setShowMFA(false);
                          setMfaCode('');
                          setMfaSessionId(null);
                        }}
                        className="px-4 py-2 bg-gray-200 text-gray-600 rounded-lg hover:bg-gray-300"
                      >
                        取消
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* 未配置或修改表单 */}
          {(!garminCredential || showGarminForm) && (
            <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
              <h3 className="font-semibold text-gray-800 mb-3">
                {garminCredential ? '修改Garmin凭证' : '配置Garmin凭证'}
              </h3>
              <div className="space-y-3">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Garmin账号邮箱
                  </label>
                  <input
                    type="email"
                    value={garminForm.garmin_email}
                    onChange={(e) => setGarminForm({ ...garminForm, garmin_email: e.target.value })}
                    className="w-full p-3 border border-gray-300 rounded-lg text-gray-900"
                    placeholder="请输入Garmin Connect邮箱"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Garmin账号密码
                  </label>
                  <div className="relative">
                    <input
                      type={showGarminPassword ? "text" : "password"}
                      value={garminForm.garmin_password}
                      onChange={(e) => setGarminForm({ ...garminForm, garmin_password: e.target.value })}
                      className="w-full p-3 pr-12 border border-gray-300 rounded-lg text-gray-900"
                      placeholder="请输入Garmin Connect密码"
                    />
                    <button
                      type="button"
                      onClick={() => setShowGarminPassword(!showGarminPassword)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-700 focus:outline-none"
                      title={showGarminPassword ? "隐藏密码" : "显示密码"}
                    >
                      {showGarminPassword ? (
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M3.98 8.223A10.477 10.477 0 001.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0112 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 01-4.293 5.774M6.228 6.228L3 3m3.228 3.228l3.65 3.65m7.894 7.894L21 21m-3.228-3.228l-3.65-3.65m0 0a3 3 0 10-4.243-4.243m4.242 4.242L9.88 9.88" />
                        </svg>
                      ) : (
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
                          <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                        </svg>
                      )}
                    </button>
                  </div>
                </div>
                <div className="flex items-center gap-3 p-3 bg-orange-50 border border-orange-200 rounded-lg">
                  <input
                    type="checkbox"
                    id="is_cn"
                    checked={garminForm.is_cn}
                    onChange={(e) => setGarminForm({ ...garminForm, is_cn: e.target.checked })}
                    className="w-5 h-5 text-orange-600 border-gray-300 rounded focus:ring-orange-500"
                  />
                  <label htmlFor="is_cn" className="text-gray-700">
                    <span className="font-medium">🇨🇳 中国用户</span>
                    <span className="text-sm text-gray-500 ml-2">
                      (使用 garmin.cn 账号)
                    </span>
                  </label>
                </div>
                
                {/* MFA 两步验证区域 */}
                {showMFA && (
                  <div className="p-4 bg-indigo-50 border border-indigo-200 rounded-lg">
                    <div className="flex items-center gap-2 mb-3">
                      <span className="text-2xl">🔐</span>
                      <h4 className="font-semibold text-indigo-900">两步验证</h4>
                    </div>
                    <p className="text-sm text-indigo-700 mb-3">
                      您的Garmin账号已开启两步验证，请打开验证器应用输入6位验证码。
                    </p>
                    <div className="flex gap-3 items-center">
                      <input
                        type="text"
                        maxLength={6}
                        value={mfaCode}
                        onChange={(e) => setMfaCode(e.target.value.replace(/\D/g, ''))}
                        className="w-40 p-3 border-2 border-indigo-300 rounded-lg text-gray-900 text-center text-xl font-bold tracking-widest focus:border-indigo-500 focus:outline-none"
                        placeholder="000000"
                      />
                      <button
                        onClick={() => verifyMFAMutation.mutate()}
                        disabled={mfaCode.length !== 6 || verifyMFAMutation.isPending}
                        className="px-4 py-2 bg-gradient-to-r from-green-500 to-emerald-600 text-white rounded-lg hover:from-green-600 hover:to-emerald-700 disabled:opacity-50"
                      >
                        {verifyMFAMutation.isPending ? '验证中...' : '✓ 验证'}
                      </button>
                      <button
                        onClick={() => {
                          setShowMFA(false);
                          setMfaCode('');
                          setMfaSessionId(null);
                          setMfaContext(null);
                          setPendingSyncDays(null);
                        }}
                        className="px-4 py-2 bg-gray-200 text-gray-600 rounded-lg hover:bg-gray-300"
                      >
                        取消
                      </button>
                    </div>
                  </div>
                )}
                
                <div className="flex gap-3">
                  <button
                    onClick={() => testConnectionMutation.mutate(garminForm)}
                    disabled={!garminForm.garmin_email || !garminForm.garmin_password || testConnectionMutation.isPending || showMFA}
                    className="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 disabled:opacity-50"
                  >
                    {testConnectionMutation.isPending ? '测试中...' : '🔍 测试连接'}
                  </button>
                  <button
                    onClick={() => saveGarminMutation.mutate(garminForm)}
                    disabled={!garminForm.garmin_email || !garminForm.garmin_password || saveGarminMutation.isPending || showMFA}
                    className="px-4 py-2 bg-gradient-to-r from-indigo-500 to-purple-600 text-white rounded-lg hover:from-indigo-600 hover:to-purple-700 disabled:opacity-50"
                  >
                    {saveGarminMutation.isPending ? '保存中...' : '💾 保存凭证'}
                  </button>
                  {showGarminForm && (
                    <button
                      onClick={() => {
                        setShowGarminForm(false);
                        setShowMFA(false);
                        setMfaCode('');
                        setMfaSessionId(null);
                        setMfaContext(null);
                        setPendingSyncDays(null);
                        setGarminForm({ garmin_email: '', garmin_password: '', is_cn: false });
                      }}
                      className="px-4 py-2 bg-gray-100 text-gray-600 rounded-lg hover:bg-gray-200"
                    >
                      取消
                    </button>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* 快捷记录饮食说明 */}
        <div className="bg-white rounded-xl shadow-lg p-6 mb-6 border border-gray-100">
          <div
            className="flex items-center justify-between cursor-pointer"
            onClick={() => setShowQuickRecordSection(!showQuickRecordSection)}
          >
            <h2 className="text-xl font-bold text-gray-900 flex items-center gap-2">
              📱 快捷记录饮食
            </h2>
            <span className="text-gray-400 text-2xl">
              {showQuickRecordSection ? '▼' : '›'}
            </span>
          </div>

          {showQuickRecordSection && (
            <div className="mt-4 space-y-4 text-gray-700">
              <p className="text-gray-600 text-sm">
                通过 iPhone 快捷指令，一键语音记录饮食、运动、打卡等健康数据。说出刚做过的事即可自动识别并保存。
              </p>

              {/* 第一步：复制 Token */}
              <div className="bg-green-50 rounded-lg p-4 border border-green-200">
                <h3 className="font-semibold text-green-900 mb-2">第一步：复制你的专属 Token</h3>
                <p className="text-sm text-green-800 mb-3">
                  安装快捷指令后需要填入此 Token 作为身份凭证，点击下方一键复制。
                </p>
                {token ? (
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(token);
                      alert('✅ Token 已复制！\n\n安装快捷指令后，编辑第一步的「文本」块，将 YOUR_TOKEN_HERE 替换为此 Token。');
                    }}
                    className="w-full flex items-center justify-between gap-2 bg-white border-2 border-green-300 hover:bg-green-100 active:scale-[0.99] transition-all rounded-lg px-4 py-3 text-left cursor-pointer"
                  >
                    <span className="text-xs font-mono text-green-900 break-all flex-1">
                      {token.slice(0, 28)}...{token.slice(-8)}
                    </span>
                    <span className="text-green-700 font-semibold text-sm whitespace-nowrap">📋 点击复制</span>
                  </button>
                ) : (
                  <p className="text-sm text-green-800">请先登录后查看专属 Token。</p>
                )}
              </div>

              {/* 第二步：安装快捷指令模板 */}
              <div className="bg-blue-50 rounded-lg p-4 border border-blue-200">
                <h3 className="font-semibold text-blue-900 mb-2">第二步：安装快捷指令模板</h3>
                <p className="text-sm text-blue-800 mb-3">
                  用 iPhone / iPad 的 <strong>Safari</strong> 打开下方链接，点「添加快捷指令」完成安装。
                </p>
                <a
                  href="https://www.icloud.com/shortcuts/ad3061e9a2094555acb8b42b93f57c6c"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
                >
                  📥 获取「健康记录」快捷指令
                </a>
              </div>

              {/* 第三步：填入 Token */}
              <div className="bg-orange-50 rounded-lg p-4 border border-orange-200">
                <h3 className="font-semibold text-orange-900 mb-2">第三步：填入你的 Token</h3>
                <ol className="text-sm text-orange-800 space-y-1 list-decimal list-inside">
                  <li>打开「快捷指令」App，找到「健康记录」</li>
                  <li>点右上角 <strong>···</strong> 进入编辑</li>
                  <li>找到顶部的<strong>「文本」块</strong>（内容为 <code className="bg-orange-100 px-1 rounded text-xs">YOUR_TOKEN_HERE</code>）</li>
                  <li>替换为第一步复制的 Token，保存</li>
                </ol>
                <p className="text-xs text-orange-600 mt-2">只需设置一次，之后每次运行无需重新输入。</p>
              </div>

              {/* 第四步：设置触发方式 */}
              <div className="space-y-3">
                <h3 className="font-semibold text-gray-800">第四步：设置触发方式</h3>

                <div className="space-y-2">
                  <h4 className="font-medium text-gray-700 text-sm">方式一：辅助触控浮钮（推荐）</h4>
                  <ol className="list-decimal list-inside text-sm space-y-1 text-gray-600">
                    <li><strong>设置</strong> → <strong>辅助功能</strong> → <strong>触控</strong> → <strong>辅助触控</strong>，开启</li>
                    <li>在「自定顶层菜单」或「轻点两下」中，选择运行「健康记录」快捷指令</li>
                    <li>使用时点击浮钮，按提示说出内容即可</li>
                  </ol>
                </div>

                <div className="space-y-2">
                  <h4 className="font-medium text-gray-700 text-sm">方式二：轻点背面</h4>
                  <ol className="list-decimal list-inside text-sm space-y-1 text-gray-600">
                    <li><strong>设置</strong> → <strong>辅助功能</strong> → <strong>触控</strong> → <strong>轻点背面</strong></li>
                    <li>选择「轻点两下」→ 选择「健康记录」快捷指令</li>
                  </ol>
                </div>

                <div className="space-y-2">
                  <h4 className="font-medium text-gray-700 text-sm">其他方式</h4>
                  <ul className="list-disc list-inside text-sm text-gray-600 space-y-1">
                    <li><strong>控制中心</strong>：下滑即可触发</li>
                    <li><strong>主屏幕小组件</strong>：桌面一键运行</li>
                    <li><strong>Pro 操作按钮</strong>：iPhone 15 Pro+ 侧边按钮直接触发</li>
                  </ul>
                </div>
              </div>

              {/* 安卓/华为用户专属 */}
              <div className="bg-purple-50 rounded-lg p-4 border border-purple-200">
                <h3 className="font-semibold text-purple-900 mb-2">安卓 / 华为用户</h3>
                <p className="text-sm text-purple-800 mb-3">
                  安卓手机无法使用 iPhone 快捷指令，可用下方「语音快捷记录」页面，添加到桌面后一点即用，体验一致。
                </p>
                {token ? (
                  <button
                    onClick={() => {
                      const url = `https://health.executor.life/quick-record?token=${token}`;
                      navigator.clipboard.writeText(url);
                      alert('✅ 链接已复制！\n\n① 用手机浏览器打开此链接\n② 浏览器菜单 →「添加到桌面」\n③ 桌面出现图标，一点即可语音记录');
                    }}
                    className="inline-flex items-center gap-2 bg-purple-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-purple-700 transition-colors"
                  >
                    📋 复制语音快捷记录链接
                  </button>
                ) : (
                  <p className="text-sm text-purple-800">请先登录后获取专属链接。</p>
                )}
              </div>

              {/* 支持的语音指令 */}
              <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
                <h3 className="font-semibold text-gray-800 mb-2">支持的语音指令</h3>
                <p className="text-sm text-gray-600 mb-2">
                  不止饮食，还支持运动、打卡、鼻炎等各类健康记录：
                </p>
                <ul className="text-sm text-gray-600 space-y-1">
                  <li>「吃了两个鸡蛋、一碗米饭、炒青菜」→ 自动记录饮食和营养</li>
                  <li>「刚跑步40分钟」→ 记录运动</li>
                  <li>「做了50个俯卧撑」→ 打卡记录</li>
                  <li>「洗了鼻子」→ 记录鼻炎护理</li>
                  <li>「吃了维生素D」→ 记录补剂</li>
                  <li>「喝了一杯水」→ 记录饮水</li>
                </ul>
              </div>
            </div>
          )}
        </div>

        {/* 隐私设置卡片 */}
        <div className="bg-white rounded-xl shadow-lg p-6 mb-6 border border-gray-100">
          <div
            className="flex items-center justify-between cursor-pointer"
            onClick={() => setShowPrivacySection(!showPrivacySection)}
          >
            <h2 className="text-xl font-bold text-gray-900 flex items-center gap-2">
              🔒 数据隐私设置
            </h2>
            <span className="text-gray-400 text-2xl">
              {showPrivacySection ? '▼' : '›'}
            </span>
          </div>

          {showPrivacySection && (
            <div className="mt-4 space-y-4">
              <p className="text-gray-600 text-sm">
                控制哪些个人信息可以通过 API 对外公开（用于外部 AI 健康助手）
              </p>

              {profileLoading ? (
                <div className="text-center py-4 text-gray-500">加载中...</div>
              ) : userProfile ? (
                <>
                  {/* 隐私开关 */}
                  <div className="bg-gray-50 rounded-lg p-4 border border-gray-200 space-y-3">
                    <h3 className="font-semibold text-gray-800 mb-2">公开字段设置</h3>

                    {[
                      { key: 'weight', label: '体重', icon: '⚖️' },
                      { key: 'height', label: '身高', icon: '📏' },
                      { key: 'age', label: '年龄', icon: '🎂' },
                      { key: 'gender', label: '性别', icon: '👤' },
                      { key: 'city', label: '所在城市', icon: '🏙️' },
                      { key: 'location', label: 'IP定位', icon: '📍' },
                    ].map(({ key, label, icon }) => (
                      <div key={key} className="flex items-center justify-between py-2 border-b border-gray-100 last:border-0">
                        <span className="text-gray-700">
                          {icon} {label}
                        </span>
                        <button
                          onClick={() => {
                            if (!userProfile.privacy_settings) return;
                            const newSettings = {
                              ...userProfile.privacy_settings,
                              [key]: !userProfile.privacy_settings[key as keyof PrivacySettings],
                            };
                            updateProfileMutation.mutate({ privacy_settings: newSettings });
                          }}
                          disabled={updateProfileMutation.isPending}
                          className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                            userProfile.privacy_settings?.[key as keyof PrivacySettings]
                              ? 'bg-green-500'
                              : 'bg-gray-300'
                          } ${updateProfileMutation.isPending ? 'opacity-50' : ''}`}
                        >
                          <span
                            className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                              userProfile.privacy_settings?.[key as keyof PrivacySettings]
                                ? 'translate-x-6'
                                : 'translate-x-1'
                            }`}
                          />
                        </button>
                      </div>
                    ))}
                  </div>

                  {/* 位置信息 */}
                  <div className="bg-blue-50 rounded-lg p-4 border border-blue-200">
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="font-semibold text-blue-800">📍 位置设置</h3>
                    </div>

                    {/* 位置模式切换 */}
                    <div className="flex items-center gap-4 mb-4 p-3 bg-white rounded-lg border border-blue-200">
                      <span className="text-gray-700 font-medium">定位方式:</span>
                      <div className="flex gap-2">
                        <button
                          onClick={() => {
                            if (userProfile.use_manual_location) {
                              updateManualLocationMutation.mutate({ use_manual_location: false });
                            }
                          }}
                          disabled={updateManualLocationMutation.isPending}
                          className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                            !userProfile.use_manual_location
                              ? 'bg-blue-500 text-white'
                              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                          } ${updateManualLocationMutation.isPending ? 'opacity-50' : ''}`}
                        >
                          🌐 IP自动定位
                        </button>
                        <button
                          onClick={() => {
                            if (!userProfile.use_manual_location) {
                              updateManualLocationMutation.mutate({
                                use_manual_location: true,
                                ...manualLocationForm,
                              });
                            }
                          }}
                          disabled={updateManualLocationMutation.isPending}
                          className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                            userProfile.use_manual_location
                              ? 'bg-blue-500 text-white'
                              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                          } ${updateManualLocationMutation.isPending ? 'opacity-50' : ''}`}
                        >
                          ✏️ 手工输入
                        </button>
                      </div>
                    </div>

                    {/* IP定位模式 */}
                    {!userProfile.use_manual_location && (
                      <div className="space-y-3">
                        <div className="flex items-center justify-between">
                          <span className="text-sm text-blue-700">当前检测位置</span>
                          <button
                            onClick={() => refreshLocationMutation.mutate()}
                            disabled={refreshLocationMutation.isPending}
                            className="px-3 py-1 bg-blue-500 text-white rounded-lg hover:bg-blue-600 text-sm disabled:opacity-50"
                          >
                            {refreshLocationMutation.isPending ? '刷新中...' : '🔄 刷新'}
                          </button>
                        </div>
                        {userProfile.detected_location ? (
                          <div className="text-blue-700 space-y-1">
                            <p>🏙️ 城市: {userProfile.detected_location.city || '未知'}</p>
                            <p>📍 地区: {userProfile.detected_location.region || '未知'}</p>
                            <p>🌍 国家: {userProfile.detected_location.country || '未知'}</p>
                            {userProfile.location_updated_at && (
                              <p className="text-xs text-blue-500 mt-2">
                                最后更新: {formatDateTime(userProfile.location_updated_at)}
                              </p>
                            )}
                          </div>
                        ) : (
                          <p className="text-blue-600">尚未检测到位置信息，点击刷新按钮获取</p>
                        )}
                      </div>
                    )}

                    {/* 手工输入模式 */}
                    {userProfile.use_manual_location && (
                      <div className="space-y-3">
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                          <div>
                            <label className="block text-sm font-medium text-blue-700 mb-1">国家</label>
                            <input
                              type="text"
                              value={manualLocationForm.country}
                              onChange={(e) => setManualLocationForm({ ...manualLocationForm, country: e.target.value })}
                              className="w-full p-2 border border-blue-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                              placeholder="如：中国"
                            />
                          </div>
                          <div>
                            <label className="block text-sm font-medium text-blue-700 mb-1">省份/地区</label>
                            <input
                              type="text"
                              value={manualLocationForm.region}
                              onChange={(e) => setManualLocationForm({ ...manualLocationForm, region: e.target.value })}
                              className="w-full p-2 border border-blue-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                              placeholder="如：浙江省"
                            />
                          </div>
                          <div>
                            <label className="block text-sm font-medium text-blue-700 mb-1">城市</label>
                            <input
                              type="text"
                              value={manualLocationForm.city}
                              onChange={(e) => setManualLocationForm({ ...manualLocationForm, city: e.target.value })}
                              className="w-full p-2 border border-blue-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                              placeholder="如：杭州市"
                            />
                          </div>
                        </div>
                        <button
                          onClick={() => updateManualLocationMutation.mutate({
                            use_manual_location: true,
                            ...manualLocationForm,
                          })}
                          disabled={updateManualLocationMutation.isPending}
                          className="w-full px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:opacity-50"
                        >
                          {updateManualLocationMutation.isPending ? '保存中...' : '💾 保存位置'}
                        </button>
                        {userProfile.manual_location && (
                          <div className="text-xs text-blue-600 mt-2">
                            当前已保存: {userProfile.manual_location.city || ''} {userProfile.manual_location.region || ''} {userProfile.manual_location.country || ''}
                          </div>
                        )}
                      </div>
                    )}
                  </div>

                  {/* 说明 */}
                  <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3 text-sm text-yellow-800">
                    <p className="font-semibold mb-1">⚠️ 隐私说明</p>
                    <ul className="list-disc list-inside space-y-1">
                      <li>这些设置控制通过 API Key 访问时哪些信息可见</li>
                      <li>关闭的字段不会出现在外部 AI 系统获取的数据中</li>
                      <li>位置信息可选择 IP 自动定位（每小时更新）或手工输入</li>
                      <li>使用手工输入时，外部系统将获取您手工设置的位置</li>
                    </ul>
                  </div>
                </>
              ) : (
                <div className="text-center py-4 text-gray-500">无法加载用户画像</div>
              )}
            </div>
          )}
        </div>

        {/* Apple Watch 设备管理 */}
        <div id="apple" className="bg-white rounded-xl shadow-md p-6 mb-6 border border-gray-200">
          <div className="flex items-center gap-3 mb-4">
            <span className="text-3xl">⌚</span>
            <div>
              <h2 className="text-xl font-bold text-gray-900">Apple Watch</h2>
              <p className="text-sm text-gray-600">通过导入 iPhone 健康数据同步 Apple Watch 数据</p>
            </div>
          </div>

          {/* 已配置状态 */}
          {appleDevice && !appleLoading && (
            <div className="bg-green-50 rounded-lg p-4 border border-green-200 mb-4">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <span className="text-2xl">✅</span>
                  <h3 className="font-semibold text-green-900">Apple Health 数据已导入</h3>
                </div>
                <span className="px-3 py-1 bg-green-200 text-green-800 rounded-full text-sm font-semibold">
                  已绑定
                </span>
              </div>
              
              {appleDevice.config?.data_range && (
                <div className="text-sm text-green-800 space-y-1">
                  <p>📅 数据范围: {appleDevice.config.data_range.start} 至 {appleDevice.config.data_range.end}</p>
                  <p>📊 数据天数: {appleDevice.config.data_days || 0} 天</p>
                </div>
              )}
              
              {appleDevice.last_sync_at && (
                <p className="text-xs text-green-700 mt-2">
                  最后同步: {formatDateTime(appleDevice.last_sync_at)}
                </p>
              )}

              <div className="flex gap-3 mt-4">
                <button
                  onClick={() => testAppleMutation.mutate()}
                  disabled={testAppleMutation.isPending}
                  className="px-4 py-2 bg-blue-100 text-blue-700 rounded-lg hover:bg-blue-200 disabled:opacity-50"
                >
                  {testAppleMutation.isPending ? '测试中...' : '🔍 测试连接'}
                </button>
                <button
                  onClick={() => syncAppleMutation.mutate(30)}
                  disabled={syncAppleMutation.isPending}
                  className="px-4 py-2 bg-gradient-to-r from-indigo-500 to-purple-600 text-white rounded-lg hover:from-indigo-600 hover:to-purple-700 disabled:opacity-50"
                >
                  {syncAppleMutation.isPending ? '同步中...' : '🔄 同步数据（30天）'}
                </button>
                <button
                  onClick={async () => {
                    if (confirm('确定要解绑 Apple Watch 吗？')) {
                      try {
                        await deviceApi.unbindDevice('apple');
                        setMessage({ type: 'success', text: '已解绑 Apple Watch' });
                        refetchApple();
                      } catch (error: any) {
                        setMessage({ type: 'error', text: extractErrorMsg(error, '解绑失败') });
                      }
                    }
                  }}
                  className="px-4 py-2 bg-red-100 text-red-700 rounded-lg hover:bg-red-200"
                >
                  🗑️ 解绑
                </button>
              </div>
            </div>
          )}

          {/* 导入文件区域 */}
          <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
            <h3 className="font-semibold text-gray-800 mb-3">📤 导入 Apple Health 数据</h3>
            
            <div className="space-y-4">
              {/* 使用说明 */}
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 text-sm text-blue-800">
                <p className="font-semibold mb-2">📱 导出步骤：</p>
                <ol className="list-decimal list-inside space-y-1">
                  <li>在 iPhone 上打开"健康" App</li>
                  <li>点击右上角头像</li>
                  <li>滚动到底部，点击"导出健康数据"</li>
                  <li>等待导出完成（可能需要几分钟）</li>
                  <li>将导出的 XML 文件上传到此处</li>
                </ol>
              </div>

              {/* 文件选择 */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  选择 Apple Health 导出文件 (XML)
                </label>
                <div className="flex items-center gap-3">
                  <input
                    type="file"
                    accept=".xml,application/xml,text/xml"
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) {
                        if (!file.name.endsWith('.xml')) {
                          setMessage({ type: 'error', text: '请选择 XML 格式的文件' });
                          return;
                        }
                        setAppleFile(file);
                      }
                    }}
                    className="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100"
                    disabled={appleImportProgress.isImporting}
                  />
                </div>
                {appleFile && (
                  <p className="text-sm text-gray-600 mt-2">
                    📄 已选择: {appleFile.name} ({(appleFile.size / 1024 / 1024).toFixed(2)} MB)
                  </p>
                )}
              </div>

              {/* 导入进度 */}
              {appleImportProgress.isImporting && (
                <div className="bg-indigo-50 border border-indigo-200 rounded-lg p-4">
                  <div className="flex items-center gap-3 mb-2">
                    <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-indigo-600"></div>
                    <span className="text-sm font-semibold text-indigo-900">{appleImportProgress.message}</span>
                  </div>
                  <div className="w-full bg-indigo-200 rounded-full h-2">
                    <div
                      className="bg-indigo-600 h-2 rounded-full transition-all duration-300"
                      style={{ width: `${appleImportProgress.progress}%` }}
                    ></div>
                  </div>
                </div>
              )}

              {/* 导入按钮 */}
              <button
                onClick={() => {
                  if (!appleFile) {
                    setMessage({ type: 'error', text: '请先选择文件' });
                    return;
                  }
                  importAppleMutation.mutate(appleFile);
                }}
                disabled={!appleFile || appleImportProgress.isImporting || importAppleMutation.isPending}
                className="w-full px-4 py-3 bg-gradient-to-r from-indigo-500 to-purple-600 text-white rounded-lg hover:from-indigo-600 hover:to-purple-700 disabled:opacity-50 disabled:cursor-not-allowed font-semibold"
              >
                {importAppleMutation.isPending || appleImportProgress.isImporting
                  ? '导入中...'
                  : '📤 导入健康数据'}
              </button>
            </div>
          </div>
        </div>

        {/* Withings 体重秤 */}
        <div id="withings" className="bg-white rounded-xl shadow-md p-6 mb-6 border border-gray-200">
          <div className="flex items-center gap-3 mb-4">
            <span className="text-3xl">{'⚖️'}</span>
            <div>
              <h2 className="text-xl font-bold text-gray-900">Withings 体重秤</h2>
              <p className="text-sm text-gray-600">绑定 Withings 账号，自动同步体重、体脂等体成分数据</p>
            </div>
          </div>

          {withingsLoading ? (
            <div className="text-center py-4 text-gray-500">加载中...</div>
          ) : withingsStatus?.bound && withingsStatus?.is_valid ? (
            <>
              {/* 已绑定状态 */}
              <div className="bg-green-50 rounded-lg p-4 border border-green-200 mb-4">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <span className="text-2xl">{'✅'}</span>
                    <h3 className="font-semibold text-green-900">Withings 已绑定</h3>
                  </div>
                  <span className="px-3 py-1 bg-green-200 text-green-800 rounded-full text-sm font-semibold">
                    已连接
                  </span>
                </div>

                <div className="text-sm text-green-800 space-y-1">
                  {withingsStatus.last_sync_at && (
                    <p>{'📅'} 最后同步: {formatDateTime(withingsStatus.last_sync_at)}</p>
                  )}
                  <p>{'📡'} Webhook 自动推送已启用（称重后数据自动同步）</p>
                </div>

                <div className="flex gap-3 mt-4">
                  <button
                    onClick={() => withingsSyncMutation.mutate(7)}
                    disabled={withingsSyncMutation.isPending}
                    className="px-4 py-2 bg-gradient-to-r from-teal-500 to-emerald-600 text-white rounded-lg hover:from-teal-600 hover:to-emerald-700 disabled:opacity-50"
                  >
                    {withingsSyncMutation.isPending ? '同步中...' : '🔄 同步最近7天'}
                  </button>
                  <button
                    onClick={() => withingsSyncMutation.mutate(30)}
                    disabled={withingsSyncMutation.isPending}
                    className="px-4 py-2 bg-teal-100 text-teal-700 rounded-lg hover:bg-teal-200 disabled:opacity-50"
                  >
                    {withingsSyncMutation.isPending ? '同步中...' : '🔄 同步30天'}
                  </button>
                  <button
                    onClick={() => {
                      if (confirm('确定要解绑 Withings 吗？解绑后将不再自动同步数据。')) {
                        unbindWithingsMutation.mutate();
                      }
                    }}
                    disabled={unbindWithingsMutation.isPending}
                    className="px-4 py-2 bg-red-100 text-red-700 rounded-lg hover:bg-red-200 disabled:opacity-50"
                  >
                    {'🗑️'} 解绑
                  </button>
                </div>
              </div>
            </>
          ) : (
            <>
              {/* 未绑定状态 */}
              {withingsStatus?.bound && !withingsStatus?.is_valid && (
                <div className="bg-yellow-50 rounded-lg p-4 border border-yellow-200 mb-4">
                  <div className="flex items-center gap-2">
                    <span className="text-xl">{'⚠️'}</span>
                    <p className="text-sm text-yellow-800">
                      Withings 授权已过期，请重新绑定。
                      {withingsStatus.last_error && (
                        <span className="block text-xs text-yellow-600 mt-1">错误: {withingsStatus.last_error}</span>
                      )}
                    </p>
                  </div>
                </div>
              )}

              <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
                <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 text-sm text-blue-800 mb-4">
                  <p className="font-semibold mb-2">{'📋'} 绑定说明：</p>
                  <ol className="list-decimal list-inside space-y-1">
                    <li>确保 Withings 体重秤已在 Withings Health Mate App 中配对</li>
                    <li>点击下方按钮，将跳转到 Withings 授权页面</li>
                    <li>登录你的 Withings 账号并授权</li>
                    <li>授权成功后，每次称重数据将自动同步</li>
                  </ol>
                </div>

                <button
                  onClick={() => withingsAuthMutation.mutate()}
                  disabled={withingsAuthMutation.isPending}
                  className="w-full px-4 py-3 bg-gradient-to-r from-teal-500 to-emerald-600 text-white rounded-lg hover:from-teal-600 hover:to-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed font-semibold"
                >
                  {withingsAuthMutation.isPending ? '获取授权链接中...' : '🔗 绑定 Withings 账号'}
                </button>
              </div>
            </>
          )}
        </div>

        {/* API Key 管理 */}
        <div className="bg-white rounded-xl shadow-md p-6 mb-6 border border-gray-200">
          <div
            className="flex items-center justify-between cursor-pointer"
            onClick={() => setShowApiKeySection(!showApiKeySection)}
          >
            <div className="flex items-center gap-3">
              <span className="text-3xl">{'\u{1F511}'}</span>
              <div>
                <h2 className="text-xl font-bold text-gray-900">开发者接口</h2>
                <p className="text-sm text-gray-600">允许外部 AI 系统访问您的健康数据</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {apiKeys.length > 0 && (
                <span className="px-3 py-1 bg-indigo-100 text-indigo-700 rounded-full text-sm">
                  {apiKeys.length} 个 Key
                </span>
              )}
              <span className="text-gray-400 text-2xl">
                {showApiKeySection ? '\u{25BC}' : '\u{203A}'}
              </span>
            </div>
          </div>

          {showApiKeySection && (
            <div className="mt-6 space-y-6">
              {/* 说明 */}
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 text-sm text-blue-800">
                <p className="font-semibold mb-2">{'\u{1F4A1}'} 什么是 API Key？</p>
                <p>API Key 允许外部 AI 健康助手（如 Browser-LLM-Driven、GPT Health 等）访问您的健康数据并提供个性化建议。这些建议会显示在「外部健康建议」页面。</p>
              </div>

              {/* API Key 列表 */}
              {apiKeys.length > 0 && (
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <h3 className="font-semibold text-gray-800">已创建的 API Key</h3>
                    <span className="text-sm text-gray-500">{apiKeys.length} / 10</span>
                  </div>
                  {apiKeys.map((key) => (
                    <div key={key.id} className="flex items-center justify-between p-4 bg-gray-50 rounded-lg border border-gray-200">
                      <div>
                        <p className="font-medium text-gray-900">{key.name}</p>
                        <p className="text-xs text-gray-500">
                          {key.scopes} · {key.last_used_at ? `最后使用: ${new Date(key.last_used_at).toLocaleDateString()}` : '从未使用'}
                        </p>
                      </div>
                      <button
                        onClick={() => handleDeleteApiKey(key.id, key.name)}
                        className="px-3 py-1 bg-red-100 text-red-700 rounded-lg hover:bg-red-200 text-sm"
                      >
                        删除
                      </button>
                    </div>
                  ))}
                </div>
              )}

              {/* 新创建的 Key 展示 */}
              {newlyCreatedKey && (
                <div className="bg-green-50 border-2 border-green-400 rounded-lg p-4 space-y-3">
                  <div className="flex items-center gap-2">
                    <span className="text-2xl">{'\u{1F511}'}</span>
                    <h3 className="font-bold text-green-800">API Key 创建成功！</h3>
                  </div>
                  <p className="text-sm text-green-700">请立即复制并妥善保存此密钥，它只会显示这一次：</p>
                  <div className="flex items-center gap-2">
                    <code className="flex-1 p-3 bg-white border border-green-300 rounded-lg font-mono text-sm text-gray-900 break-all select-all">
                      {newlyCreatedKey}
                    </code>
                    <button
                      onClick={() => {
                        navigator.clipboard.writeText(newlyCreatedKey);
                        setMessage({ type: 'success', text: '已复制到剪贴板' });
                      }}
                      className="px-4 py-3 bg-green-600 text-white rounded-lg hover:bg-green-700 font-medium whitespace-nowrap"
                    >
                      复制
                    </button>
                  </div>
                  <button
                    onClick={() => setNewlyCreatedKey(null)}
                    className="w-full px-4 py-2 bg-green-100 text-green-700 rounded-lg hover:bg-green-200 text-sm"
                  >
                    我已保存，关闭此提示
                  </button>
                </div>
              )}

              {/* 创建新 Key */}
              <div className="space-y-3">
                <h3 className="font-semibold text-gray-800">创建新的 API Key</h3>
                {apiKeys.length >= 10 ? (
                  <div className="p-4 bg-yellow-50 border border-yellow-200 rounded-lg text-sm text-yellow-800">
                    <p className="font-semibold">⚠️ 已达到最大限制</p>
                    <p className="mt-1">您已创建 10 个 API Key，这是允许的最大数量。请删除不需要的 Key 后再创建新的。</p>
                  </div>
                ) : (
                  <div className="flex gap-3">
                    <input
                      type="text"
                      value={newKeyName}
                      onChange={(e) => setNewKeyName(e.target.value)}
                      placeholder="输入名称（如：Browser-LLM-Driven）"
                      className="flex-1 p-3 border border-gray-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                    />
                    <button
                      onClick={handleCreateApiKey}
                      disabled={!newKeyName.trim()}
                      className="px-6 py-3 bg-gradient-to-r from-indigo-500 to-purple-600 text-white rounded-lg hover:from-indigo-600 hover:to-purple-700 disabled:opacity-50 disabled:cursor-not-allowed font-semibold whitespace-nowrap"
                    >
                      + 创建
                    </button>
                  </div>
                )}
              </div>

              {/* 使用说明 */}
              <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 text-sm text-gray-700 space-y-4">
                <div>
                  <p className="font-semibold mb-2">{'\u{1F4DD}'} 使用方法：</p>
                  <ol className="list-decimal list-inside space-y-1">
                    <li>创建 API Key 后，复制并保存（Key 只显示一次）</li>
                    <li>在外部 AI 系统中配置此 API Key</li>
                    <li>外部系统将通过 <code className="bg-gray-200 px-1 rounded">X-API-Key</code> 头部访问您的数据</li>
                    <li>外部系统写入的健康建议将显示在「外部健康建议」页面</li>
                  </ol>
                </div>

                <div>
                  <p className="font-semibold mb-2">{'\u{1F517}'} API 端点：</p>
                  <div className="space-y-2 font-mono text-xs">
                    <div className="bg-white p-2 rounded border">
                      <span className="text-green-600 font-bold">GET</span>
                      <span className="ml-2 text-gray-800">https://health.executor.life/api/v1/external/health-data</span>
                      <p className="text-gray-500 mt-1 font-sans">获取健康数据（支持 ?date=2024-01-25 或 ?start_date=...&end_date=...）</p>
                    </div>
                    <div className="bg-white p-2 rounded border">
                      <span className="text-blue-600 font-bold">POST</span>
                      <span className="ml-2 text-gray-800">https://health.executor.life/api/v1/external/recommendations</span>
                      <p className="text-gray-500 mt-1 font-sans">写入健康建议（JSON Body）</p>
                    </div>
                  </div>
                </div>

                <div>
                  <p className="font-semibold mb-2">{'\u{1F4E6}'} GET 请求示例（读取健康数据）：</p>
                  <pre className="bg-gray-800 text-green-400 p-3 rounded-lg text-xs overflow-x-auto">
{`curl -X GET "https://health.executor.life/api/v1/external/health-data?date=2024-01-25" \\
  -H "X-API-Key: 你的API密钥"`}
                  </pre>
                </div>

                <div>
                  <p className="font-semibold mb-2">{'\u{1F4E4}'} POST 请求示例（写入健康建议）：</p>
                  <pre className="bg-gray-800 text-green-400 p-3 rounded-lg text-xs overflow-x-auto whitespace-pre-wrap">
{`curl -X POST "https://health.executor.life/api/v1/external/recommendations" \\
  -H "X-API-Key: 你的API密钥" \\
  -H "Content-Type: application/json" \\
  -d '{
    "category": "exercise",
    "title": "今日运动建议",
    "content": "根据睡眠数据，建议进行30分钟有氧运动",
    "source_name": "我的AI助手",
    "recommendation_date": "2024-01-25"
  }'`}
                  </pre>
                  <div className="mt-2 text-xs text-gray-600">
                    <p className="font-semibold">POST 请求字段说明：</p>
                    <ul className="mt-1 space-y-1 list-disc list-inside">
                      <li><code className="bg-gray-200 px-1 rounded">category</code>: 建议类别 - <code className="text-blue-600">exercise</code>(运动) / <code className="text-blue-600">diet</code>(饮食) / <code className="text-blue-600">sleep</code>(睡眠) / <code className="text-blue-600">supplement</code>(补剂) / <code className="text-blue-600">general</code>(综合)</li>
                      <li><code className="bg-gray-200 px-1 rounded">title</code>: 建议标题</li>
                      <li><code className="bg-gray-200 px-1 rounded">content</code>: 建议内容（支持 Markdown 格式）</li>
                      <li><code className="bg-gray-200 px-1 rounded">source_name</code>: 来源名称（如 &quot;GPT Health&quot;）</li>
                      <li><code className="bg-gray-200 px-1 rounded">recommendation_date</code>: 建议日期（可选，默认今天）</li>
                    </ul>
                  </div>
                </div>
              </div>

              {/* 跳转外部建议页面 */}
              <a
                href="/external-advice"
                className="block w-full text-center px-4 py-3 bg-purple-100 text-purple-700 rounded-lg hover:bg-purple-200 font-medium"
              >
                {'\u{1F4E1}'} 查看外部健康建议 {'\u{2192}'}
              </a>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}

// 导出受保护的页面
export default function SettingsPage() {
  return (
    <ProtectedRoute>
      <SettingsContent />
    </ProtectedRoute>
  );
}
