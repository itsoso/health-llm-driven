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
  last_sync_at: string | null;
  latest_data_date: string | null;
  total_records: number;
}

interface GarminSyncStatus {
  total_configured_users: number;
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
    onSuccess: () => {
      setShowDeleteConfirm(false);
      setSelectedUser(null);
      queryClient.invalidateQueries({ queryKey: ['admin-users'] });
      queryClient.invalidateQueries({ queryKey: ['admin-stats'] });
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
      const res = await api.post(`/admin/garmin/sync-user/${userId}?days=${days}`);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-garmin-sync-status'] });
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
                    <td colSpan={8} className="px-4 py-8 text-center text-purple-200">
                      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-400 mx-auto"></div>
                    </td>
                  </tr>
                ) : userList?.users.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="px-4 py-8 text-center text-purple-200">
                      暂无用户数据
                    </td>
                  </tr>
                ) : (
                  userList?.users.map((u) => (
                    <tr key={u.id} className="hover:bg-white/5 transition-colors">
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
                <h2 className="text-lg font-semibold text-white">
                  📊 用户同步状态 ({garminSyncStatus?.total_configured_users || 0} 人已配置)
                </h2>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-white/5">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-medium text-purple-200 uppercase">用户</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-purple-200 uppercase">Garmin邮箱</th>
                      <th className="px-4 py-3 text-center text-xs font-medium text-purple-200 uppercase">状态</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-purple-200 uppercase">最后同步</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-purple-200 uppercase">最新数据</th>
                      <th className="px-4 py-3 text-center text-xs font-medium text-purple-200 uppercase">记录数</th>
                      <th className="px-4 py-3 text-center text-xs font-medium text-purple-200 uppercase">操作</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/10">
                    {garminStatusLoading ? (
                      <tr>
                        <td colSpan={7} className="px-4 py-8 text-center text-purple-200">
                          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-400 mx-auto"></div>
                        </td>
                      </tr>
                    ) : garminSyncStatus?.users.length === 0 ? (
                      <tr>
                        <td colSpan={7} className="px-4 py-8 text-center text-purple-200">
                          暂无配置Garmin的用户
                        </td>
                      </tr>
                    ) : (
                      garminSyncStatus?.users.map((gu) => (
                        <tr key={gu.user_id} className="hover:bg-white/5 transition-colors">
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
                            {gu.sync_enabled ? (
                              <span className="px-2 py-1 bg-green-500/20 text-green-300 text-xs rounded-full">已启用</span>
                            ) : (
                              <span className="px-2 py-1 bg-gray-500/20 text-gray-300 text-xs rounded-full">已禁用</span>
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
                            <button
                              onClick={() => syncUserMutation.mutate({ userId: gu.user_id, days: syncDays })}
                              disabled={syncUserMutation.isPending}
                              className="px-3 py-1 bg-blue-600/80 text-white text-sm rounded hover:bg-blue-600 transition-colors disabled:opacity-50"
                            >
                              {syncUserMutation.isPending ? '...' : '同步'}
                            </button>
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
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-slate-800 rounded-xl p-6 max-w-md w-full mx-4 border border-white/20">
            <h3 className="text-xl font-bold text-white mb-4">确认删除</h3>
            <p className="text-purple-200 mb-6">
              确定要删除用户 <span className="text-white font-semibold">{selectedUser.name}</span> 吗？
              <br />
              <span className="text-red-400 text-sm">此操作将删除该用户的所有数据，且无法恢复。</span>
            </p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => {
                  setShowDeleteConfirm(false);
                  setSelectedUser(null);
                }}
                className="px-4 py-2 bg-white/10 text-white rounded-lg hover:bg-white/20 transition-colors"
              >
                取消
              </button>
              <button
                onClick={() => deleteUserMutation.mutate(selectedUser.id)}
                disabled={deleteUserMutation.isPending}
                className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors disabled:opacity-50"
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

