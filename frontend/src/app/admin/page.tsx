'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { api } from '@/services/api';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

interface AdminUser {
  id: number;
  username: string | null;
  email: string | null;
  name: string;
  gender: string | null;
  is_active: boolean;
  is_admin: boolean;
  is_approved: boolean;
  created_at: string | null;
  last_activity: string | null;
  has_garmin: boolean;
  health_records_count: number;
  medical_exams_count: number;
}

interface NewsApiKey {
  id: number;
  name: string;
  api_key: string | null;
  is_active: boolean;
  last_used_at: string | null;
  created_at: string;
}

interface AdminStats {
  total_users: number;
  active_users: number;
  admin_users: number;
  users_with_garmin: number;
  total_health_records: number;
  total_medical_exams: number;
  new_users_today: number;
  new_users_week: number;
}

interface UserListResponse {
  users: AdminUser[];
  total: number;
  page: number;
  page_size: number;
}

interface GarminSyncUser {
  user_id: number;
  username: string | null;
  name: string | null;
  garmin_email: string;
  sync_enabled: boolean;
  credentials_valid: boolean;
  last_error: string | null;
  error_count: number;
  last_sync_at: string | null;
  latest_data_date: string | null;
  total_records: number;
}

interface GarminSyncStatus {
  total_configured_users: number;
  valid_credentials: number;
  invalid_credentials: number;
  users: GarminSyncUser[];
}

interface SyncResult {
  total_users: number;
  success_users: number;
  failed_users: number;
  details: Array<{
    user_id: number;
    success: boolean;
    success_count: number;
    error_count: number;
    message: string;
  }>;
}

interface ClearCacheResult {
  message: string;
  deleted_count: number;
}

// 邀请码相关类型
interface InvitationCode {
  id: number;
  code: string;
  note: string | null;
  max_uses: number;
  used_count: number;
  remaining_uses: number;
  is_active: boolean;
  is_valid: boolean;
  expires_at: string | null;
  created_at: string;
  creator_name: string | null;
}

interface Application {
  id: number;
  email: string;
  name: string;
  phone: string | null;
  status: 'pending' | 'approved' | 'rejected';
  health_questionnaire: {
    age?: number;
    gender?: string;
    height_cm?: number;
    weight_kg?: number;
    health_goals?: string[];
    chronic_conditions?: string[];
    wearable_devices?: string[];
    exercise_frequency?: string;
    why_join?: string;
  } | null;
  review_note: string | null;
  created_at: string;
  reviewed_at: string | null;
  reviewer_name: string | null;
}

interface InvitationStats {
  invitation_codes: {
    total: number;
    active: number;
    total_uses: number;
  };
  applications: {
    total: number;
    pending: number;
    approved: number;
    rejected: number;
  };
}

