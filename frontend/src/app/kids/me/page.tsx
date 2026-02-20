'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { useKidsTheme } from '@/contexts/KidsThemeContext';
import { api, moodApi } from '@/services/api';
import { compressImage } from '@/utils/imageCompress';

export default function KidsMePage() {
  const router = useRouter();
  const { user, logout, refreshUser } = useAuth();
  const { theme, points } = useKidsTheme();
  const [stats, setStats] = useState({ checkins: 0, water: 0, mood: '' });
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const today = new Date().toISOString().split('T')[0];

  const loadStats = useCallback(async () => {
    try {
      const [checkinRes, waterRes, moodRes] = await Promise.allSettled([
        api.get('/checkin/records/today'),
        api.get(`/water/records/me/date/${today}`),
        moodApi.getTodayRecord(),
      ]);

      let checkins = 0;
      if (checkinRes.status === 'fulfilled') {
        const data = checkinRes.value.data;
        checkins = data?.completed_templates ?? (data?.records || []).filter((r: any) => r.completion_rate >= 100).length;
      }

      let water = 0;
      if (waterRes.status === 'fulfilled') {
        const wData = waterRes.value.data;
        water = wData?.total_amount ?? (wData?.records || []).reduce((sum: number, r: any) => sum + (r.amount || 0), 0);
      }

      const moodEmojis: Record<number, string> = { 1: '😢', 2: '😟', 3: '😐', 4: '😊', 5: '😄' };
      let mood = '';
      if (moodRes.status === 'fulfilled' && moodRes.value.data) {
        const score = moodRes.value.data.mood_score;
        if (score && moodEmojis[score]) {
          mood = moodEmojis[score];
        }
      }

      setStats({ checkins, water, mood });
    } catch {
      // 忽略
    }
  }, [today]);

  useEffect(() => {
    loadStats();
  }, [loadStats]);

  const handleLogout = () => {
    logout();
    router.push('/login');
  };

  const handleAvatarClick = () => {
    fileInputRef.current?.click();
  };

  const handleAvatarUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    try {
      const compressed = await compressImage(file, 512, 0.8);
      const formData = new FormData();
      formData.append('file', compressed);
      await api.post('/users/me/avatar', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      await refreshUser();
    } catch {
      // 忽略
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const firstName = user?.name?.charAt(0) || '👧';

  return (
    <div className="flex flex-col items-center px-6 py-8 min-h-full overflow-y-auto">
      {/* 头像 */}
      <button
        onClick={handleAvatarClick}
        disabled={uploading}
        className={`relative w-28 h-28 rounded-full bg-gradient-to-br ${theme.btnGrad} flex items-center justify-center shadow-xl mb-2 overflow-hidden active:scale-95 transition-transform`}
      >
        {user?.avatar_url ? (
          <img src={user.avatar_url} alt="头像" className="w-full h-full object-cover" />
        ) : (
          <span className="text-5xl text-white font-bold">{firstName}</span>
        )}
        {uploading && (
          <div className="absolute inset-0 bg-black/30 flex items-center justify-center">
            <div className="w-8 h-8 border-4 border-white border-t-transparent rounded-full animate-spin" />
          </div>
        )}
      </button>
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={handleAvatarUpload}
      />
      <p className="text-sm text-gray-400 mb-3">点击头像更换照片</p>

      {/* 用户名 */}
      <h1 className={`text-3xl font-bold ${theme.accent} mb-2`}>{user?.name || '小朋友'}</h1>

      {/* 积分显示 */}
      <div className={`flex items-center gap-2 px-5 py-2.5 rounded-full bg-gradient-to-r ${theme.btnGrad} shadow-md mb-8`}>
        <span className="text-2xl">⭐</span>
        <span className="text-white text-xl font-bold">{points} 积分</span>
      </div>

      {/* 今日统计 */}
      <div className="grid grid-cols-3 gap-4 w-full max-w-lg mb-8">
        <div className="flex flex-col items-center p-4 bg-white rounded-3xl shadow-md border-2 border-green-100">
          <span className="text-4xl mb-1">✅</span>
          <span className="text-2xl font-bold text-green-600">{stats.checkins}</span>
          <span className="text-sm text-gray-500">今日打卡</span>
        </div>
        <div className="flex flex-col items-center p-4 bg-white rounded-3xl shadow-md border-2 border-blue-100">
          <span className="text-4xl mb-1">💧</span>
          <span className="text-2xl font-bold text-blue-600">{stats.water}ml</span>
          <span className="text-sm text-gray-500">今日喝水</span>
        </div>
        <div className="flex flex-col items-center p-4 bg-white rounded-3xl shadow-md border-2 border-yellow-100">
          <span className="text-4xl mb-1">{stats.mood || '❓'}</span>
          <span className="text-2xl font-bold text-yellow-600">{stats.mood ? '已记录' : '未记录'}</span>
          <span className="text-sm text-gray-500">今日心情</span>
        </div>
      </div>

      {/* 操作按钮 */}
      <div className="flex flex-col gap-4 w-full max-w-sm">
        <button
          onClick={() => router.push('/kids/shop')}
          className={`w-full py-4 rounded-2xl bg-gradient-to-r ${theme.btnGrad} text-lg font-bold text-white shadow-lg hover:shadow-xl transition-all active:scale-95`}
        >
          🛍️ 皮肤商店
        </button>

        <button
          onClick={() => router.push('/')}
          className={`w-full py-4 bg-white border-2 ${theme.navBorder} rounded-2xl text-lg font-bold ${theme.accent} hover:bg-gray-50 transition-all active:scale-95 shadow-md`}
        >
          🔄 切换到完整版
        </button>

        <button
          onClick={handleLogout}
          className="w-full py-4 bg-white border-2 border-gray-200 rounded-2xl text-lg font-bold text-gray-500 hover:bg-gray-50 transition-all active:scale-95 shadow-md"
        >
          👋 退出登录
        </button>
      </div>
    </div>
  );
}
