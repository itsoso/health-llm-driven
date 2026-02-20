'use client';

import Link from 'next/link';

interface KidsTabBarProps {
  currentPath: string;
  isBoy?: boolean;
}

const TABS = [
  { href: '/kids', label: '聊天', icon: '💬' },
  { href: '/kids/plan', label: '计划', icon: '📋' },
  { href: '/kids/checkin', label: '打卡', icon: '✅' },
  { href: '/kids/water', label: '喝水', icon: '💧' },
  { href: '/kids/mood', label: '心情', icon: '😊' },
  { href: '/kids/me', label: '我的', icon: '👤' },
];

export default function KidsTabBar({ currentPath, isBoy = false }: KidsTabBarProps) {
  const isActive = (href: string) => {
    if (href === '/kids') return currentPath === '/kids';
    return currentPath.startsWith(href);
  };

  const activeBg = isBoy ? 'bg-blue-100' : 'bg-pink-100';
  const activeText = isBoy ? 'text-blue-600' : 'text-pink-600';
  const navBorder = isBoy ? 'border-blue-100' : 'border-pink-100';
  const hoverBg = isBoy ? 'hover:bg-blue-50' : 'hover:bg-pink-50';

  return (
    <nav
      className={`flex-shrink-0 bg-white/90 backdrop-blur-xl border-t-2 ${navBorder} shadow-lg`}
      style={{ paddingBottom: 'env(safe-area-inset-bottom, 0px)' }}
    >
      <div className="flex justify-around items-center h-20 max-w-2xl mx-auto px-2">
        {TABS.map(tab => {
          const active = isActive(tab.href);
          return (
            <Link
              key={tab.href}
              href={tab.href}
              className={`flex flex-col items-center justify-center gap-0.5 min-w-[44px] min-h-[56px] px-1 rounded-2xl transition-all duration-200 ${
                active ? `${activeBg} scale-110 shadow-md` : `${hoverBg} active:scale-95`
              }`}
            >
              <span className="text-2xl">{tab.icon}</span>
              <span className={`text-xs font-bold ${active ? activeText : 'text-gray-500'}`}>
                {tab.label}
              </span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
