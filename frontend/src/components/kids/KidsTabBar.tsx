'use client';

import Link from 'next/link';

interface KidsTabBarProps {
  currentPath: string;
}

const TABS = [
  { href: '/kids', label: '聊天', icon: '💬' },
  { href: '/kids/checkin', label: '打卡', icon: '✅' },
  { href: '/kids/water', label: '喝水', icon: '💧' },
  { href: '/kids/mood', label: '心情', icon: '😊' },
  { href: '/kids/me', label: '我的', icon: '👤' },
];

export default function KidsTabBar({ currentPath }: KidsTabBarProps) {
  const isActive = (href: string) => {
    if (href === '/kids') return currentPath === '/kids';
    return currentPath.startsWith(href);
  };

  return (
    <nav className="flex-shrink-0 bg-white/90 backdrop-blur-xl border-t-2 border-pink-100 shadow-lg"
      style={{ paddingBottom: 'env(safe-area-inset-bottom, 0px)' }}>
      <div className="flex justify-around items-center h-20 max-w-2xl mx-auto px-4">
        {TABS.map(tab => {
          const active = isActive(tab.href);
          return (
            <Link
              key={tab.href}
              href={tab.href}
              className={`flex flex-col items-center justify-center gap-1 min-w-[64px] min-h-[64px] rounded-2xl transition-all duration-200 ${
                active
                  ? 'bg-pink-100 scale-110 shadow-md'
                  : 'hover:bg-pink-50 active:scale-95'
              }`}
            >
              <span className="text-3xl">
                {tab.icon}
              </span>
              <span className={`text-sm font-bold ${
                active ? 'text-pink-600' : 'text-gray-500'
              }`}>
                {tab.label}
              </span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
