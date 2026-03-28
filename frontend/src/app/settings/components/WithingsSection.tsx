'use client';

import { useQuery, useMutation, QueryClient } from '@tanstack/react-query';
import { withingsApi, deviceApi } from '@/services/api';
import { formatDateTime } from '@/utils/timezone';
import { extractErrorMsg } from './GarminSection';

interface WithingsSectionProps {
  token: string | null;
  setMessage: (msg: { type: 'success' | 'error'; text: string } | null) => void;
  queryClient: QueryClient;
}

export default function WithingsSection({ token, setMessage, queryClient }: WithingsSectionProps) {
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

  return (
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
  );
}
