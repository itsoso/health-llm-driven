'use client';

import { useState, useRef, useEffect } from 'react';
import { useQuery, useMutation, QueryClient } from '@tanstack/react-query';
import { useAuth } from '@/contexts/AuthContext';
import { formatDateTime } from '@/utils/timezone';
import { GARMIN_ENDPOINTS } from './garminEndpoints';

// 使用相对路径，通过Next.js代理到后端
const API_BASE = '/api';

export interface GarminCredential {
  id: number;
  garmin_email: string;
  is_cn: boolean;
  last_sync_at: string | null;
  sync_enabled: boolean;
}

export function extractErrorMsg(error: any, fallback: string): string {
  const detail = error?.response?.data?.detail;
  if (!detail) return error?.message || fallback;
  if (typeof detail === 'string') return detail;
  return JSON.stringify(detail);
}

interface GarminSectionProps {
  token: string | null;
  message: { type: 'success' | 'error'; text: string } | null;
  setMessage: (msg: { type: 'success' | 'error'; text: string } | null) => void;
  queryClient: QueryClient;
  highlightGarmin: boolean;
  setHighlightGarmin: (v: boolean) => void;
}

export default function GarminSection({
  token,
  message,
  setMessage,
  queryClient,
  highlightGarmin,
  setHighlightGarmin,
}: GarminSectionProps) {
  const { refreshUser } = useAuth();
  const garminSectionRef = useRef<HTMLDivElement>(null);

  const [garminForm, setGarminForm] = useState({
    garmin_email: '',
    garmin_password: '',
    is_cn: false,
  });
  const [showGarminForm, setShowGarminForm] = useState(false);
  const [showGarminPassword, setShowGarminPassword] = useState(false);
  const [syncDays, setSyncDays] = useState(1);
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

  // MFA 两步验证状态
  const [showMFA, setShowMFA] = useState(false);
  const [mfaCode, setMfaCode] = useState('');
  const [mfaSessionId, setMfaSessionId] = useState<string | null>(null);
  const [mfaContext, setMfaContext] = useState<'test' | 'connect' | 'sync' | null>(null);
  const [pendingSyncDays, setPendingSyncDays] = useState<number | null>(null);

  // 处理 URL hash 滚动到 Garmin 设置
  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (window.location.hash === '#garmin') {
      const timer = setTimeout(() => {
        garminSectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        setHighlightGarmin(true);
        setTimeout(() => setHighlightGarmin(false), 3000);
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [setHighlightGarmin]);

  // 获取Garmin凭证
  const { data: garminCredential, isLoading: garminLoading } = useQuery({
    queryKey: ['garmin-credential'],
    queryFn: async () => {
      if (!token) return null;
      const res = await fetch(GARMIN_ENDPOINTS.credentials, {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (res.status === 404) return null;
      if (!res.ok) throw new Error('获取失败');
      return res.json() as Promise<GarminCredential>;
    },
    enabled: !!token,
  });

  // 认证成功后原子保存 Garmin 连接
  const saveGarminMutation = useMutation({
    mutationFn: async (data: { garmin_email: string; garmin_password: string; is_cn: boolean }) => {
      const res = await fetch(GARMIN_ENDPOINTS.connect, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify(data),
      });

      const contentType = res.headers.get('content-type');
      if (!contentType || !contentType.includes('application/json')) {
        throw new Error('服务器错误，请稍后重试');
      }

      const result = await res.json();
      if (!res.ok) {
        throw new Error(result.detail || '保存失败');
      }
      if (!result.success && !result.mfa_required) {
        throw new Error(result.message || '连接失败');
      }
      return result;
    },
    onSuccess: (data) => {
      if (data.mfa_required && data.mfa_session_id) {
        setMfaSessionId(data.mfa_session_id);
        setMfaContext('connect');
        setShowMFA(true);
        setMessage({ type: 'error', text: '🔐 需要两步验证，请输入验证码' });
        return;
      }
      queryClient.invalidateQueries({ queryKey: ['garmin-credential'] });
      refreshUser();
      setShowGarminForm(false);
      setGarminForm({ garmin_email: '', garmin_password: '', is_cn: false });
      setMessage({ type: 'success', text: 'Garmin 账号已安全连接。' });
    },
    onError: (error: Error) => {
      setMessage({ type: 'error', text: error.message });
    },
  });

  // 删除Garmin凭证
  const deleteGarminMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch(GARMIN_ENDPOINTS.credentials, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` },
      });

      const contentType = res.headers.get('content-type');
      if (!contentType || !contentType.includes('application/json')) {
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

      const contentType = res.headers.get('content-type');
      if (!contentType || !contentType.includes('application/json')) {
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
        setMfaSessionId(data.mfa_session_id);
        setMfaContext('test');
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
        const isConnectContext = mfaContext === 'connect';

        if (isSyncContext) {
          setMessage({ type: 'success', text: '✅ 验证成功！正在开始同步...' });
          setShowMFA(false);
          setMfaCode('');
          setMfaSessionId(null);

          const syncDaysVal = pendingSyncDays || 1;
          setPendingSyncDays(null);

          setMfaContext(null);

          setTimeout(() => {
            if (!syncProgress.isSyncing) {
              startSyncWithProgressRequest(syncDaysVal);
            }
          }, 500);
        } else {
          if (isConnectContext) {
            setShowGarminForm(false);
            setGarminForm({ garmin_email: '', garmin_password: '', is_cn: false });
            refreshUser();
          }
          setMessage({
            type: 'success',
            text: data.message || (isConnectContext
              ? 'Garmin 账号已安全连接。'
              : 'Garmin 凭证验证成功。'),
          });
          setShowMFA(false);
          setMfaCode('');
          setMfaSessionId(null);
          setMfaContext(null);
        }

        queryClient.invalidateQueries({ queryKey: ['garmin-credential'] });
      } else {
        let errorMsg = data.message;
        if (errorMsg.includes('Couldn\'t find ticket') || errorMsg.includes('验证失败')) {
          errorMsg = '❌ 验证码错误或已过期！请检查验证器应用中的最新验证码（每30秒更新一次）。';
        }
        setMessage({ type: 'error', text: errorMsg });
      }
    },
    onError: (error: Error) => {
      let errorMsg = error.message;
      if (errorMsg.includes('Couldn\'t find ticket') || errorMsg.includes('验证失败')) {
        errorMsg = '❌ 验证码错误或已过期！请检查验证器应用中的最新验证码（每30秒更新一次）。';
      }
      setMessage({ type: 'error', text: errorMsg });
    },
  });

  // 流式同步Garmin数据（带进度）
  const startSyncWithProgress = async (days: number) => {
    startSyncWithProgressRequest(days);
  };

  const startSyncWithProgressRequest = async (days: number) => {
    if (!token) return;

    if (syncProgress.isSyncing) {
      return;
    }

    setMfaContext('sync');
    setPendingSyncDays(days);

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
                if (data.mfa_required) {
                  if (data.mfa_session_id) {
                    setMfaSessionId(data.mfa_session_id);
                    setMfaContext('sync');
                    setPendingSyncDays(days);
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

      const contentType = res.headers.get('content-type');
      if (!contentType || !contentType.includes('application/json')) {
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

  return (
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
                {saveGarminMutation.isPending ? '连接中...' : '🔗 连接并保存'}
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
  );
}
