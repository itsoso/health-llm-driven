'use client';

import { useState, useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import ProtectedRoute from '@/components/ProtectedRoute';

// 使用相对路径，通过Next.js代理到后端
const API_BASE = '/api';

interface GarminCredential {
  id: number;
  garmin_email: string;
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
  });
  const [showGarminForm, setShowGarminForm] = useState(false);
  const [syncDays, setSyncDays] = useState(7);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [highlightGarmin, setHighlightGarmin] = useState(false);
  
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

  // 保存Garmin凭证
  const saveGarminMutation = useMutation({
    mutationFn: async (data: { garmin_email: string; garmin_password: string }) => {
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
      setGarminForm({ garmin_email: '', garmin_password: '' });
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
    mutationFn: async (data: { garmin_email: string; garmin_password: string }) => {
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
        return { success: false, message: '服务器错误，请稍后重试' };
      }
      
      return res.json();
    },
    onSuccess: (data) => {
      if (data.success) {
        setMessage({ type: 'success', text: data.message });
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
                setMessage({ type: 'error', text: data.message });
              }
            } catch (e) {
              // 忽略解析错误
            }
          }
        }
      }
    } catch (error: any) {
      setSyncProgress(prev => ({ ...prev, isSyncing: false }));
      setMessage({ type: 'error', text: error.message || '同步失败' });
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
                  </p>
                  <p className={`text-sm mt-1 ${garminCredential.sync_enabled ? 'text-green-700' : 'text-gray-500'}`}>
                    账号: {garminCredential.garmin_email}
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
                <div className="flex gap-3">
                  <button
                    onClick={() => testConnectionMutation.mutate(garminForm)}
                    disabled={!garminForm.garmin_email || !garminForm.garmin_password || testConnectionMutation.isPending}
                    className="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 disabled:opacity-50"
                  >
                    {testConnectionMutation.isPending ? '测试中...' : '🔍 测试连接'}
                  </button>
                  <button
                    onClick={() => saveGarminMutation.mutate(garminForm)}
                    disabled={!garminForm.garmin_email || !garminForm.garmin_password || saveGarminMutation.isPending}
                    className="px-4 py-2 bg-gradient-to-r from-indigo-500 to-purple-600 text-white rounded-lg hover:from-indigo-600 hover:to-purple-700 disabled:opacity-50"
                  >
                    {saveGarminMutation.isPending ? '保存中...' : '💾 保存凭证'}
                  </button>
                  {showGarminForm && (
                    <button
                      onClick={() => {
                        setShowGarminForm(false);
                        setGarminForm({ garmin_email: '', garmin_password: '' });
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

