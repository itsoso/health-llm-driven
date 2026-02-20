'use client';

import { useAuth } from '@/contexts/AuthContext';

export interface KidsTheme {
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
  icon: string;
  loadingColor: string;
}

const boyTheme: KidsTheme = {
  isBoy: true,
  bg: 'from-blue-50 via-sky-50 to-indigo-50',
  accent: 'text-blue-600',
  btnGrad: 'from-blue-400 to-sky-400',
  tabActiveBg: 'bg-blue-100',
  tabActiveText: 'text-blue-600',
  navBorder: 'border-blue-100',
  inputBorder: 'border-blue-200',
  inputFocus: 'focus:ring-blue-300 focus:border-blue-300',
  bubbleGrad: 'from-blue-300 to-sky-300',
  sidebarBorder: 'border-blue-100',
  searchBg: 'bg-blue-50',
  searchBorder: 'border-blue-100',
  cardBorder: 'border-blue-100',
  cardHoverBorder: 'hover:border-blue-300',
  activeBg: 'bg-blue-50',
  activeAccent: 'border-l-blue-400',
  hoverBg: 'hover:bg-blue-50/80',
  paginateBtn: 'text-blue-500 hover:bg-blue-50',
  dot1: 'bg-blue-400',
  dot2: 'bg-sky-400',
  icon: '⭐',
  loadingColor: 'text-blue-500',
};

const girlTheme: KidsTheme = {
  isBoy: false,
  bg: 'from-pink-50 via-purple-50 to-blue-50',
  accent: 'text-purple-600',
  btnGrad: 'from-pink-400 to-purple-400',
  tabActiveBg: 'bg-pink-100',
  tabActiveText: 'text-pink-600',
  navBorder: 'border-pink-100',
  inputBorder: 'border-pink-200',
  inputFocus: 'focus:ring-purple-300 focus:border-purple-300',
  bubbleGrad: 'from-pink-300 to-purple-300',
  sidebarBorder: 'border-pink-100',
  searchBg: 'bg-pink-50',
  searchBorder: 'border-pink-100',
  cardBorder: 'border-pink-100',
  cardHoverBorder: 'hover:border-pink-300',
  activeBg: 'bg-purple-50',
  activeAccent: 'border-l-purple-400',
  hoverBg: 'hover:bg-pink-50/80',
  paginateBtn: 'text-purple-500 hover:bg-purple-50',
  dot1: 'bg-pink-400',
  dot2: 'bg-purple-400',
  icon: '🌟',
  loadingColor: 'text-purple-500',
};

export function useKidsTheme(): KidsTheme {
  const { user } = useAuth();
  return user?.gender === 'male' ? boyTheme : girlTheme;
}
