'use client';

import Link from 'next/link';
import { useKidsTheme } from '@/contexts/KidsThemeContext';

interface KidsTabBarProps {
  currentPath: string;
}

const TABS = [
  { href: '/kids', label: '聊天', icon: '💬' },
  { href: '/kids/plan', label: '计划', icon: '📋' },
  { href: '/kids/checkin', label: '打卡', icon: '✅' },
  { href: '/kids/vocab', label: '单词', icon: '📖' },
  { href: '/kids/water', label: '喝水', icon: '💧' },
  { href: '/kids/mood', label: '心情', icon: '😊' },
  { href: '/kids/dog', label: '狗狗', icon: '🐾' },
  { href: '/friends', label: '好友', icon: '👫' },
  { href: '/points', label: '积分', icon: '🏆' },
  { href: '/kids/me', label: '我的', icon: '👤' },
];

export default function KidsTabBar({ currentPath }: KidsTabBarProps) {
  const { theme } = useKidsTheme();

  const isActive = (href: string) => {
    if (href === '/kids') return currentPath === '/kids';
    return currentPath.startsWith(href);
  };

  return (
    <nav
      className={`flex-shrink-0 bg-white/90 backdrop-blur-xl border-t-2 ${theme.navBorder} shadow-lg`}
      style={{ paddingBottom: 'env(safe-area-inset-bottom, 0px)' }}
    >
      <div className="flex items-center h-16 max-w-2xl mx-auto px-1 overflow-x-auto scrollbar-hide">
        {TABS.map(tab => {
          const active = isActive(tab.href);
          return (
            <Link
              key={tab.href}
              href={tab.href}
              className={`flex flex-col items-center justify-center gap-0.5 min-w-[36px] min-h-[48px] px-1.5 rounded-2xl transition-all duration-200 flex-shrink-0 ${
                active ? `${theme.tabActiveBg} scale-105 shadow-md` : `${theme.hoverBg} active:scale-95`
              }`}
            >
              <span className="text-lg">{tab.icon}</span>
              <span className={`text-[9px] font-bold ${active ? theme.tabActiveText : 'text-gray-500'}`}>
                {tab.label}
              </span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
