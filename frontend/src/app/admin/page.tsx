'use client';

import { useState, useEffect } from 'react';
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
  created_at: string | null;
  last_activity: string | null;
  has_garmin: boolean;
  health_records_count: number;
  medical_exams_count: number;
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

export default function AdminPage() {
  const router = useRouter();
  const { user, isAuthenticated, isLoading: authLoading } = useAuth();
  const queryClient = useQueryClient();
  
  const [activeTab, setActiveTab] = useState<'users' | 'garmin'>('users');
  const [searchTerm, setSearchTerm] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [selectedUser, setSelectedUser] = useState<AdminUser | null>(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [syncDays, setSyncDays] = useState(3);
  const [syncResult, setSyncResult] = useState<SyncResult | null>(null);
  const [syncingUserId, setSyncingUserId] = useState<number | null>(null); // 追踪当前正在同步的用户
  const pageSize = 15;

  // 权限检查
  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login');
    } else if (!authLoading && isAuthenticated && !user?.is_admin) {
      router.push('/');
    }
  }, [authLoading, isAuthenticated, user, router]);

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
      // 即使失败也关闭对话框
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
      setSyncingUserId(userId); // 开始同步时设置正在同步的用户ID
      const res = await api.post(`/admin/garmin/sync-user/${userId}?days=${days}`);
      return res.data;
    },
    onSuccess: () => {
      setSyncingUserId(null); // 成功后清除
      queryClient.invalidateQueries({ queryKey: ['admin-garmin-sync-status'] });
    },
    onError: () => {
      setSyncingUserId(null); // 失败后也清除
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
    <main className="min-h-screen p-8 bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 pt-24">
      <div className="max-w-7xl mx-auto">
        {/* 页面标题 */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-white mb-2">🛡️ 管理后台</h1>
          <p className="text-purple-200">管理用户和查看系统统计</p>
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
                  📊 用户同步状态
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
      </div>

      {/* 删除确认弹窗 */}
      {showDeleteConfirm && selectedUser && (
        <div 
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
          onClick={(e) => {
            // 点击背景关闭对话框
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
                  console.log('确认删除按钮被点击，用户ID:', selectedUser.id);
                  if (selectedUser && selectedUser.id) {
                    deleteUserMutation.mutate(selectedUser.id);
                  } else {
                    console.error('selectedUser 或 selectedUser.id 为空');
                    alert('错误：无法获取用户ID');
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
    </main>
  );
}

