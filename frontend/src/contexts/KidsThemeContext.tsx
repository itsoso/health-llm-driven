'use client';

import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import { useAuth } from '@/contexts/AuthContext';

export interface KidsTheme {
  id: string;
  name: string;
  icon: string;
  cost: number;
  isBoy: boolean;
  bg: string;
  accent: string;
  btnGrad: string;
  tabActiveBg: string;
  tabActiveText: string;
  navBorder: string;
  inputBorder: string;
  inputFocus: string;
  bubbleGrad: string;
  sidebarBorder: string;
  searchBg: string;
  searchBorder: string;
  cardBorder: string;
  cardHoverBorder: string;
  activeBg: string;
  activeAccent: string;
  hoverBg: string;
  paginateBtn: string;
  dot1: string;
  dot2: string;
  loadingColor: string;
}

export const SKINS: KidsTheme[] = [
  {
    id: 'boy_default', name: '蓝天男孩', icon: '⭐', cost: 0, isBoy: true,
    bg: 'from-blue-50 via-sky-50 to-indigo-50',
    accent: 'text-blue-600',
    btnGrad: 'from-blue-400 to-sky-400',
    tabActiveBg: 'bg-blue-100', tabActiveText: 'text-blue-600',
    navBorder: 'border-blue-100',
    inputBorder: 'border-blue-200',
    inputFocus: 'focus:ring-blue-300 focus:border-blue-300',
    bubbleGrad: 'from-blue-300 to-sky-300',
    sidebarBorder: 'border-blue-100',
    searchBg: 'bg-blue-50', searchBorder: 'border-blue-100',
    cardBorder: 'border-blue-100', cardHoverBorder: 'hover:border-blue-300',
    activeBg: 'bg-blue-50', activeAccent: 'border-l-blue-400',
    hoverBg: 'hover:bg-blue-50/80',
    paginateBtn: 'text-blue-500 hover:bg-blue-50',
    dot1: 'bg-blue-400', dot2: 'bg-sky-400',
    loadingColor: 'text-blue-500',
  },
  {
    id: 'girl_default', name: '粉色女孩', icon: '🌟', cost: 0, isBoy: false,
    bg: 'from-pink-50 via-purple-50 to-blue-50',
    accent: 'text-purple-600',
    btnGrad: 'from-pink-400 to-purple-400',
    tabActiveBg: 'bg-pink-100', tabActiveText: 'text-pink-600',
    navBorder: 'border-pink-100',
    inputBorder: 'border-pink-200',
    inputFocus: 'focus:ring-purple-300 focus:border-purple-300',
    bubbleGrad: 'from-pink-300 to-purple-300',
    sidebarBorder: 'border-pink-100',
    searchBg: 'bg-pink-50', searchBorder: 'border-pink-100',
    cardBorder: 'border-pink-100', cardHoverBorder: 'hover:border-pink-300',
    activeBg: 'bg-purple-50', activeAccent: 'border-l-purple-400',
    hoverBg: 'hover:bg-pink-50/80',
    paginateBtn: 'text-purple-500 hover:bg-purple-50',
    dot1: 'bg-pink-400', dot2: 'bg-purple-400',
    loadingColor: 'text-purple-500',
  },
  {
    id: 'mint', name: '薄荷绿', icon: '🍃', cost: 5, isBoy: false,
    bg: 'from-teal-50 via-green-50 to-cyan-50',
    accent: 'text-teal-600',
    btnGrad: 'from-teal-300 to-green-300',
    tabActiveBg: 'bg-teal-100', tabActiveText: 'text-teal-600',
    navBorder: 'border-teal-100',
    inputBorder: 'border-teal-200',
    inputFocus: 'focus:ring-teal-300 focus:border-teal-300',
    bubbleGrad: 'from-teal-200 to-green-200',
    sidebarBorder: 'border-teal-100',
    searchBg: 'bg-teal-50', searchBorder: 'border-teal-100',
    cardBorder: 'border-teal-100', cardHoverBorder: 'hover:border-teal-300',
    activeBg: 'bg-teal-50', activeAccent: 'border-l-teal-400',
    hoverBg: 'hover:bg-teal-50/80',
    paginateBtn: 'text-teal-500 hover:bg-teal-50',
    dot1: 'bg-teal-300', dot2: 'bg-green-300',
    loadingColor: 'text-teal-500',
  },
  {
    id: 'strawberry', name: '草莓红', icon: '🍓', cost: 5, isBoy: false,
    bg: 'from-red-50 via-rose-50 to-pink-50',
    accent: 'text-red-500',
    btnGrad: 'from-red-400 to-rose-400',
    tabActiveBg: 'bg-red-100', tabActiveText: 'text-red-500',
    navBorder: 'border-red-100',
    inputBorder: 'border-red-200',
    inputFocus: 'focus:ring-red-300 focus:border-red-300',
    bubbleGrad: 'from-red-300 to-rose-300',
    sidebarBorder: 'border-red-100',
    searchBg: 'bg-red-50', searchBorder: 'border-red-100',
    cardBorder: 'border-red-100', cardHoverBorder: 'hover:border-red-300',
    activeBg: 'bg-red-50', activeAccent: 'border-l-red-400',
    hoverBg: 'hover:bg-red-50/80',
    paginateBtn: 'text-red-500 hover:bg-red-50',
    dot1: 'bg-red-400', dot2: 'bg-rose-400',
    loadingColor: 'text-red-500',
  },
  {
    id: 'sunflower', name: '向日葵', icon: '🌻', cost: 5, isBoy: false,
    bg: 'from-yellow-50 via-lime-50 to-green-50',
    accent: 'text-yellow-600',
    btnGrad: 'from-yellow-300 to-lime-400',
    tabActiveBg: 'bg-yellow-100', tabActiveText: 'text-yellow-600',
    navBorder: 'border-yellow-100',
    inputBorder: 'border-yellow-200',
    inputFocus: 'focus:ring-yellow-300 focus:border-yellow-300',
    bubbleGrad: 'from-yellow-200 to-lime-300',
    sidebarBorder: 'border-yellow-100',
    searchBg: 'bg-yellow-50', searchBorder: 'border-yellow-100',
    cardBorder: 'border-yellow-100', cardHoverBorder: 'hover:border-yellow-300',
    activeBg: 'bg-yellow-50', activeAccent: 'border-l-yellow-400',
    hoverBg: 'hover:bg-yellow-50/80',
    paginateBtn: 'text-yellow-500 hover:bg-yellow-50',
    dot1: 'bg-yellow-300', dot2: 'bg-lime-400',
    loadingColor: 'text-yellow-500',
  },
  {
    id: 'sky', name: '天空蓝', icon: '☁️', cost: 5, isBoy: true,
    bg: 'from-sky-50 via-blue-50 to-cyan-50',
    accent: 'text-sky-500',
    btnGrad: 'from-sky-300 to-blue-300',
    tabActiveBg: 'bg-sky-100', tabActiveText: 'text-sky-500',
    navBorder: 'border-sky-100',
    inputBorder: 'border-sky-200',
    inputFocus: 'focus:ring-sky-300 focus:border-sky-300',
    bubbleGrad: 'from-sky-200 to-blue-200',
    sidebarBorder: 'border-sky-100',
    searchBg: 'bg-sky-50', searchBorder: 'border-sky-100',
    cardBorder: 'border-sky-100', cardHoverBorder: 'hover:border-sky-300',
    activeBg: 'bg-sky-50', activeAccent: 'border-l-sky-400',
    hoverBg: 'hover:bg-sky-50/80',
    paginateBtn: 'text-sky-500 hover:bg-sky-50',
    dot1: 'bg-sky-300', dot2: 'bg-blue-300',
    loadingColor: 'text-sky-500',
  },
  {
    id: 'peach', name: '蜜桃橙', icon: '🍑', cost: 5, isBoy: false,
    bg: 'from-orange-50 via-pink-50 to-rose-50',
    accent: 'text-orange-500',
    btnGrad: 'from-orange-300 to-pink-300',
    tabActiveBg: 'bg-orange-100', tabActiveText: 'text-orange-500',
    navBorder: 'border-orange-100',
    inputBorder: 'border-orange-200',
    inputFocus: 'focus:ring-orange-300 focus:border-orange-300',
    bubbleGrad: 'from-orange-200 to-pink-200',
    sidebarBorder: 'border-orange-100',
    searchBg: 'bg-orange-50', searchBorder: 'border-orange-100',
    cardBorder: 'border-orange-100', cardHoverBorder: 'hover:border-orange-300',
    activeBg: 'bg-orange-50', activeAccent: 'border-l-orange-400',
    hoverBg: 'hover:bg-orange-50/80',
    paginateBtn: 'text-orange-500 hover:bg-orange-50',
    dot1: 'bg-orange-300', dot2: 'bg-pink-300',
    loadingColor: 'text-orange-500',
  },
  {
    id: 'forest', name: '森林绿', icon: '🌿', cost: 10, isBoy: false,
    bg: 'from-green-50 via-emerald-50 to-teal-50',
    accent: 'text-green-600',
    btnGrad: 'from-green-400 to-emerald-400',
    tabActiveBg: 'bg-green-100', tabActiveText: 'text-green-600',
    navBorder: 'border-green-100',
    inputBorder: 'border-green-200',
    inputFocus: 'focus:ring-green-300 focus:border-green-300',
    bubbleGrad: 'from-green-300 to-emerald-300',
    sidebarBorder: 'border-green-100',
    searchBg: 'bg-green-50', searchBorder: 'border-green-100',
    cardBorder: 'border-green-100', cardHoverBorder: 'hover:border-green-300',
    activeBg: 'bg-green-50', activeAccent: 'border-l-green-400',
    hoverBg: 'hover:bg-green-50/80',
    paginateBtn: 'text-green-500 hover:bg-green-50',
    dot1: 'bg-green-400', dot2: 'bg-emerald-400',
    loadingColor: 'text-green-500',
  },
  {
    id: 'sunset', name: '夕阳橙', icon: '🌅', cost: 15, isBoy: false,
    bg: 'from-orange-50 via-amber-50 to-yellow-50',
    accent: 'text-orange-600',
    btnGrad: 'from-orange-400 to-amber-400',
    tabActiveBg: 'bg-orange-100', tabActiveText: 'text-orange-600',
    navBorder: 'border-orange-100',
    inputBorder: 'border-orange-200',
    inputFocus: 'focus:ring-orange-300 focus:border-orange-300',
    bubbleGrad: 'from-orange-300 to-amber-300',
    sidebarBorder: 'border-orange-100',
    searchBg: 'bg-orange-50', searchBorder: 'border-orange-100',
    cardBorder: 'border-orange-100', cardHoverBorder: 'hover:border-orange-300',
    activeBg: 'bg-orange-50', activeAccent: 'border-l-orange-400',
    hoverBg: 'hover:bg-orange-50/80',
    paginateBtn: 'text-orange-500 hover:bg-orange-50',
    dot1: 'bg-orange-400', dot2: 'bg-amber-400',
    loadingColor: 'text-orange-500',
  },
  {
    id: 'ocean', name: '深海蓝', icon: '🌊', cost: 20, isBoy: true,
    bg: 'from-cyan-50 via-teal-50 to-blue-50',
    accent: 'text-teal-600',
    btnGrad: 'from-cyan-400 to-teal-400',
    tabActiveBg: 'bg-cyan-100', tabActiveText: 'text-teal-600',
    navBorder: 'border-cyan-100',
    inputBorder: 'border-cyan-200',
    inputFocus: 'focus:ring-cyan-300 focus:border-cyan-300',
    bubbleGrad: 'from-cyan-300 to-teal-300',
    sidebarBorder: 'border-cyan-100',
    searchBg: 'bg-cyan-50', searchBorder: 'border-cyan-100',
    cardBorder: 'border-cyan-100', cardHoverBorder: 'hover:border-cyan-300',
    activeBg: 'bg-cyan-50', activeAccent: 'border-l-cyan-400',
    hoverBg: 'hover:bg-cyan-50/80',
    paginateBtn: 'text-teal-500 hover:bg-cyan-50',
    dot1: 'bg-cyan-400', dot2: 'bg-teal-400',
    loadingColor: 'text-teal-500',
  },
  {
    id: 'sakura', name: '樱花粉', icon: '🌸', cost: 20, isBoy: false,
    bg: 'from-rose-50 via-pink-50 to-fuchsia-50',
    accent: 'text-rose-600',
    btnGrad: 'from-rose-400 to-fuchsia-400',
    tabActiveBg: 'bg-rose-100', tabActiveText: 'text-rose-600',
    navBorder: 'border-rose-100',
    inputBorder: 'border-rose-200',
    inputFocus: 'focus:ring-rose-300 focus:border-rose-300',
    bubbleGrad: 'from-rose-300 to-fuchsia-300',
    sidebarBorder: 'border-rose-100',
    searchBg: 'bg-rose-50', searchBorder: 'border-rose-100',
    cardBorder: 'border-rose-100', cardHoverBorder: 'hover:border-rose-300',
    activeBg: 'bg-rose-50', activeAccent: 'border-l-rose-400',
    hoverBg: 'hover:bg-rose-50/80',
    paginateBtn: 'text-rose-500 hover:bg-rose-50',
    dot1: 'bg-rose-400', dot2: 'bg-fuchsia-400',
    loadingColor: 'text-rose-500',
  },
  {
    id: 'lavender', name: '薰衣草', icon: '💜', cost: 25, isBoy: false,
    bg: 'from-violet-50 via-purple-50 to-indigo-50',
    accent: 'text-violet-600',
    btnGrad: 'from-violet-400 to-indigo-400',
    tabActiveBg: 'bg-violet-100', tabActiveText: 'text-violet-600',
    navBorder: 'border-violet-100',
    inputBorder: 'border-violet-200',
    inputFocus: 'focus:ring-violet-300 focus:border-violet-300',
    bubbleGrad: 'from-violet-300 to-indigo-300',
    sidebarBorder: 'border-violet-100',
    searchBg: 'bg-violet-50', searchBorder: 'border-violet-100',
    cardBorder: 'border-violet-100', cardHoverBorder: 'hover:border-violet-300',
    activeBg: 'bg-violet-50', activeAccent: 'border-l-violet-400',
    hoverBg: 'hover:bg-violet-50/80',
    paginateBtn: 'text-violet-500 hover:bg-violet-50',
    dot1: 'bg-violet-400', dot2: 'bg-indigo-400',
    loadingColor: 'text-violet-500',
  },
  {
    id: 'rainbow', name: '糖果彩虹', icon: '🌈', cost: 30, isBoy: false,
    bg: 'from-yellow-50 via-pink-50 to-purple-50',
    accent: 'text-pink-600',
    btnGrad: 'from-yellow-400 via-pink-400 to-purple-400',
    tabActiveBg: 'bg-yellow-100', tabActiveText: 'text-pink-600',
    navBorder: 'border-yellow-100',
    inputBorder: 'border-pink-200',
    inputFocus: 'focus:ring-pink-300 focus:border-pink-300',
    bubbleGrad: 'from-yellow-300 to-pink-300',
    sidebarBorder: 'border-yellow-100',
    searchBg: 'bg-yellow-50', searchBorder: 'border-yellow-100',
    cardBorder: 'border-yellow-100', cardHoverBorder: 'hover:border-pink-300',
    activeBg: 'bg-yellow-50', activeAccent: 'border-l-pink-400',
    hoverBg: 'hover:bg-yellow-50/80',
    paginateBtn: 'text-pink-500 hover:bg-yellow-50',
    dot1: 'bg-yellow-400', dot2: 'bg-pink-400',
    loadingColor: 'text-pink-500',
  },
  {
    id: 'galaxy', name: '星空银河', icon: '🌌', cost: 35, isBoy: true,
    bg: 'from-slate-50 via-blue-50 to-indigo-100',
    accent: 'text-indigo-600',
    btnGrad: 'from-indigo-500 to-purple-500',
    tabActiveBg: 'bg-indigo-100', tabActiveText: 'text-indigo-600',
    navBorder: 'border-indigo-100',
    inputBorder: 'border-indigo-200',
    inputFocus: 'focus:ring-indigo-300 focus:border-indigo-300',
    bubbleGrad: 'from-indigo-400 to-purple-400',
    sidebarBorder: 'border-indigo-100',
    searchBg: 'bg-indigo-50', searchBorder: 'border-indigo-100',
    cardBorder: 'border-indigo-100', cardHoverBorder: 'hover:border-indigo-300',
    activeBg: 'bg-indigo-50', activeAccent: 'border-l-indigo-400',
    hoverBg: 'hover:bg-indigo-50/80',
    paginateBtn: 'text-indigo-500 hover:bg-indigo-50',
    dot1: 'bg-indigo-400', dot2: 'bg-purple-400',
    loadingColor: 'text-indigo-500',
  },
  {
    id: 'golden', name: '黄金传说', icon: '👑', cost: 50, isBoy: false,
    bg: 'from-yellow-50 via-amber-50 to-orange-50',
    accent: 'text-amber-600',
    btnGrad: 'from-yellow-400 to-amber-500',
    tabActiveBg: 'bg-yellow-100', tabActiveText: 'text-amber-600',
    navBorder: 'border-yellow-200',
    inputBorder: 'border-yellow-200',
    inputFocus: 'focus:ring-yellow-300 focus:border-yellow-300',
    bubbleGrad: 'from-yellow-300 to-amber-400',
    sidebarBorder: 'border-yellow-100',
    searchBg: 'bg-yellow-50', searchBorder: 'border-yellow-100',
    cardBorder: 'border-yellow-200', cardHoverBorder: 'hover:border-yellow-400',
    activeBg: 'bg-yellow-50', activeAccent: 'border-l-yellow-500',
    hoverBg: 'hover:bg-yellow-50/80',
    paginateBtn: 'text-amber-500 hover:bg-yellow-50',
    dot1: 'bg-yellow-400', dot2: 'bg-amber-500',
    loadingColor: 'text-amber-500',
  },
];