export default function AdminPage() {
  const router = useRouter();
  const { user, isAuthenticated, isLoading: authLoading } = useAuth();
  const queryClient = useQueryClient();
  
  const [activeTab, setActiveTab] = useState<'users' | 'garmin' | 'invitation' | 'apikeys' | 'performance'>('users');
  const [searchTerm, setSearchTerm] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [selectedUser, setSelectedUser] = useState<AdminUser | null>(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [syncDays, setSyncDays] = useState(3);
  const [syncResult, setSyncResult] = useState<SyncResult | null>(null);
  const [syncingUserId, setSyncingUserId] = useState<number | null>(null);
  const pageSize = 15;

  // 邀请码相关 state
  const [invitationCodes, setInvitationCodes] = useState<InvitationCode[]>([]);
  const [applications, setApplications] = useState<Application[]>([]);
  const [invitationStats, setInvitationStats] = useState<InvitationStats | null>(null);
  const [selectedApp, setSelectedApp] = useState<Application | null>(null);
  const [reviewNote, setReviewNote] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('pending');
  const [showCreateCode, setShowCreateCode] = useState(false);
  const [newCodeNote, setNewCodeNote] = useState('');
  const [newCodeMaxUses, setNewCodeMaxUses] = useState(10);
  const [newCodeExpiresDays, setNewCodeExpiresDays] = useState<number | null>(null);
  const [invitationLoading, setInvitationLoading] = useState(false);

  // API Key 相关 state
  const [apiKeys, setApiKeys] = useState<NewsApiKey[]>([]);
  const [apiKeysLoading, setApiKeysLoading] = useState(false);
  const [showCreateApiKey, setShowCreateApiKey] = useState(false);
  const [newApiKeyName, setNewApiKeyName] = useState('');
  const [newApiKey, setNewApiKey] = useState<string | null>(null);

  // 权限检查
  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login');
    } else if (!authLoading && isAuthenticated && !user?.is_admin) {
      router.push('/');
    }
  }, [authLoading, isAuthenticated, user, router]);

  // 获取邀请码数据
  const fetchInvitationData = useCallback(async () => {
    setInvitationLoading(true);
    try {
      const [appsRes, codesRes, statsRes] = await Promise.all([
        api.get(`/invitation/applications${statusFilter ? `?status=${statusFilter}` : ''}`),
        api.get('/invitation/codes'),
        api.get('/invitation/stats'),
      ]);
      setApplications(appsRes.data);
      setInvitationCodes(codesRes.data);
      setInvitationStats(statsRes.data);
    } catch (error) {
      console.error('Failed to fetch invitation data:', error);
    } finally {
      setInvitationLoading(false);
    }
  }, [statusFilter]);

  // 切换到邀请码 tab 时加载数据
  useEffect(() => {
    if (activeTab === 'invitation' && isAuthenticated && user?.is_admin) {
      fetchInvitationData();
    }
  }, [activeTab, isAuthenticated, user, fetchInvitationData]);

  // 获取统计数据
  const { data: stats, isLoading: statsLoading } = useQuery<AdminStats>({
    queryKey: ['admin-stats'],
    queryFn: async () => {
      const res = await api.get('/admin/stats');
      return res.data;
    },
    enabled: isAuthenticated && user?.is_admin,
  });

  // 获取用户列表
  const { data: userList, isLoading: usersLoading, refetch } = useQuery<UserListResponse>({
    queryKey: ['admin-users', currentPage, searchTerm],
    queryFn: async () => {
      const params = new URLSearchParams({
        page: currentPage.toString(),
        page_size: pageSize.toString(),
      });
      if (searchTerm) {
        params.append('search', searchTerm);
      }
      const res = await api.get(`/admin/users?${params}`);
      return res.data;
    },
    enabled: isAuthenticated && user?.is_admin,
  });

  // 设置管理员权限
  const setAdminMutation = useMutation({
    mutationFn: async ({ userId, isAdmin }: { userId: number; isAdmin: boolean }) => {
      const res = await api.put(`/admin/users/${userId}/admin`, { is_admin: isAdmin });
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-users'] });
      queryClient.invalidateQueries({ queryKey: ['admin-stats'] });
    },
  });

  // 设置用户状态
  const setActiveMutation = useMutation({
    mutationFn: async ({ userId, isActive }: { userId: number; isActive: boolean }) => {
      const res = await api.put(`/admin/users/${userId}/active`, { is_active: isActive });
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-users'] });
      queryClient.invalidateQueries({ queryKey: ['admin-stats'] });
    },
  });

  // 删除用户
  const deleteUserMutation = useMutation({
    mutationFn: async (userId: number) => {
      const res = await api.delete(`/admin/users/${userId}`);
      return res.data;
    },
    onSuccess: (data) => {
      setShowDeleteConfirm(false);
      setSelectedUser(null);
      alert(data.message || '用户删除成功');
      queryClient.invalidateQueries({ queryKey: ['admin-users'] });
      queryClient.invalidateQueries({ queryKey: ['admin-stats'] });
    },
    onError: (error: any) => {
      console.error('删除用户失败:', error);
      const errorMessage = error?.response?.data?.detail || error?.message || '删除用户失败，请稍后重试';
      alert(`❌ ${errorMessage}`);
      setShowDeleteConfirm(false);
      setSelectedUser(null);
    },
  });

  // 获取 Garmin 同步状态
  const { data: garminSyncStatus, isLoading: garminStatusLoading, refetch: refetchGarminStatus } = useQuery<GarminSyncStatus>({
    queryKey: ['admin-garmin-sync-status'],
    queryFn: async () => {
      const res = await api.get('/admin/garmin/sync-status');
      return res.data;
    },
    enabled: isAuthenticated && user?.is_admin && activeTab === 'garmin',
  });

  // 同步所有用户
  const syncAllMutation = useMutation({
    mutationFn: async (days: number) => {
      const res = await api.post(`/admin/garmin/sync-all?days=${days}`);
      return res.data;
    },
    onSuccess: (data) => {
      setSyncResult(data);
      queryClient.invalidateQueries({ queryKey: ['admin-garmin-sync-status'] });
    },
  });

  // 同步单个用户
  const syncUserMutation = useMutation({
    mutationFn: async ({ userId, days }: { userId: number; days: number }) => {
      setSyncingUserId(userId);
      const res = await api.post(`/admin/garmin/sync-user/${userId}?days=${days}`);
      return res.data;
    },
    onSuccess: () => {
      setSyncingUserId(null);
      queryClient.invalidateQueries({ queryKey: ['admin-garmin-sync-status'] });
    },
    onError: () => {
      setSyncingUserId(null);
    },
  });

  // 重置用户凭证状态
  const resetCredentialsMutation = useMutation({
    mutationFn: async (userId: number) => {
      const res = await api.post(`/admin/garmin/reset-credentials/${userId}`);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-garmin-sync-status'] });
    },
  });

  // 启用/禁用用户Garmin同步
  const toggleSyncMutation = useMutation({
    mutationFn: async ({ userId, syncEnabled }: { userId: number; syncEnabled: boolean }) => {
      const res = await api.put(`/admin/garmin/sync-enabled/${userId}`, { sync_enabled: syncEnabled });
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-garmin-sync-status'] });
    },
  });

  // 清理用户缓存
  const clearUserCacheMutation = useMutation({
    mutationFn: async (userId: number) => {
      const res = await api.delete(`/admin/users/${userId}/cache`);
      return res.data as ClearCacheResult;
    },
    onSuccess: (data) => {
      alert(`${data.message}（删除 ${data.deleted_count} 条记录）`);
    },
  });

  // 清理所有无数据缓存
  const clearNoDataCacheMutation = useMutation({
    mutationFn: async () => {
      const res = await api.delete('/admin/cache/no-data');
      return res.data as ClearCacheResult;
    },
    onSuccess: (data) => {
      alert(`${data.message}（删除 ${data.deleted_count} 条记录）`);
    },
  });

  // 清理所有缓存
  const clearAllCacheMutation = useMutation({
    mutationFn: async () => {
      const res = await api.delete('/admin/cache/all');
      return res.data as ClearCacheResult;
    },
    onSuccess: (data) => {
      alert(`${data.message}（删除 ${data.deleted_count} 条记录）`);
    },
  });

  // 邀请码相关操作
  const handleReview = async (approved: boolean) => {
    if (!selectedApp) return;
    
    try {
      await api.post(`/invitation/applications/${selectedApp.id}/review`, {
        approved,
        note: reviewNote || null,
      });
      setSelectedApp(null);
      setReviewNote('');
      fetchInvitationData();
    } catch (error) {
      console.error('Failed to review:', error);
      alert('审批失败，请重试');
    }
  };

  const handleCreateCode = async () => {
    try {
      await api.post('/invitation/codes', {
        note: newCodeNote || null,
        max_uses: newCodeMaxUses,
        expires_days: newCodeExpiresDays,
      });
      setShowCreateCode(false);
      setNewCodeNote('');
      setNewCodeMaxUses(10);
      setNewCodeExpiresDays(null);
      fetchInvitationData();
    } catch (error) {
      console.error('Failed to create code:', error);
      alert('创建失败，请重试');
    }
  };

  const handleDisableCode = async (codeId: number) => {
    if (!confirm('确定要禁用此邀请码吗？')) return;
    
    try {
      await api.delete(`/invitation/codes/${codeId}`);
      fetchInvitationData();
    } catch (error) {
      console.error('Failed to disable code:', error);
      alert('操作失败，请重试');
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    alert('已复制到剪贴板');
  };

  // API Key 相关操作
  const fetchApiKeys = useCallback(async () => {
    setApiKeysLoading(true);
    try {
      const res = await api.get('/news/admin/api-keys');
      setApiKeys(res.data);
    } catch (error) {
      console.error('Failed to fetch API keys:', error);
    } finally {
      setApiKeysLoading(false);
    }
  }, []);

  // 切换到 API Keys tab 时加载数据
  useEffect(() => {
    if (activeTab === 'apikeys' && isAuthenticated && user?.is_admin) {
      fetchApiKeys();
    }
  }, [activeTab, isAuthenticated, user, fetchApiKeys]);

  const handleCreateApiKey = async () => {
    if (!newApiKeyName.trim()) {
      alert('请输入 API Key 名称');
      return;
    }
    try {
      const res = await api.post('/news/admin/api-keys', { name: newApiKeyName });
      setNewApiKey(res.data.api_key);
      setNewApiKeyName('');
      fetchApiKeys();
    } catch (error) {
      console.error('Failed to create API key:', error);
      alert('创建 API Key 失败');
    }
  };

  const handleDeleteApiKey = async (keyId: number) => {
    if (!confirm('确定要删除此 API Key 吗？删除后将无法恢复。')) return;
    try {
      await api.delete(`/news/admin/api-keys/${keyId}`);
      fetchApiKeys();
    } catch (error) {
      console.error('Failed to delete API key:', error);
      alert('删除 API Key 失败');
    }
  };

  // 设置用户 VIP 状态
  const setVipMutation = useMutation({
    mutationFn: async ({ userId, isApproved }: { userId: number; isApproved: boolean }) => {
      const res = await api.put(`/admin/users/${userId}/approve`, { is_approved: isApproved });
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-users'] });
    },
  });

  // 加载状态
  if (authLoading || !isAuthenticated || !user?.is_admin) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-400 mx-auto mb-4"></div>
          <p className="text-purple-200">验证权限中...</p>
        </div>
      </div>
    );
  }

  const totalPages = userList ? Math.ceil(userList.total / pageSize) : 0;

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setCurrentPage(1);
    refetch();
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleDateString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <main className="min-h-screen p-8 bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 pt-4">
      <div className="max-w-7xl mx-auto">
        {/* 页面标题 */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-white mb-2">🛡️ 管理后台</h1>
          <p className="text-purple-200">管理用户、Garmin同步和邀请码</p>
        </div>

        {/* Tab 切换 */}
        <div className="flex gap-2 mb-6">
          <button
            onClick={() => setActiveTab('users')}
            className={`px-6 py-2 rounded-lg font-medium transition-colors ${
              activeTab === 'users'
                ? 'bg-purple-600 text-white'
                : 'bg-white/10 text-purple-200 hover:bg-white/20'
            }`}
          >
            👥 用户管理
          </button>
          <button
            onClick={() => setActiveTab('garmin')}
            className={`px-6 py-2 rounded-lg font-medium transition-colors ${
              activeTab === 'garmin'
                ? 'bg-purple-600 text-white'
                : 'bg-white/10 text-purple-200 hover:bg-white/20'
            }`}
          >
            ⌚ Garmin同步
          </button>
          <button
            onClick={() => setActiveTab('invitation')}
            className={`px-6 py-2 rounded-lg font-medium transition-colors ${
              activeTab === 'invitation'
                ? 'bg-purple-600 text-white'
                : 'bg-white/10 text-purple-200 hover:bg-white/20'
            }`}
          >
            🎫 邀请码管理
          </button>
          <button
            onClick={() => setActiveTab('apikeys')}
            className={`px-6 py-2 rounded-lg font-medium transition-colors ${
              activeTab === 'apikeys'
                ? 'bg-purple-600 text-white'
                : 'bg-white/10 text-purple-200 hover:bg-white/20'
            }`}
          >
            🔑 API Key
          </button>
          <button
            onClick={() => router.push('/admin/performance')}
            className="px-6 py-2 rounded-lg font-medium transition-colors bg-white/10 text-purple-200 hover:bg-white/20"
          >
            📈 性能监控
          </button>
        </div>

        {/* 用户管理 Tab */}
        {activeTab === 'users' && (
          <>
            {/* 缓存管理 */}
            <div className="bg-white/10 backdrop-blur-lg rounded-xl p-4 mb-6 border border-white/20">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <h3 className="text-lg font-semibold text-white">🗑️ 缓存管理</h3>
                  <p className="text-purple-200 text-sm">清理每日AI建议缓存，强制重新生成</p>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => clearNoDataCacheMutation.mutate()}
                    disabled={clearNoDataCacheMutation.isPending}
                    className="px-4 py-2 bg-yellow-600 text-white rounded-lg hover:bg-yellow-700 transition-colors disabled:opacity-50 text-sm"
                  >
                    {clearNoDataCacheMutation.isPending ? '清理中...' : '清理无数据缓存'}
                  </button>
                  <button
                    onClick={() => {
                      if (confirm('确定要清理所有用户的缓存吗？这将强制所有用户重新生成AI建议。')) {
                        clearAllCacheMutation.mutate();
                      }
                    }}
                    disabled={clearAllCacheMutation.isPending}
                    className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors disabled:opacity-50 text-sm"
                  >
                    {clearAllCacheMutation.isPending ? '清理中...' : '清理全部缓存'}
                  </button>
                </div>
              </div>
            </div>

            {/* 统计卡片 */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
              <div className="bg-white/10 backdrop-blur-lg rounded-xl p-4 border border-white/20">
                <div className="text-3xl font-bold text-white">{stats?.total_users || 0}</div>
                <div className="text-purple-200 text-sm">总用户数</div>
              </div>
              <div className="bg-white/10 backdrop-blur-lg rounded-xl p-4 border border-white/20">
                <div className="text-3xl font-bold text-green-400">{stats?.active_users || 0}</div>
                <div className="text-purple-200 text-sm">活跃用户</div>
              </div>
              <div className="bg-white/10 backdrop-blur-lg rounded-xl p-4 border border-white/20">
                <div className="text-3xl font-bold text-blue-400">{stats?.users_with_garmin || 0}</div>
                <div className="text-purple-200 text-sm">绑定Garmin</div>
              </div>
              <div className="bg-white/10 backdrop-blur-lg rounded-xl p-4 border border-white/20">
                <div className="text-3xl font-bold text-yellow-400">{stats?.new_users_week || 0}</div>
                <div className="text-purple-200 text-sm">本周新增</div>
              </div>
            </div>

            {/* 更多统计 */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
              <div className="bg-white/5 backdrop-blur rounded-lg p-3 border border-white/10">
                <div className="text-xl font-semibold text-white">{stats?.admin_users || 0}</div>
                <div className="text-purple-300 text-xs">管理员</div>
              </div>
              <div className="bg-white/5 backdrop-blur rounded-lg p-3 border border-white/10">
                <div className="text-xl font-semibold text-white">{stats?.total_health_records || 0}</div>
                <div className="text-purple-300 text-xs">健康记录</div>
              </div>
              <div className="bg-white/5 backdrop-blur rounded-lg p-3 border border-white/10">
                <div className="text-xl font-semibold text-white">{stats?.total_medical_exams || 0}</div>
                <div className="text-purple-300 text-xs">体检报告</div>
              </div>
              <div className="bg-white/5 backdrop-blur rounded-lg p-3 border border-white/10">
                <div className="text-xl font-semibold text-white">{stats?.new_users_today || 0}</div>
                <div className="text-purple-300 text-xs">今日新增</div>
              </div>
            </div>

            {/* 搜索和用户列表 */}
        <div className="bg-white/10 backdrop-blur-lg rounded-xl border border-white/20 overflow-hidden">
          {/* 搜索栏 */}
          <div className="p-4 border-b border-white/10">
            <form onSubmit={handleSearch} className="flex gap-2">
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="搜索用户名、邮箱或姓名..."
                className="flex-1 px-4 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-purple-300 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
              <button
                type="submit"
                className="px-6 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors"
              >
                搜索
              </button>
            </form>
          </div>

          {/* 用户表格 */}
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-white/5">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-purple-200 uppercase tracking-wider">ID</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-purple-200 uppercase tracking-wider">用户</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-purple-200 uppercase tracking-wider">邮箱</th>
                  <th className="px-4 py-3 text-center text-xs font-medium text-purple-200 uppercase tracking-wider">状态</th>
                  <th className="px-4 py-3 text-center text-xs font-medium text-purple-200 uppercase tracking-wider">Garmin</th>
                  <th className="px-4 py-3 text-center text-xs font-medium text-purple-200 uppercase tracking-wider">记录数</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-purple-200 uppercase tracking-wider">注册时间</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-purple-200 uppercase tracking-wider">最后活动</th>
                  <th className="px-4 py-3 text-center text-xs font-medium text-purple-200 uppercase tracking-wider">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/10">
                {usersLoading ? (
                  <tr>
                    <td colSpan={9} className="px-4 py-8 text-center text-purple-200">
                      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-400 mx-auto"></div>
                    </td>
                  </tr>
                ) : userList?.users.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="px-4 py-8 text-center text-purple-200">
                      暂无用户数据
                    </td>
                  </tr>
                ) : (
                  userList?.users.map((u) => (
                    <tr key={u.id} className="hover:bg-white/5 transition-colors">
                      <td className="px-4 py-3 text-purple-200 text-sm font-mono">{u.id}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center">
                          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center text-white font-semibold text-sm mr-3">
                            {u.name?.[0] || '?'}
                          </div>
                          <div>
                            <div className="text-white font-medium flex items-center gap-2">
                              {u.name}
                              {u.is_admin && (
                                <span className="px-1.5 py-0.5 bg-yellow-500/20 text-yellow-300 text-xs rounded">管理员</span>
                              )}
                              {u.is_approved && (
                                <span className="px-1.5 py-0.5 bg-gradient-to-r from-purple-500/30 to-pink-500/30 text-purple-200 text-xs rounded">VIP</span>
                              )}
                            </div>
                            <div className="text-purple-300 text-sm">@{u.username || '-'}</div>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-purple-200 text-sm">{u.email || '-'}</td>
                      <td className="px-4 py-3 text-center">
                        {u.is_active ? (
                          <span className="px-2 py-1 bg-green-500/20 text-green-300 text-xs rounded-full">活跃</span>
                        ) : (
                          <span className="px-2 py-1 bg-red-500/20 text-red-300 text-xs rounded-full">禁用</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-center">
                        {u.has_garmin ? (
                          <span className="text-green-400">✓</span>
                        ) : (
                          <span className="text-gray-500">-</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-center text-purple-200 text-sm">
                        {u.health_records_count + u.medical_exams_count}
                      </td>
                      <td className="px-4 py-3 text-purple-200 text-sm">{formatDate(u.created_at)}</td>
                      <td className="px-4 py-3 text-purple-200 text-sm">{formatDate(u.last_activity)}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center justify-center gap-1">
                          {/* 设置/取消 VIP */}
                          <button
                            onClick={() => setVipMutation.mutate({ userId: u.id, isApproved: !u.is_approved })}
                            disabled={u.id === user?.id}
                            className={`p-1.5 rounded transition-colors ${
                              u.id === user?.id
                                ? 'text-gray-500 cursor-not-allowed'
                                : u.is_approved
                                ? 'text-purple-400 hover:bg-purple-500/20'
                                : 'text-gray-400 hover:bg-white/10'
                            }`}
                            title={u.is_approved ? '取消 VIP' : '设为 VIP'}
                          >
                            💎
                          </button>

                          {/* 设置/取消管理员 */}
                          <button
                            onClick={() => setAdminMutation.mutate({ userId: u.id, isAdmin: !u.is_admin })}
                            disabled={u.id === user?.id}
                            className={`p-1.5 rounded transition-colors ${
                              u.id === user?.id
                                ? 'text-gray-500 cursor-not-allowed'
                                : u.is_admin
                                ? 'text-yellow-400 hover:bg-yellow-500/20'
                                : 'text-gray-400 hover:bg-white/10'
                            }`}
                            title={u.is_admin ? '取消管理员' : '设为管理员'}
                          >
                            👑
                          </button>
                          
                          {/* 启用/禁用 */}
                          <button
                            onClick={() => setActiveMutation.mutate({ userId: u.id, isActive: !u.is_active })}
                            disabled={u.id === user?.id}
                            className={`p-1.5 rounded transition-colors ${
                              u.id === user?.id
                                ? 'text-gray-500 cursor-not-allowed'
                                : u.is_active
                                ? 'text-green-400 hover:bg-green-500/20'
                                : 'text-red-400 hover:bg-red-500/20'
                            }`}
                            title={u.is_active ? '禁用用户' : '启用用户'}
                          >
                            {u.is_active ? '🔓' : '🔒'}
                          </button>
                          
                          {/* 清理缓存 */}
                          <button
                            onClick={() => {
                              if (confirm(`确定清理用户 ${u.name} 的缓存吗？`)) {
                                clearUserCacheMutation.mutate(u.id);
                              }
                            }}
                            disabled={clearUserCacheMutation.isPending}
                            className="p-1.5 rounded transition-colors text-orange-400 hover:bg-orange-500/20"
                            title="清理缓存"
                          >
                            🧹
                          </button>
                          
                          {/* 删除 */}
                          <button
                            onClick={() => {
                              setSelectedUser(u);
                              setShowDeleteConfirm(true);
                            }}
                            disabled={u.id === user?.id}
                            className={`p-1.5 rounded transition-colors ${
                              u.id === user?.id
                                ? 'text-gray-500 cursor-not-allowed'
                                : 'text-red-400 hover:bg-red-500/20'
                            }`}
                            title="删除用户"
                          >
                            🗑️
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* 分页 */}
          {totalPages > 1 && (
            <div className="p-4 border-t border-white/10 flex items-center justify-between">
              <div className="text-purple-200 text-sm">
                共 {userList?.total || 0} 个用户，第 {currentPage} / {totalPages} 页
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                  disabled={currentPage === 1}
                  className="px-3 py-1 bg-white/10 text-white rounded hover:bg-white/20 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  上一页
                </button>
                <button
                  onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                  disabled={currentPage === totalPages}
                  className="px-3 py-1 bg-white/10 text-white rounded hover:bg-white/20 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  下一页
                </button>
              </div>
            </div>
          )}
        </div>
          </>
        )}

        {/* Garmin 同步管理 Tab */}
        {activeTab === 'garmin' && (
          <div className="space-y-6">
            {/* 同步控制面板 */}
            <div className="bg-white/10 backdrop-blur-lg rounded-xl p-6 border border-white/20">
              <h2 className="text-xl font-bold text-white mb-4">🔄 批量同步控制</h2>
              <div className="flex flex-wrap items-center gap-4">
                <div className="flex items-center gap-2">
                  <label className="text-purple-200">同步天数:</label>
                  <select
                    value={syncDays}
                    onChange={(e) => setSyncDays(Number(e.target.value))}
                    className="px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
                  >
                    <option value={1}>1天</option>
                    <option value={3}>3天</option>
                    <option value={7}>7天</option>
                    <option value={14}>14天</option>
                    <option value={30}>30天</option>
                  </select>
                </div>
                <button
                  onClick={() => syncAllMutation.mutate(syncDays)}
                  disabled={syncAllMutation.isPending}
                  className="px-6 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                >
                  {syncAllMutation.isPending ? (
                    <>
                      <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent"></div>
                      同步中...
                    </>
                  ) : (
                    '🚀 同步所有用户'
                  )}
                </button>
                <button
                  onClick={() => refetchGarminStatus()}
                  className="px-4 py-2 bg-white/10 text-white rounded-lg hover:bg-white/20 transition-colors"
                >
                  🔄 刷新状态
                </button>
              </div>

              {/* 同步结果 */}
              {syncResult && (
                <div className="mt-4 p-4 bg-white/5 rounded-lg border border-white/10">
                  <h3 className="text-lg font-semibold text-white mb-2">同步结果</h3>
                  <div className="grid grid-cols-3 gap-4 mb-4">
                    <div className="text-center">
                      <div className="text-2xl font-bold text-white">{syncResult.total_users}</div>
                      <div className="text-purple-300 text-sm">总用户</div>
                    </div>
                    <div className="text-center">
                      <div className="text-2xl font-bold text-green-400">{syncResult.success_users}</div>
                      <div className="text-purple-300 text-sm">成功</div>
                    </div>
                    <div className="text-center">
                      <div className="text-2xl font-bold text-red-400">{syncResult.failed_users}</div>
                      <div className="text-purple-300 text-sm">失败</div>
                    </div>
                  </div>
                  {syncResult.details.length > 0 && (
                    <div className="space-y-2 max-h-40 overflow-y-auto">
                      {syncResult.details.map((detail, idx) => (
                        <div key={idx} className={`text-sm px-3 py-1 rounded ${detail.success ? 'bg-green-500/20 text-green-300' : 'bg-red-500/20 text-red-300'}`}>
                          用户 {detail.user_id}: {detail.message}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* 用户同步状态列表 */}
            <div className="bg-white/10 backdrop-blur-lg rounded-xl border border-white/20 overflow-hidden">
              <div className="p-4 border-b border-white/10">
                <h2 className="text-lg font-semibold text-white flex items-center gap-4">
                  🔄 用户同步状态
                  <span className="text-sm font-normal text-purple-200">
                    共 {garminSyncStatus?.total_configured_users || 0} 人 | 
                    <span className="text-green-400"> {garminSyncStatus?.valid_credentials || 0} 有效</span> | 
                    <span className="text-red-400"> {garminSyncStatus?.invalid_credentials || 0} 失效</span>
                  </span>
                </h2>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-white/5">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-medium text-purple-200 uppercase">ID</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-purple-200 uppercase">用户</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-purple-200 uppercase">Garmin邮箱</th>
                      <th className="px-4 py-3 text-center text-xs font-medium text-purple-200 uppercase">凭证状态</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-purple-200 uppercase">最后同步</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-purple-200 uppercase">最新数据</th>
                      <th className="px-4 py-3 text-center text-xs font-medium text-purple-200 uppercase">记录数</th>
                      <th className="px-4 py-3 text-center text-xs font-medium text-purple-200 uppercase">操作</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/10">
                    {garminStatusLoading ? (
                      <tr>
                        <td colSpan={8} className="px-4 py-8 text-center text-purple-200">
                          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-400 mx-auto"></div>
                        </td>
                      </tr>
                    ) : garminSyncStatus?.users.length === 0 ? (
                      <tr>
                        <td colSpan={8} className="px-4 py-8 text-center text-purple-200">
                          暂无配置Garmin的用户
                        </td>
                      </tr>
                    ) : (
                      garminSyncStatus?.users.map((gu) => (
                        <tr key={gu.user_id} className="hover:bg-white/5 transition-colors">
                          <td className="px-4 py-3 text-purple-200 text-sm font-mono">{gu.user_id}</td>
                          <td className="px-4 py-3">
                            <div className="flex items-center">
                              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-green-500 to-teal-500 flex items-center justify-center text-white font-semibold text-sm mr-3">
                                {gu.name?.[0] || '?'}
                              </div>
                              <div>
                                <div className="text-white font-medium">{gu.name || '-'}</div>
                                <div className="text-purple-300 text-sm">@{gu.username || '-'}</div>
                              </div>
                            </div>
                          </td>
                          <td className="px-4 py-3 text-purple-200 text-sm">{gu.garmin_email}</td>
                          <td className="px-4 py-3 text-center">
                            {gu.credentials_valid ? (
                              gu.sync_enabled ? (
                                <span className="px-2 py-1 bg-green-500/20 text-green-300 text-xs rounded-full">✓ 有效</span>
                              ) : (
                                <span className="px-2 py-1 bg-gray-500/20 text-gray-300 text-xs rounded-full">已禁用</span>
                              )
                            ) : (
                              <div className="flex flex-col items-center gap-1">
                                <span className="px-2 py-1 bg-red-500/20 text-red-300 text-xs rounded-full">✗ 失效</span>
                                {gu.last_error && (
                                  <span className="text-red-300 text-xs max-w-32 truncate" title={gu.last_error}>
                                    {gu.error_count}次错误
                                  </span>
                                )}
                              </div>
                            )}
                          </td>
                          <td className="px-4 py-3 text-purple-200 text-sm">
                            {gu.last_sync_at ? formatDate(gu.last_sync_at) : '-'}
                          </td>
                          <td className="px-4 py-3 text-purple-200 text-sm">
                            {gu.latest_data_date || '-'}
                          </td>
                          <td className="px-4 py-3 text-center text-purple-200 text-sm">{gu.total_records}</td>
                          <td className="px-4 py-3 text-center">
                            <div className="flex items-center justify-center gap-2">
                              {/* 启用/禁用同步开关 */}
                              <button
                                onClick={() => toggleSyncMutation.mutate({ userId: gu.user_id, syncEnabled: !gu.sync_enabled })}
                                disabled={toggleSyncMutation.isPending}
                                className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
                                  gu.sync_enabled ? 'bg-green-500' : 'bg-gray-500'
                                } disabled:opacity-50`}
                                title={gu.sync_enabled ? '点击禁用同步' : '点击启用同步'}
                              >
                                <span
                                  className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                                    gu.sync_enabled ? 'translate-x-4' : 'translate-x-0.5'
                                  }`}
                                />
                              </button>
                              
                              {/* 立即同步按钮 */}
                              <button
                                onClick={() => syncUserMutation.mutate({ userId: gu.user_id, days: syncDays })}
                                disabled={syncingUserId !== null || !gu.credentials_valid}
                                className="px-2 py-1 bg-blue-600/80 text-white text-xs rounded hover:bg-blue-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                                title={gu.credentials_valid ? "立即同步数据" : "凭证失效，无法同步"}
                              >
                                {syncingUserId === gu.user_id ? '同步中...' : '同步'}
                              </button>
                              
                              {/* 重置凭证按钮 */}
                              {!gu.credentials_valid && (
                                <button
                                  onClick={() => resetCredentialsMutation.mutate(gu.user_id)}
                                  disabled={resetCredentialsMutation.isPending}
                                  className="px-2 py-1 bg-yellow-600/80 text-white text-xs rounded hover:bg-yellow-600 transition-colors disabled:opacity-50"
                                  title="重置凭证状态"
                                >
                                  重置
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* 邀请码管理 Tab */}
        {activeTab === 'invitation' && (
          <div className="space-y-6">
            {/* 统计卡片 */}
            {invitationStats && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="bg-white/10 backdrop-blur-lg rounded-xl p-4 border border-white/20">
                  <div className="text-3xl font-bold text-yellow-400">{invitationStats.applications.pending}</div>
                  <div className="text-purple-200 text-sm">待审批申请</div>
                </div>
                <div className="bg-white/10 backdrop-blur-lg rounded-xl p-4 border border-white/20">
                  <div className="text-3xl font-bold text-green-400">{invitationStats.applications.approved}</div>
                  <div className="text-purple-200 text-sm">已通过</div>
                </div>
                <div className="bg-white/10 backdrop-blur-lg rounded-xl p-4 border border-white/20">
                  <div className="text-3xl font-bold text-purple-400">{invitationStats.invitation_codes.active}</div>
                  <div className="text-purple-200 text-sm">有效邀请码</div>
                </div>
                <div className="bg-white/10 backdrop-blur-lg rounded-xl p-4 border border-white/20">
                  <div className="text-3xl font-bold text-blue-400">{invitationStats.invitation_codes.total_uses}</div>
                  <div className="text-purple-200 text-sm">总使用次数</div>
                </div>
              </div>
            )}

            {/* 邀请码列表 */}
            <div className="bg-white/10 backdrop-blur-lg rounded-xl border border-white/20 overflow-hidden">
              <div className="p-4 border-b border-white/10 flex items-center justify-between">
                <h2 className="text-lg font-semibold text-white">🎫 邀请码列表</h2>
                <button
                  onClick={() => setShowCreateCode(true)}
                  className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors text-sm"
                >
                  + 创建邀请码
                </button>
              </div>

              {invitationLoading ? (
                <div className="p-8 text-center">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-400 mx-auto"></div>
                </div>
              ) : invitationCodes.length === 0 ? (
                <div className="p-8 text-center text-purple-200">暂无邀请码</div>
              ) : (
                <div className="divide-y divide-white/10">
                  {invitationCodes.map((code) => (
                    <div key={code.id} className="p-4 hover:bg-white/5 transition-colors">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-4">
                          <code className="px-3 py-1.5 bg-purple-500/20 text-purple-300 rounded font-mono text-lg">
                            {code.code}
                          </code>
                          <span className={`px-2 py-1 rounded text-xs ${
                            code.is_valid
                              ? 'bg-green-500/20 text-green-400'
                              : 'bg-red-500/20 text-red-400'
                          }`}>
                            {code.is_valid ? '有效' : '已失效'}
                          </span>
                          <span className="text-purple-200 text-sm">
                            {code.used_count}/{code.max_uses} 次
                          </span>
                          {code.note && (
                            <span className="text-gray-400 text-sm">({code.note})</span>
                          )}
                        </div>
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => copyToClipboard(code.code)}
                            className="px-3 py-1 bg-white/10 text-white rounded hover:bg-white/20 transition-colors text-sm"
                          >
                            复制
                          </button>
                          {code.is_active && (
                            <button
                              onClick={() => handleDisableCode(code.id)}
                              className="px-3 py-1 bg-red-500/20 text-red-400 rounded hover:bg-red-500/30 transition-colors text-sm"
                            >
                              禁用
                            </button>
                          )}
                        </div>
                      </div>
                      <div className="mt-2 text-gray-400 text-xs">
                        创建于 {formatDate(code.created_at)}
                        {code.creator_name && ` · 创建者: ${code.creator_name}`}
                        {code.expires_at && ` · 过期时间: ${formatDate(code.expires_at)}`}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* 用户申请列表 */}
            <div className="bg-white/10 backdrop-blur-lg rounded-xl border border-white/20 overflow-hidden">
              <div className="p-4 border-b border-white/10">
                <h2 className="text-lg font-semibold text-white mb-4">📝 用户申请</h2>
                <div className="flex items-center gap-2">
                  {['pending', 'approved', 'rejected', ''].map((status) => (
                    <button
                      key={status || 'all'}
                      onClick={() => setStatusFilter(status)}
                      className={`px-3 py-1 rounded text-sm ${
                        statusFilter === status
                          ? 'bg-purple-500 text-white'
                          : 'bg-white/10 text-gray-300 hover:bg-white/20'
                      }`}
                    >
                      {status === 'pending' ? '待审批' : 
                       status === 'approved' ? '已通过' : 
                       status === 'rejected' ? '已拒绝' : '全部'}
                    </button>
                  ))}
                </div>
              </div>

              {invitationLoading ? (
                <div className="p-8 text-center">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-400 mx-auto"></div>
                </div>
              ) : applications.length === 0 ? (
                <div className="p-8 text-center text-purple-200">暂无申请记录</div>
              ) : (
                <div className="divide-y divide-white/10">
                  {applications.map((app) => (
                    <div
                      key={app.id}
                      className="p-4 hover:bg-white/5 cursor-pointer transition-colors"
                      onClick={() => setSelectedApp(app)}
                    >
                      <div className="flex items-center justify-between">
                        <div>
                          <div className="flex items-center gap-3">
                            <span className="text-white font-medium">{app.name}</span>
                            <span className={`px-2 py-0.5 rounded text-xs ${
                              app.status === 'pending' ? 'bg-yellow-500/20 text-yellow-400' :
                              app.status === 'approved' ? 'bg-green-500/20 text-green-400' :
                              'bg-red-500/20 text-red-400'
                            }`}>
                              {app.status === 'pending' ? '待审批' :
                               app.status === 'approved' ? '已通过' : '已拒绝'}
                            </span>
                          </div>
                          <div className="text-gray-400 text-sm mt-1">
                            {app.email} · 申请时间：{formatDate(app.created_at)}
                          </div>
                        </div>
                        <span className="text-gray-500">→</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* API Key 管理 Tab */}
        {activeTab === 'apikeys' && (
          <div className="space-y-6">
            {/* 创建 API Key */}
            <div className="bg-white/10 backdrop-blur-lg rounded-xl p-6 border border-white/20">
              <h2 className="text-xl font-bold text-white mb-4">🔑 创建 API Key</h2>
              <p className="text-purple-200 text-sm mb-4">
                API Key 用于外部系统（如 browser-llm-orchestrator）向资讯系统写入内容。
              </p>
              <div className="flex gap-4">
                <input
                  type="text"
                  value={newApiKeyName}
                  onChange={(e) => setNewApiKeyName(e.target.value)}
                  placeholder="输入 API Key 名称，如：browser-llm-orchestrator"
                  className="flex-1 px-4 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-purple-300 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
                <button
                  onClick={handleCreateApiKey}
                  className="px-6 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors"
                >
                  创建
                </button>
              </div>

              {/* 新创建的 API Key 显示 */}
              {newApiKey && (
                <div className="mt-4 p-4 bg-green-500/20 border border-green-500/30 rounded-lg">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-green-400 font-medium mb-1">API Key 创建成功！</p>
                      <p className="text-green-200 text-xs mb-2">请立即复制保存，此密钥只显示一次。</p>
                      <code className="block p-2 bg-black/30 rounded text-green-300 font-mono text-sm break-all">
                        {newApiKey}
                      </code>
                    </div>
                    <button
                      onClick={() => {
                        copyToClipboard(newApiKey);
                        setNewApiKey(null);
                      }}
                      className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors ml-4"
                    >
                      复制并关闭
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* API Key 列表 */}
            <div className="bg-white/10 backdrop-blur-lg rounded-xl border border-white/20 overflow-hidden">
              <div className="p-4 border-b border-white/10">
                <h2 className="text-lg font-semibold text-white">📋 API Key 列表</h2>
              </div>

              {apiKeysLoading ? (
                <div className="p-8 text-center">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-400 mx-auto"></div>
                </div>
              ) : apiKeys.length === 0 ? (
                <div className="p-8 text-center text-purple-200">
                  <p>暂无 API Key</p>
                  <p className="text-sm text-gray-400 mt-2">点击上方按钮创建一个新的 API Key</p>
                </div>
              ) : (
                <div className="divide-y divide-white/10">
                  {apiKeys.map((key) => (
                    <div key={key.id} className="p-4 hover:bg-white/5 transition-colors">
                      <div className="flex items-center justify-between">
                        <div>
                          <div className="flex items-center gap-3">
                            <span className="text-white font-medium">{key.name}</span>
                            <span className={`px-2 py-1 rounded text-xs ${
                              key.is_active
                                ? 'bg-green-500/20 text-green-400'
                                : 'bg-red-500/20 text-red-400'
                            }`}>
                              {key.is_active ? '有效' : '已禁用'}
                            </span>
                          </div>
                          <div className="text-gray-400 text-sm mt-1">
                            创建于 {formatDate(key.created_at)}
                            {key.last_used_at && ` · 最后使用: ${formatDate(key.last_used_at)}`}
                          </div>
                        </div>
                        <button
                          onClick={() => handleDeleteApiKey(key.id)}
                          className="px-3 py-1 bg-red-500/20 text-red-400 rounded hover:bg-red-500/30 transition-colors text-sm"
                        >
                          删除
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* 使用说明 */}
            <div className="bg-white/5 backdrop-blur rounded-xl p-4 border border-white/10">
              <h3 className="text-purple-200 font-medium mb-2">📚 使用说明</h3>
              <div className="text-gray-400 text-sm space-y-2">
                <p>在请求头中添加 <code className="px-1 py-0.5 bg-white/10 rounded text-purple-300">X-API-Key</code> 字段：</p>
                <code className="block p-2 bg-black/30 rounded text-green-300 font-mono text-xs">
                  curl -X POST /api/news/external/articles -H &quot;X-API-Key: your-api-key&quot; -d &apos;...&apos;
                </code>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* 删除用户确认弹窗 */}
      {showDeleteConfirm && selectedUser && (
        <div 
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
          onClick={(e) => {
            if (e.target === e.currentTarget) {
              setShowDeleteConfirm(false);
              setSelectedUser(null);
            }
          }}
        >
          <div 
            className="bg-slate-800 rounded-xl p-6 max-w-md w-full mx-4 border border-white/20"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-xl font-bold text-white mb-4">确认删除</h3>
            <p className="text-purple-200 mb-6">
              确定要删除用户 <span className="text-white font-semibold">{selectedUser.name}</span> 吗？
              <br />
              <span className="text-red-400 text-sm">此操作将删除该用户的所有数据，且无法恢复。</span>
            </p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  setShowDeleteConfirm(false);
                  setSelectedUser(null);
                }}
                disabled={deleteUserMutation.isPending}
                className="px-4 py-2 bg-white/10 text-white rounded-lg hover:bg-white/20 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                取消
              </button>
              <button
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  if (selectedUser && selectedUser.id) {
                    deleteUserMutation.mutate(selectedUser.id);
                  }
                }}
                disabled={deleteUserMutation.isPending || !selectedUser}
                className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {deleteUserMutation.isPending ? '删除中...' : '确认删除'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 创建邀请码弹窗 */}
      {showCreateCode && (
        <div 
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
          onClick={(e) => {
            if (e.target === e.currentTarget) {
              setShowCreateCode(false);
            }
          }}
        >
          <div 
            className="bg-slate-800 rounded-xl p-6 max-w-md w-full mx-4 border border-white/20"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-xl font-bold text-white mb-4">创建邀请码</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-purple-200 text-sm mb-2">备注（可选）</label>
                <input
                  type="text"
                  value={newCodeNote}
                  onChange={(e) => setNewCodeNote(e.target.value)}
                  placeholder="例如：给朋友的邀请码"
                  className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-purple-300 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>
              <div>
                <label className="block text-purple-200 text-sm mb-2">最大使用次数</label>
                <input
                  type="number"
                  value={newCodeMaxUses}
                  onChange={(e) => setNewCodeMaxUses(Number(e.target.value))}
                  min={1}
                  max={100}
                  className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>
              <div>
                <label className="block text-purple-200 text-sm mb-2">过期天数（可选）</label>
                <input
                  type="number"
                  value={newCodeExpiresDays || ''}
                  onChange={(e) => setNewCodeExpiresDays(e.target.value ? Number(e.target.value) : null)}
                  placeholder="留空表示永不过期"
                  min={1}
                  className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-purple-300 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>
            </div>
            <div className="flex gap-3 justify-end mt-6">
              <button
                onClick={() => setShowCreateCode(false)}
                className="px-4 py-2 bg-white/10 text-white rounded-lg hover:bg-white/20 transition-colors"
              >
                取消
              </button>
              <button
                onClick={handleCreateCode}
                className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors"
              >
                创建
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 审批申请弹窗 */}
      {selectedApp && (
        <div 
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
          onClick={(e) => {
            if (e.target === e.currentTarget) {
              setSelectedApp(null);
              setReviewNote('');
            }
          }}
        >
          <div 
            className="bg-slate-800 rounded-xl p-6 max-w-lg w-full mx-4 border border-white/20 max-h-[90vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-xl font-bold text-white mb-4">申请详情</h3>
            
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <span className="text-gray-400 text-sm">姓名</span>
                  <p className="text-white">{selectedApp.name}</p>
                </div>
                <div>
                  <span className="text-gray-400 text-sm">邮箱</span>
                  <p className="text-white">{selectedApp.email}</p>
                </div>
                {selectedApp.phone && (
                  <div>
                    <span className="text-gray-400 text-sm">手机</span>
                    <p className="text-white">{selectedApp.phone}</p>
                  </div>
                )}
                <div>
                  <span className="text-gray-400 text-sm">状态</span>
                  <p className={`${
                    selectedApp.status === 'pending' ? 'text-yellow-400' :
                    selectedApp.status === 'approved' ? 'text-green-400' : 'text-red-400'
                  }`}>
                    {selectedApp.status === 'pending' ? '待审批' :
                     selectedApp.status === 'approved' ? '已通过' : '已拒绝'}
                  </p>
                </div>
              </div>

              {selectedApp.health_questionnaire && (
                <div className="bg-white/5 rounded-lg p-4">
                  <h4 className="text-purple-200 font-medium mb-3">健康问卷</h4>
                  <div className="grid grid-cols-2 gap-3 text-sm">
                    {selectedApp.health_questionnaire.age && (
                      <div>
                        <span className="text-gray-400">年龄</span>
                        <p className="text-white">{selectedApp.health_questionnaire.age}岁</p>
                      </div>
                    )}
                    {selectedApp.health_questionnaire.gender && (
                      <div>
                        <span className="text-gray-400">性别</span>
                        <p className="text-white">{selectedApp.health_questionnaire.gender}</p>
                      </div>
                    )}
                    {selectedApp.health_questionnaire.height_cm && (
                      <div>
                        <span className="text-gray-400">身高</span>
                        <p className="text-white">{selectedApp.health_questionnaire.height_cm}cm</p>
                      </div>
                    )}
                    {selectedApp.health_questionnaire.weight_kg && (
                      <div>
                        <span className="text-gray-400">体重</span>
                        <p className="text-white">{selectedApp.health_questionnaire.weight_kg}kg</p>
                      </div>
                    )}
                    {selectedApp.health_questionnaire.exercise_frequency && (
                      <div className="col-span-2">
                        <span className="text-gray-400">运动频率</span>
                        <p className="text-white">{selectedApp.health_questionnaire.exercise_frequency}</p>
                      </div>
                    )}
                    {selectedApp.health_questionnaire.health_goals && selectedApp.health_questionnaire.health_goals.length > 0 && (
                      <div className="col-span-2">
                        <span className="text-gray-400">健康目标</span>
                        <p className="text-white">{selectedApp.health_questionnaire.health_goals.join(', ')}</p>
                      </div>
                    )}
                    {selectedApp.health_questionnaire.wearable_devices && selectedApp.health_questionnaire.wearable_devices.length > 0 && (
                      <div className="col-span-2">
                        <span className="text-gray-400">穿戴设备</span>
                        <p className="text-white">{selectedApp.health_questionnaire.wearable_devices.join(', ')}</p>
                      </div>
                    )}
                    {selectedApp.health_questionnaire.why_join && (
                      <div className="col-span-2">
                        <span className="text-gray-400">加入原因</span>
                        <p className="text-white">{selectedApp.health_questionnaire.why_join}</p>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {selectedApp.status === 'pending' && (
                <div>
                  <label className="block text-purple-200 text-sm mb-2">审批备注（可选）</label>
                  <textarea
                    value={reviewNote}
                    onChange={(e) => setReviewNote(e.target.value)}
                    placeholder="输入审批备注..."
                    rows={3}
                    className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-purple-300 focus:outline-none focus:ring-2 focus:ring-purple-500 resize-none"
                  />
                </div>
              )}

              {selectedApp.review_note && (
                <div className="bg-white/5 rounded-lg p-3">
                  <span className="text-gray-400 text-sm">审批备注</span>
                  <p className="text-white">{selectedApp.review_note}</p>
                  {selectedApp.reviewer_name && (
                    <p className="text-gray-400 text-xs mt-1">
                      审批人: {selectedApp.reviewer_name} · {formatDate(selectedApp.reviewed_at)}
                    </p>
                  )}
                </div>
              )}
            </div>

            <div className="flex gap-3 justify-end mt-6">
              <button
                onClick={() => {
                  setSelectedApp(null);
                  setReviewNote('');
                }}
                className="px-4 py-2 bg-white/10 text-white rounded-lg hover:bg-white/20 transition-colors"
              >
                关闭
              </button>
              {selectedApp.status === 'pending' && (
                <>
                  <button
                    onClick={() => handleReview(false)}
                    className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
                  >
                    拒绝
                  </button>
                  <button
                    onClick={() => handleReview(true)}
                    className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors"
                  >
                    通过
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
