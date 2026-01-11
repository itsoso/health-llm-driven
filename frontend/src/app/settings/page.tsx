'use client';

import { useState, useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import ProtectedRoute from '@/components/ProtectedRoute';
import { deviceApi } from '@/services/api';

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

  const [garminForm, setGarminForm] = useState({
    garmin_email: '',
    garmin_password: '',
    is_cn: false,
  });
  const [showGarminForm, setShowGarminForm] = useState(false);
  const [syncDays, setSyncDays] = useState(7);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [highlightGarmin, setHighlightGarmin] = useState(false);
  
  // MFA 两步验证状态
  const [showMFA, setShowMFA] = useState(false);
  const [mfaCode, setMfaCode] = useState('');
  const [mfaSessionId, setMfaSessionId] = useState<string | null>(null);
  const [mfaContext, setMfaContext] = useState<'test' | 'sync' | null>(null); // MFA验证的上下文：测试连接或同步
  const [pendingSyncDays, setPendingSyncDays] = useState<number | null>(null); // 待同步的天数（如果是在同步场景）
  const [authenticatedSessionId, setAuthenticatedSessionId] = useState<string | null>(null); // MFA验证成功后的session_id，用于复用认证状态
  
  // Apple Watch 状态
  const [appleFile, setAppleFile] = useState<File | null>(null);
  const [appleImportProgress, setAppleImportProgress] = useState<{
    isImporting: boolean;
    progress: number;
    message: string;
  }>({
    isImporting: false,
    progress: 0,
    message: '',
  });
  
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
      const errorMsg = error.response?.data?.detail || error.message || '导入失败，请重试';
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
      const errorMsg = error.response?.data?.detail || error.message || '测试失败';
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
      const errorMsg = error.response?.data?.detail || error.message || '同步失败';
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
      if (data.success) {
        const isSyncContext = mfaContext === 'sync';
        
        // 保存验证成功后的session_id，用于后续同步复用
        if (data.session_id) {
          setAuthenticatedSessionId(data.session_id);
        }
        
        if (isSyncContext) {
          // 同步场景：验证成功后自动触发同步
          setMessage({ type: 'success', text: '✅ 验证成功！正在开始同步...' });
          setShowMFA(false);
          setMfaCode('');
          setMfaSessionId(null);
          setMfaContext(null);
          
          // 自动触发同步
          const syncDays = pendingSyncDays || 7;
          setPendingSyncDays(null);
          
          // 延迟一下，让用户看到成功消息
          setTimeout(() => {
            startSyncWithProgress(syncDays);
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
        setMessage({ type: 'error', text: data.message });
      }
    },
    onError: (error: Error) => {
      setMessage({ type: 'error', text: error.message });
    },
  });

  // 流式同步Garmin数据（带进度）
  const startSyncWithProgress = async (days: number) => {
    if (!token) return;
    
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
      const response = await fetch(`${API_BASE}/auth/garmin/sync-stream?days=${days}`, {
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
                // 检查是否是MFA错误
                if (data.mfa_required) {
                  if (data.mfa_session_id) {
                    setMfaSessionId(data.mfa_session_id);
                    setMfaContext('sync'); // 标记为同步场景
                    setPendingSyncDays(days); // 保存待同步的天数
                    setShowMFA(true);
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

  // 未登录跳转
  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login');
    }
  }, [authLoading, isAuthenticated, router]);

  // 处理 URL hash 滚动到 Garmin 设置
  useEffect(() => {
    if (typeof window !== 'undefined' && window.location.hash === '#garmin') {
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
  }, []);

  if (authLoading || !isAuthenticated) {
    return (
      <main className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 pt-24 pb-8 px-4">
        <div className="max-w-4xl mx-auto text-center py-20">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">加载中...</p>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 pt-24 pb-8 px-4">
      <div className="max-w-4xl mx-auto">
        {/* 消息提示 */}
        {message && (
          <div className={`mb-6 p-4 rounded-lg ${
            message.type === 'success' 
              ? 'bg-green-50 border border-green-200 text-green-800' 
              : 'bg-red-50 border border-red-200 text-red-800'
          }`}>
            {message.type === 'success' ? '✅' : '❌'} {message.text}
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
              <p className="text-gray-900 font-medium">{user?.email || '-'}</p>
            </div>
            <div>
              <label className="text-sm text-gray-500">姓名</label>
              <p className="text-gray-900 font-medium">{user?.name || '-'}</p>
            </div>
            <div>
              <label className="text-sm text-gray-500">账户状态</label>
              <p className="text-green-600 font-medium">
                {user?.is_active ? '✓ 已激活' : '✗ 未激活'}
              </p>
            </div>
          </div>
          <div className="mt-4 pt-4 border-t">
            <button
              onClick={logout}
              className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors"
            >
              退出登录
            </button>
          </div>
        </div>

        {/* Garmin设置卡片 */}
        <div 
          ref={garminSectionRef}
          id="garmin"
          className={`bg-white rounded-xl shadow-lg p-6 border transition-all duration-500 ${
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
                      最后同步: {new Date(garminCredential.last_sync_at).toLocaleString('zh-CN')}
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
                  <input
                    type="password"
                    value={garminForm.garmin_password}
                    onChange={(e) => setGarminForm({ ...garminForm, garmin_password: e.target.value })}
                    className="w-full p-3 border border-gray-300 rounded-lg text-gray-900"
                    placeholder="请输入Garmin Connect密码"
                  />
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
                  最后同步: {new Date(appleDevice.last_sync_at).toLocaleString('zh-CN')}
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
                        setMessage({ type: 'error', text: error.response?.data?.detail || '解绑失败' });
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

