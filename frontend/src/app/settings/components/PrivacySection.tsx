'use client';

import { useState, useEffect } from 'react';
import { useQuery, useMutation, QueryClient } from '@tanstack/react-query';
import { formatDateTime } from '@/utils/timezone';
import { manageAiConsent } from '@/services/aiConsent';

const API_BASE = '/api';

interface PrivacySettings {
  weight: boolean;
  height: boolean;
  age: boolean;
  gender: boolean;
  city: boolean;
  location: boolean;
}

interface DetectedLocation {
  city: string | null;
  region: string | null;
  country: string | null;
}

interface ManualLocation {
  city: string | null;
  region: string | null;
  country: string | null;
}

interface UserProfile {
  privacy_settings: PrivacySettings;
  detected_location: DetectedLocation | null;
  manual_location: ManualLocation | null;
  use_manual_location: boolean;
  location_updated_at: string | null;
  city: string | null;
}

interface PrivacySectionProps {
  token: string | null;
  setMessage: (msg: { type: 'success' | 'error'; text: string } | null) => void;
  queryClient: QueryClient;
}

export default function PrivacySection({ token, setMessage, queryClient }: PrivacySectionProps) {
  const [showPrivacySection, setShowPrivacySection] = useState(false);
  const [manualLocationForm, setManualLocationForm] = useState({
    city: '',
    region: '',
    country: '中国',
  });

  // 获取用户画像（隐私设置）
  const { data: userProfile, isLoading: profileLoading } = useQuery({
    queryKey: ['user-profile'],
    queryFn: async () => {
      if (!token) return null;
      const res = await fetch(`${API_BASE}/profile/me`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (!res.ok) throw new Error('获取用户画像失败');
      return res.json() as Promise<UserProfile>;
    },
    enabled: !!token,
  });

  // 当用户画像加载完成时，初始化手工位置表单
  useEffect(() => {
    if (userProfile?.manual_location) {
      setManualLocationForm({
        city: userProfile.manual_location.city || '',
        region: userProfile.manual_location.region || '',
        country: userProfile.manual_location.country || '中国',
      });
    }
  }, [userProfile]);

  // 更新用户画像（隐私设置）
  const updateProfileMutation = useMutation({
    mutationFn: async (data: { privacy_settings: PrivacySettings }) => {
      const res = await fetch(`${API_BASE}/profile/me`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify(data),
      });
      if (!res.ok) throw new Error('更新失败');
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['user-profile'] });
      setMessage({ type: 'success', text: '隐私设置已更新' });
    },
    onError: (error: Error) => {
      setMessage({ type: 'error', text: error.message });
    },
  });

  // 刷新位置
  const refreshLocationMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch(`${API_BASE}/profile/me/refresh-location`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (!res.ok) throw new Error('刷新位置失败');
      return res.json();
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['user-profile'] });
      if (data.success) {
        setMessage({ type: 'success', text: `位置已更新: ${data.location?.city || '未知'}` });
      } else {
        setMessage({ type: 'error', text: data.message || '无法获取位置' });
      }
    },
    onError: (error: Error) => {
      setMessage({ type: 'error', text: error.message });
    },
  });

  // 更新手工位置
  const updateManualLocationMutation = useMutation({
    mutationFn: async (data: { use_manual_location: boolean; city?: string; region?: string; country?: string }) => {
      const res = await fetch(`${API_BASE}/profile/me/manual-location`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify(data),
      });
      if (!res.ok) throw new Error('更新失败');
      return res.json();
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['user-profile'] });
      if (data.success) {
        setMessage({ type: 'success', text: data.use_manual_location ? '已切换为手工输入位置' : '已切换为IP自动定位' });
      }
    },
    onError: (error: Error) => {
      setMessage({ type: 'error', text: error.message });
    },
  });

  return (
    <div className="bg-white rounded-xl shadow-lg p-6 mb-6 border border-gray-100">
      <div className="mb-5 border-b border-gray-100 pb-5">
        <h2 className="text-lg font-semibold text-gray-900">第三方 AI 数据使用</h2>
        <p className="mt-2 text-sm text-gray-600">查看 AI 服务接收方、数据范围，或撤回授权。与下方 API 公开字段设置相互独立。</p>
        <button type="button" onClick={() => void manageAiConsent().catch(error => setMessage({ type: 'error', text: error instanceof Error ? error.message : '无法加载授权说明，请重试。' }))}
          className="mt-3 min-h-11 rounded-lg border border-green-700 px-4 text-sm font-medium text-green-800">查看与管理 AI 授权</button>
      </div>
      <div
        className="flex items-center justify-between cursor-pointer"
        onClick={() => setShowPrivacySection(!showPrivacySection)}
      >
        <h2 className="text-xl font-bold text-gray-900 flex items-center gap-2">
          🔒 数据隐私设置
        </h2>
        <span className="text-gray-400 text-2xl">
          {showPrivacySection ? '▼' : '›'}
        </span>
      </div>

      {showPrivacySection && (
        <div className="mt-4 space-y-4">
          <p className="text-gray-600 text-sm">
            控制哪些个人信息可以通过 API 对外公开（用于外部 AI 健康助手）
          </p>

          {profileLoading ? (
            <div className="text-center py-4 text-gray-500">加载中...</div>
          ) : userProfile ? (
            <>
              {/* 隐私开关 */}
              <div className="bg-gray-50 rounded-lg p-4 border border-gray-200 space-y-3">
                <h3 className="font-semibold text-gray-800 mb-2">公开字段设置</h3>

                {[
                  { key: 'weight', label: '体重', icon: '⚖️' },
                  { key: 'height', label: '身高', icon: '📏' },
                  { key: 'age', label: '年龄', icon: '🎂' },
                  { key: 'gender', label: '性别', icon: '👤' },
                  { key: 'city', label: '所在城市', icon: '🏙️' },
                  { key: 'location', label: 'IP定位', icon: '📍' },
                ].map(({ key, label, icon }) => (
                  <div key={key} className="flex items-center justify-between py-2 border-b border-gray-100 last:border-0">
                    <span className="text-gray-700">
                      {icon} {label}
                    </span>
                    <button
                      onClick={() => {
                        if (!userProfile.privacy_settings) return;
                        const newSettings = {
                          ...userProfile.privacy_settings,
                          [key]: !userProfile.privacy_settings[key as keyof PrivacySettings],
                        };
                        updateProfileMutation.mutate({ privacy_settings: newSettings });
                      }}
                      disabled={updateProfileMutation.isPending}
                      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                        userProfile.privacy_settings?.[key as keyof PrivacySettings]
                          ? 'bg-green-500'
                          : 'bg-gray-300'
                      } ${updateProfileMutation.isPending ? 'opacity-50' : ''}`}
                    >
                      <span
                        className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                          userProfile.privacy_settings?.[key as keyof PrivacySettings]
                            ? 'translate-x-6'
                            : 'translate-x-1'
                        }`}
                      />
                    </button>
                  </div>
                ))}
              </div>

              {/* 位置信息 */}
              <div className="bg-blue-50 rounded-lg p-4 border border-blue-200">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="font-semibold text-blue-800">📍 位置设置</h3>
                </div>

                {/* 位置模式切换 */}
                <div className="flex items-center gap-4 mb-4 p-3 bg-white rounded-lg border border-blue-200">
                  <span className="text-gray-700 font-medium">定位方式:</span>
                  <div className="flex gap-2">
                    <button
                      onClick={() => {
                        if (userProfile.use_manual_location) {
                          updateManualLocationMutation.mutate({ use_manual_location: false });
                        }
                      }}
                      disabled={updateManualLocationMutation.isPending}
                      className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                        !userProfile.use_manual_location
                          ? 'bg-blue-500 text-white'
                          : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                      } ${updateManualLocationMutation.isPending ? 'opacity-50' : ''}`}
                    >
                      🌐 IP自动定位
                    </button>
                    <button
                      onClick={() => {
                        if (!userProfile.use_manual_location) {
                          updateManualLocationMutation.mutate({
                            use_manual_location: true,
                            ...manualLocationForm,
                          });
                        }
                      }}
                      disabled={updateManualLocationMutation.isPending}
                      className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                        userProfile.use_manual_location
                          ? 'bg-blue-500 text-white'
                          : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                      } ${updateManualLocationMutation.isPending ? 'opacity-50' : ''}`}
                    >
                      ✏️ 手工输入
                    </button>
                  </div>
                </div>

                {/* IP定位模式 */}
                {!userProfile.use_manual_location && (
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-blue-700">当前检测位置</span>
                      <button
                        onClick={() => refreshLocationMutation.mutate()}
                        disabled={refreshLocationMutation.isPending}
                        className="px-3 py-1 bg-blue-500 text-white rounded-lg hover:bg-blue-600 text-sm disabled:opacity-50"
                      >
                        {refreshLocationMutation.isPending ? '刷新中...' : '🔄 刷新'}
                      </button>
                    </div>
                    {userProfile.detected_location ? (
                      <div className="text-blue-700 space-y-1">
                        <p>🏙️ 城市: {userProfile.detected_location.city || '未知'}</p>
                        <p>📍 地区: {userProfile.detected_location.region || '未知'}</p>
                        <p>🌍 国家: {userProfile.detected_location.country || '未知'}</p>
                        {userProfile.location_updated_at && (
                          <p className="text-xs text-blue-500 mt-2">
                            最后更新: {formatDateTime(userProfile.location_updated_at)}
                          </p>
                        )}
                      </div>
                    ) : (
                      <p className="text-blue-600">尚未检测到位置信息，点击刷新按钮获取</p>
                    )}
                  </div>
                )}

                {/* 手工输入模式 */}
                {userProfile.use_manual_location && (
                  <div className="space-y-3">
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                      <div>
                        <label className="block text-sm font-medium text-blue-700 mb-1">国家</label>
                        <input
                          type="text"
                          value={manualLocationForm.country}
                          onChange={(e) => setManualLocationForm({ ...manualLocationForm, country: e.target.value })}
                          className="w-full p-2 border border-blue-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                          placeholder="如：中国"
                        />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-blue-700 mb-1">省份/地区</label>
                        <input
                          type="text"
                          value={manualLocationForm.region}
                          onChange={(e) => setManualLocationForm({ ...manualLocationForm, region: e.target.value })}
                          className="w-full p-2 border border-blue-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                          placeholder="如：浙江省"
                        />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-blue-700 mb-1">城市</label>
                        <input
                          type="text"
                          value={manualLocationForm.city}
                          onChange={(e) => setManualLocationForm({ ...manualLocationForm, city: e.target.value })}
                          className="w-full p-2 border border-blue-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                          placeholder="如：杭州市"
                        />
                      </div>
                    </div>
                    <button
                      onClick={() => updateManualLocationMutation.mutate({
                        use_manual_location: true,
                        ...manualLocationForm,
                      })}
                      disabled={updateManualLocationMutation.isPending}
                      className="w-full px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:opacity-50"
                    >
                      {updateManualLocationMutation.isPending ? '保存中...' : '💾 保存位置'}
                    </button>
                    {userProfile.manual_location && (
                      <div className="text-xs text-blue-600 mt-2">
                        当前已保存: {userProfile.manual_location.city || ''} {userProfile.manual_location.region || ''} {userProfile.manual_location.country || ''}
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* 说明 */}
              <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3 text-sm text-yellow-800">
                <p className="font-semibold mb-1">⚠️ 隐私说明</p>
                <ul className="list-disc list-inside space-y-1">
                  <li>这些设置控制通过 API Key 访问时哪些信息可见</li>
                  <li>关闭的字段不会出现在外部 AI 系统获取的数据中</li>
                  <li>位置信息可选择 IP 自动定位（每小时更新）或手工输入</li>
                  <li>使用手工输入时，外部系统将获取您手工设置的位置</li>
                </ul>
              </div>
            </>
          ) : (
            <div className="text-center py-4 text-gray-500">无法加载用户画像</div>
          )}
        </div>
      )}
    </div>
  );
}
