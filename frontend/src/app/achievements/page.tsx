'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import ProtectedRoute from '@/components/ProtectedRoute';
import { achievementApi } from '@/services/api';

interface Achievement {
  id: number;
  code: string;
  name: string;
  description: string;
  icon: string;
  category: string;
  rarity: string;
  criteria_value: number;
  progress: number;
  unlocked: boolean;
  unlocked_at: string | null;
}

const CATEGORY_TABS = [
  { key: 'all', label: '全部' },
  { key: 'streak', label: '连续' },
  { key: 'activity', label: '活动' },
  { key: 'milestone', label: '里程碑' },
];

const RARITY_COLORS: Record<string, string> = {
  common: 'from-gray-100 to-gray-200 border-gray-300',
  rare: 'from-blue-50 to-blue-100 border-blue-300',
  epic: 'from-purple-50 to-purple-100 border-purple-300',
  legendary: 'from-yellow-50 to-amber-100 border-amber-400',
};

const RARITY_GLOW: Record<string, string> = {
  common: '',
  rare: 'shadow-blue-200',
  epic: 'shadow-purple-200',
  legendary: 'shadow-amber-300',
};

export default function AchievementsPage() {
  const router = useRouter();
  const [achievements, setAchievements] = useState<Achievement[]>([]);
  const [unlocked, setUnlocked] = useState(0);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('all');
  const [selectedBadge, setSelectedBadge] = useState<Achievement | null>(null);

  useEffect(() => {
    loadAchievements();
  }, []);

  const loadAchievements = async () => {
    try {
      const res = await achievementApi.getMyAchievements();
      setAchievements(res.data.achievements);
      setUnlocked(res.data.unlocked);
      setTotal(res.data.total);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  const filtered = activeTab === 'all'
    ? achievements
    : achievements.filter(a => a.category === activeTab);

  return (
    <ProtectedRoute>
      <div className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 pt-20 pb-24 px-4">
        <div className="max-w-2xl mx-auto">
          {/* Header */}
          <div className="flex items-center gap-3 mb-6">
            <button onClick={() => router.back()} className="text-gray-500 hover:text-gray-700">
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
            </button>
            <div>
              <h1 className="text-xl font-bold text-gray-800">我的成就</h1>
              <p className="text-sm text-gray-500">
                已解锁 <span className="font-bold text-indigo-600">{unlocked}</span> / {total}
              </p>
            </div>
          </div>

          {/* Category Tabs */}
          <div className="flex gap-2 mb-6 overflow-x-auto">
            {CATEGORY_TABS.map(tab => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`px-4 py-1.5 rounded-full text-sm font-medium whitespace-nowrap transition ${
                  activeTab === tab.key
                    ? 'bg-indigo-600 text-white'
                    : 'bg-white text-gray-600 hover:bg-gray-100'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Loading */}
          {loading && (
            <div className="text-center py-20">
              <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-indigo-600 mx-auto" />
            </div>
          )}

          {/* Badge Grid */}
          {!loading && (
            <div className="grid grid-cols-3 gap-3">
              {filtered.map(badge => {
                const pct = Math.min((badge.progress / badge.criteria_value) * 100, 100);
                const rarityClass = RARITY_COLORS[badge.rarity] || RARITY_COLORS.common;
                const glowClass = badge.unlocked ? (RARITY_GLOW[badge.rarity] || '') : '';

                return (
                  <button
                    key={badge.id}
                    onClick={() => setSelectedBadge(badge)}
                    className={`relative flex flex-col items-center p-3 rounded-2xl border bg-gradient-to-b transition-all ${rarityClass} ${
                      badge.unlocked ? `shadow-lg ${glowClass}` : 'opacity-60 grayscale'
                    }`}
                  >
                    <span className="text-3xl mb-1">{badge.icon}</span>
                    <span className="text-xs font-bold text-center leading-tight">{badge.name}</span>
                    {/* Progress bar */}
                    {!badge.unlocked && (
                      <div className="w-full mt-2">
                        <div className="h-1 bg-gray-300 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-indigo-500 rounded-full transition-all"
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                        <p className="text-[10px] text-gray-500 text-center mt-0.5">
                          {Math.round(badge.progress)}/{Math.round(badge.criteria_value)}
                        </p>
                      </div>
                    )}
                    {badge.unlocked && (
                      <span className="text-[10px] text-green-600 font-medium mt-1">
                        已解锁
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          )}

          {/* Detail Modal */}
          {selectedBadge && (
            <div
              className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4"
              onClick={() => setSelectedBadge(null)}
            >
              <div
                className="bg-white rounded-2xl p-6 max-w-sm w-full shadow-xl"
                onClick={e => e.stopPropagation()}
              >
                <div className="text-center">
                  <span className="text-5xl">{selectedBadge.icon}</span>
                  <h3 className="text-lg font-bold mt-3">{selectedBadge.name}</h3>
                  <p className="text-sm text-gray-500 mt-1">{selectedBadge.description}</p>
                  <div className="mt-3">
                    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${
                      selectedBadge.rarity === 'legendary' ? 'bg-amber-100 text-amber-700' :
                      selectedBadge.rarity === 'epic' ? 'bg-purple-100 text-purple-700' :
                      selectedBadge.rarity === 'rare' ? 'bg-blue-100 text-blue-700' :
                      'bg-gray-100 text-gray-600'
                    }`}>
                      {selectedBadge.rarity === 'legendary' ? '传说' :
                       selectedBadge.rarity === 'epic' ? '史诗' :
                       selectedBadge.rarity === 'rare' ? '稀有' : '普通'}
                    </span>
                  </div>
                  {/* Progress */}
                  <div className="mt-4">
                    <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-indigo-500 rounded-full"
                        style={{ width: `${Math.min((selectedBadge.progress / selectedBadge.criteria_value) * 100, 100)}%` }}
                      />
                    </div>
                    <p className="text-sm text-gray-600 mt-1">
                      {Math.round(selectedBadge.progress)} / {Math.round(selectedBadge.criteria_value)}
                    </p>
                  </div>
                  {selectedBadge.unlocked && selectedBadge.unlocked_at && (
                    <p className="text-xs text-green-600 mt-2">
                      解锁于 {new Date(selectedBadge.unlocked_at).toLocaleDateString()}
                    </p>
                  )}
                </div>
                <button
                  onClick={() => setSelectedBadge(null)}
                  className="mt-5 w-full py-2 bg-gray-100 rounded-xl text-sm text-gray-600 hover:bg-gray-200"
                >
                  关闭
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </ProtectedRoute>
  );
}
