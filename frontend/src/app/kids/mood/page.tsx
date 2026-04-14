'use client';

import { useState, useEffect, useCallback } from 'react';
import { moodApi } from '@/services/api/records';

const MOODS = [
  { score: 1, emoji: '😢', label: '难过', color: 'bg-red-100 border-red-300 hover:bg-red-200', activeColor: 'bg-red-200 border-red-400 ring-4 ring-red-200' },
  { score: 2, emoji: '😟', label: '不太好', color: 'bg-orange-100 border-orange-300 hover:bg-orange-200', activeColor: 'bg-orange-200 border-orange-400 ring-4 ring-orange-200' },
  { score: 3, emoji: '😐', label: '一般', color: 'bg-yellow-100 border-yellow-300 hover:bg-yellow-200', activeColor: 'bg-yellow-200 border-yellow-400 ring-4 ring-yellow-200' },
  { score: 4, emoji: '😊', label: '开心', color: 'bg-green-100 border-green-300 hover:bg-green-200', activeColor: 'bg-green-200 border-green-400 ring-4 ring-green-200' },
  { score: 5, emoji: '😄', label: '超开心', color: 'bg-emerald-100 border-emerald-300 hover:bg-emerald-200', activeColor: 'bg-emerald-200 border-emerald-400 ring-4 ring-emerald-200' },
];

const ENCOURAGEMENTS = [
  '抱抱你，明天会更好的~ 💕',
  '别担心，一切都会好起来的~ 🌈',
  '还不错哦，继续加油~ ✨',
  '你的笑容真好看！继续保持~ 🌟',
  '哇，今天心情超棒！太开心了！🎉',
];

export default function KidsMoodPage() {
  const [todayMood, setTodayMood] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [showCelebration, setShowCelebration] = useState(false);
  const [encouragement, setEncouragement] = useState('');

  const today = new Date().toISOString().split('T')[0];

  const loadTodayMood = useCallback(async () => {
    try {
      const res = await moodApi.getTodayRecord();
      if (res.data && res.data.mood_score) {
        setTodayMood(res.data.mood_score);
      }
    } catch {
      // 忽略
    }
  }, []);

  useEffect(() => {
    loadTodayMood();
  }, [loadTodayMood]);

  const handleSelectMood = async (score: number) => {
    if (saving) return;
    setSaving(true);
    try {
      await moodApi.createRecord({
        record_date: today,
        mood_score: score,
      });
      setTodayMood(score);
      setEncouragement(ENCOURAGEMENTS[score - 1]);
      setShowCelebration(true);
      setTimeout(() => setShowCelebration(false), 3000);
    } catch {
      // 忽略
    } finally {
      setSaving(false);
    }
  };

  const handleChangeMood = () => {
    setTodayMood(null);
    setShowCelebration(false);
  };

  return (
    <div className="flex flex-col items-center px-6 py-8 min-h-full">
      <h1 className="text-3xl font-bold text-purple-600 mb-4">😊 今天心情怎么样？</h1>

      {todayMood === null ? (
        <>
          <p className="text-xl text-gray-500 mb-10">选一个表情告诉我吧~</p>

          {/* 心情选择 */}
          <div className="flex gap-6 flex-wrap justify-center">
            {MOODS.map(mood => (
              <button
                key={mood.score}
                onClick={() => handleSelectMood(mood.score)}
                disabled={saving}
                className={`flex flex-col items-center gap-3 w-32 h-36 rounded-3xl border-3 transition-all active:scale-95 shadow-lg ${
                  saving ? 'opacity-50' : mood.color
                } border-2`}
              >
                <span className="text-6xl mt-3">{mood.emoji}</span>
                <span className="text-lg font-bold text-gray-700">{mood.label}</span>
              </button>
            ))}
          </div>
        </>
      ) : (
        <div className="text-center mt-8">
          {/* 已选心情展示 */}
          <div className={`inline-block px-12 py-8 rounded-3xl shadow-xl border-2 ${
            MOODS[todayMood - 1]?.activeColor || ''
          }`}>
            <div className="text-8xl mb-4">{MOODS[todayMood - 1]?.emoji}</div>
            <div className="text-2xl font-bold text-gray-700 mb-2">
              {MOODS[todayMood - 1]?.label}
            </div>
          </div>

          {/* 庆祝/鼓励 */}
          {showCelebration && (
            <div className="mt-8 animate-bounce">
              <p className="text-2xl font-bold text-purple-600">{encouragement}</p>
            </div>
          )}

          {/* 换个心情按钮 */}
          <div className="mt-10">
            <button
              onClick={handleChangeMood}
              className="px-8 py-3 bg-white border-2 border-pink-200 rounded-full text-lg font-bold text-gray-600 hover:border-pink-400 hover:text-pink-600 transition-all active:scale-95 shadow-md"
            >
              换个心情
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
