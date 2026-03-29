'use client';

import { UseMutationResult } from '@tanstack/react-query';

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

interface ClearCacheResult {
  message: string;
  deleted_count: number;
}

interface UserManagementTabProps {
  stats: AdminStats | undefined;
  statsLoading: boolean;
  userList: UserListResponse | undefined;
  usersLoading: boolean;
  currentPage: number;
  setCurrentPage: (fn: (p: number) => number) => void;
  searchTerm: string;
  setSearchTerm: (v: string) => void;
  handleSearch: (e: React.FormEvent) => void;
  setShowCreateUser: (v: boolean) => void;
  currentUserId: number | undefined;
  setVipMutation: UseMutationResult<any, any, { userId: number; isApproved: boolean }>;
  setAdminMutation: UseMutationResult<any, any, { userId: number; isAdmin: boolean }>;
  setActiveMutation: UseMutationResult<any, any, { userId: number; isActive: boolean }>;
  clearUserCacheMutation: UseMutationResult<ClearCacheResult, any, number>;
  clearNoDataCacheMutation: UseMutationResult<ClearCacheResult, any, void>;
  clearAllCacheMutation: UseMutationResult<ClearCacheResult, any, void>;
  setSelectedUser: (u: AdminUser) => void;
  setShowResetPassword: (v: boolean) => void;
  setShowDeleteConfirm: (v: boolean) => void;
  formatDate: (dateStr: string | null) => string;
  pageSize: number;
}

export default function UserManagementTab({
  stats,
  statsLoading,
  userList,
  usersLoading,
  currentPage,
  setCurrentPage,
  searchTerm,
  setSearchTerm,
  handleSearch,
  setShowCreateUser,
  currentUserId,
  setVipMutation,
  setAdminMutation,
  setActiveMutation,
  clearUserCacheMutation,
  clearNoDataCacheMutation,
  clearAllCacheMutation,
  setSelectedUser,
  setShowResetPassword,
  setShowDeleteConfirm,
  formatDate,
  pageSize,
}: UserManagementTabProps) {
  const totalPages = userList ? Math.ceil(userList.total / pageSize) : 0;

  return (
    <>
      {/* Cache Management */}
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

      {/* Stats Cards */}
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

      {/* More Stats */}
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

      {/* Search and User List */}
      <div className="bg-white/10 backdrop-blur-lg rounded-xl border border-white/20 overflow-hidden">
        {/* Search Bar */}
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
            <button
              type="button"
              onClick={() => setShowCreateUser(true)}
              className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors whitespace-nowrap"
            >
              + 创建用户
            </button>
          </form>
        </div>

        {/* User Table */}
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
                        {/* VIP */}
                        <button
                          onClick={() => setVipMutation.mutate({ userId: u.id, isApproved: !u.is_approved })}
                          disabled={u.id === currentUserId}
                          className={`p-1.5 rounded transition-colors ${
                            u.id === currentUserId
                              ? 'text-gray-500 cursor-not-allowed'
                              : u.is_approved
                              ? 'text-purple-400 hover:bg-purple-500/20'
                              : 'text-gray-400 hover:bg-white/10'
                          }`}
                          title={u.is_approved ? '取消 VIP' : '设为 VIP'}
                        >
                          💎
                        </button>

                        {/* Admin */}
                        <button
                          onClick={() => setAdminMutation.mutate({ userId: u.id, isAdmin: !u.is_admin })}
                          disabled={u.id === currentUserId}
                          className={`p-1.5 rounded transition-colors ${
                            u.id === currentUserId
                              ? 'text-gray-500 cursor-not-allowed'
                              : u.is_admin
                              ? 'text-yellow-400 hover:bg-yellow-500/20'
                              : 'text-gray-400 hover:bg-white/10'
                          }`}
                          title={u.is_admin ? '取消管理员' : '设为管理员'}
                        >
                          👑
                        </button>

                        {/* Active/Inactive */}
                        <button
                          onClick={() => setActiveMutation.mutate({ userId: u.id, isActive: !u.is_active })}
                          disabled={u.id === currentUserId}
                          className={`p-1.5 rounded transition-colors ${
                            u.id === currentUserId
                              ? 'text-gray-500 cursor-not-allowed'
                              : u.is_active
                              ? 'text-green-400 hover:bg-green-500/20'
                              : 'text-red-400 hover:bg-red-500/20'
                          }`}
                          title={u.is_active ? '禁用用户' : '启用用户'}
                        >
                          {u.is_active ? '🔓' : '🔒'}
                        </button>

                        {/* Clear Cache */}
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

                        {/* Reset Password */}
                        <button
                          onClick={() => {
                            setSelectedUser(u);
                            setShowResetPassword(true);
                          }}
                          className="p-1.5 rounded transition-colors text-blue-400 hover:bg-blue-500/20"
                          title="重置密码"
                        >
                          🔑
                        </button>

                        {/* Delete */}
                        <button
                          onClick={() => {
                            setSelectedUser(u);
                            setShowDeleteConfirm(true);
                          }}
                          disabled={u.id === currentUserId}
                          className={`p-1.5 rounded transition-colors ${
                            u.id === currentUserId
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

        {/* Pagination */}
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
  );
}
