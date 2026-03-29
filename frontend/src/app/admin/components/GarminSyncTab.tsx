'use client';

import { UseMutationResult } from '@tanstack/react-query';

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

interface GarminSyncTabProps {
  garminSyncStatus: GarminSyncStatus | undefined;
  garminStatusLoading: boolean;
  refetchGarminStatus: () => void;
  syncDays: number;
  setSyncDays: (v: number) => void;
  syncResult: SyncResult | null;
  syncingUserId: number | null;
  syncAllMutation: UseMutationResult<any, any, number>;
  syncUserMutation: UseMutationResult<any, any, { userId: number; days: number }>;
  resetCredentialsMutation: UseMutationResult<any, any, number>;
  toggleSyncMutation: UseMutationResult<any, any, { userId: number; syncEnabled: boolean }>;
  formatDate: (dateStr: string | null) => string;
}

export default function GarminSyncTab({
  garminSyncStatus,
  garminStatusLoading,
  refetchGarminStatus,
  syncDays,
  setSyncDays,
  syncResult,
  syncingUserId,
  syncAllMutation,
  syncUserMutation,
  resetCredentialsMutation,
  toggleSyncMutation,
  formatDate,
}: GarminSyncTabProps) {
  return (
    <div className="space-y-6">
      {/* Sync Control Panel */}
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

        {/* Sync Result */}
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

      {/* User Sync Status List */}
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
                        {/* Toggle Sync */}
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

                        {/* Sync Now */}
                        <button
                          onClick={() => syncUserMutation.mutate({ userId: gu.user_id, days: syncDays })}
                          disabled={syncingUserId !== null || !gu.credentials_valid}
                          className="px-2 py-1 bg-blue-600/80 text-white text-xs rounded hover:bg-blue-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                          title={gu.credentials_valid ? "立即同步数据" : "凭证失效，无法同步"}
                        >
                          {syncingUserId === gu.user_id ? '同步中...' : '同步'}
                        </button>

                        {/* Reset Credentials */}
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
  );
}