export interface KidsThemeContextType {
  theme: KidsTheme;
  currentSkinId: string;
  points: number;
  unlockedSkins: string[];
  setSkin: (skinId: string) => void;
  addPoints: (pts: number) => void;
  purchaseSkin: (skinId: string) => boolean;
}

const KidsThemeContext = createContext<KidsThemeContextType | null>(null);

export function KidsThemeProvider({ children }: { children: ReactNode }) {
  const { user, token } = useAuth();
  const userId = user?.id || 'guest';
  const defaultSkinId = user?.gender === 'male' ? 'boy_default' : 'girl_default';

  const [currentSkinId, setCurrentSkinId] = useState<string>(defaultSkinId);
  const [points, setPoints] = useState<number>(0);
  const [unlockedSkins, setUnlockedSkins] = useState<string[]>(['boy_default', 'girl_default']);

  const syncPointsToServer = useCallback(async (nextPoints: number) => {
    if (!token || !user?.id) return;
    try {
      await fetch('/api/auth/me/kids-points', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ kids_points: nextPoints }),
      });
    } catch {
      // Keep local state even if server sync is temporarily unavailable.
    }
  }, [token, user?.id]);

  useEffect(() => {
    const savedSkin = localStorage.getItem(`kids_skin_${userId}`);
    const savedUnlocked = localStorage.getItem(`kids_skins_${userId}`);
    const dbPoints = typeof user?.kids_points === 'number' ? user.kids_points : 0;

    setCurrentSkinId(savedSkin || defaultSkinId);
    setPoints(dbPoints);
    if (savedUnlocked) {
      try { setUnlockedSkins(JSON.parse(savedUnlocked)); } catch { /* ignore */ }
    } else {
      setUnlockedSkins(['boy_default', 'girl_default']);
    }
  }, [userId, defaultSkinId, user?.kids_points, syncPointsToServer]);

  const theme = SKINS.find(s => s.id === currentSkinId) || SKINS.find(s => s.id === defaultSkinId)!;

  const setSkin = useCallback((skinId: string) => {
    setCurrentSkinId(skinId);
    localStorage.setItem(`kids_skin_${userId}`, skinId);
  }, [userId]);

  const addPoints = useCallback((pts: number) => {
    setPoints(prev => {
      const next = prev + pts;
      void syncPointsToServer(next);
      return next;
    });
  }, [syncPointsToServer]);

  const purchaseSkin = useCallback((skinId: string): boolean => {
    const skin = SKINS.find(s => s.id === skinId);
    if (!skin) return false;
    if (unlockedSkins.includes(skinId)) return true;
    if (points < skin.cost) return false;

    const newPoints = points - skin.cost;
    const newUnlocked = [...unlockedSkins, skinId];

    setPoints(newPoints);
    setUnlockedSkins(newUnlocked);
    localStorage.setItem(`kids_skins_${userId}`, JSON.stringify(newUnlocked));
    void syncPointsToServer(newPoints);

    return true;
  }, [points, unlockedSkins, syncPointsToServer]);

  return (
    <KidsThemeContext.Provider value={{ theme, currentSkinId, points, unlockedSkins, setSkin, addPoints, purchaseSkin }}>
      {children}
    </KidsThemeContext.Provider>
  );
}

export function useKidsTheme(): KidsThemeContextType {
  const ctx = useContext(KidsThemeContext);
  if (!ctx) throw new Error('useKidsTheme must be used within KidsThemeProvider');
  return ctx;
}
