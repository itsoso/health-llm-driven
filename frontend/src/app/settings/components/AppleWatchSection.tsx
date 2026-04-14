'use client';

import { useState } from 'react';
import { useQuery, useMutation, QueryClient } from '@tanstack/react-query';
import { deviceApi } from '@/services/api/devices';
import { formatDateTime } from '@/utils/timezone';
import { extractErrorMsg } from './GarminSection';

interface AppleWatchSectionProps {
  token: string | null;
  setMessage: (msg: { type: 'success' | 'error'; text: string } | null) => void;
  queryClient: QueryClient;
}

export default function AppleWatchSection({ token, setMessage, queryClient }: AppleWatchSectionProps) {
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

  return (
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
  );
}
