'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { api, moodApi } from '@/services/api';
import { compressImage } from '@/utils/imageCompress';

export default function KidsMePage() {
  const router = useRouter();
  const { user, logout, refreshUser } = useAuth();
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
        // 优先用 completed_templates，其次用 records 过滤
        checkins = data?.completed_templates ?? (data?.records || []).filter((r: any) => r.completion_rate >= 100).length;
      }

      let water = 0;
      if (waterRes.status === 'fulfilled') {
        const wData = waterRes.value.data;
        // API 返回对象 { total_amount, records: [...] }
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
    <div className="flex flex-col items-center px-6 py-8 min-h-full">
      {/* 头像 */}
      <button
        onClick={handleAvatarClick}
        disabled={uploading}
        className="relative w-28 h-28 rounded-full bg-gradient-to-br from-pink-300 to-purple-400 flex items-center justify-center shadow-xl mb-2 overflow-hidden active:scale-95 transition-transform"
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
      <p className="text-sm text-gray-400 mb-4">点击头像更换照片</p>

      {/* 用户名 */}
      <h1 className="text-3xl font-bold text-purple-600 mb-8">{user?.name || '小朋友'}</h1>

      {/* 今日统计 */}
      <div className="grid grid-cols-3 gap-6 w-full max-w-lg mb-10">
        <div className="flex flex-col items-center p-5 bg-white rounded-3xl shadow-lg border-2 border-green-100">
          <span className="text-4xl mb-2">✅</span>
          <span className="text-2xl font-bold text-green-600">{stats.checkins}</span>
          <span className="text-base text-gray-500">今日打卡</span>
        </div>
        <div className="flex flex-col items-center p-5 bg-white rounded-3xl shadow-lg border-2 border-blue-100">
          <span className="text-4xl mb-2">💧</span>
          <span className="text-2xl font-bold text-blue-600">{stats.water}ml</span>
          <span className="text-base text-gray-500">今日喝水</span>
        </div>
        <div className="flex flex-col items-center p-5 bg-white rounded-3xl shadow-lg border-2 border-yellow-100">
          <span className="text-4xl mb-2">{stats.mood || '❓'}</span>
          <span className="text-2xl font-bold text-yellow-600">{stats.mood ? '已记录' : '未记录'}</span>
          <span className="text-base text-gray-500">今日心情</span>
        </div>
      </div>

      {/* 操作按钮 */}
      <div className="flex flex-col gap-4 w-full max-w-sm">
        <button
          onClick={() => router.push('/')}
          className="w-full py-4 bg-white border-2 border-purple-200 rounded-2xl text-lg font-bold text-purple-600 hover:bg-purple-50 transition-all active:scale-95 shadow-md"
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
