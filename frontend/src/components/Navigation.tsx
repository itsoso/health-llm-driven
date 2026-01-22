'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState, useRef, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';

interface NavItem {
  href: string;
  label: string;
  icon: string;
}

interface NavGroup {
  label: string;
  icon: string;
  items: NavItem[];
}

export default function Navigation() {
  const pathname = usePathname();
  const { user, isAuthenticated, logout, isLoading: authLoading } = useAuth();
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [openDropdown, setOpenDropdown] = useState<string | null>(null);
  const [showUserMenu, setShowUserMenu] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const userMenuRef = useRef<HTMLDivElement>(null);

  // 主要导航项（直接显示）
  const mainNavItems: NavItem[] = [
    { href: '/', label: '首页', icon: '🏠' },
    { href: '/overview', label: '健康概览', icon: '📋' },
    { href: '/daily-insights', label: '今日建议', icon: '💪' },
    { href: '/review', label: '每日复盘', icon: '📝' },
  ];

  // 分组下拉菜单
  const navGroups: NavGroup[] = [
    {
      label: '每日记录',
      icon: '📝',
      items: [
        { href: '/habits', label: '习惯追踪', icon: '✅' },
        { href: '/supplements', label: '补剂管理', icon: '💊' },
        { href: '/checkin', label: '运动打卡', icon: '🏃' },
        { href: '/rhinitis', label: '鼻炎追踪', icon: '🤧' },
        { href: '/diet', label: '饮食记录', icon: '🍽️' },
        { href: '/water', label: '饮水追踪', icon: '💧' },
      ],
    },
    {
      label: '健康追踪',
      icon: '❤️',
      items: [
        { href: '/dashboard', label: '仪表盘', icon: '📊' },
        { href: '/workout', label: '运动训练', icon: '🏋️' },
        { href: '/workout-guidance', label: '运动指导', icon: '🎯' },
        { href: '/heart-rate', label: '心率监测', icon: '❤️' },
        { href: '/weight', label: '体重追踪', icon: '⚖️' },
        { href: '/blood-pressure', label: '血压追踪', icon: '🩺' },
        { href: '/environment', label: '环境健康', icon: '🌤️' },
        { href: '/disease', label: '疾病管理', icon: '🏥' },
      ],
    },
    {
      label: '数据分析',
      icon: '📈',
      items: [
        { href: '/garmin', label: 'Garmin数据', icon: '⌚' },
        { href: '/analysis', label: '健康分析', icon: '🔍' },
      ],
    },
    {
      label: '管理中心',
      icon: '⚙️',
      items: [
        { href: '/goals', label: '目标管理', icon: '🎯' },
        { href: '/medical-exams', label: '体检记录', icon: '🏥' },
        { href: '/data-collection', label: '数据收集', icon: '📥' },
        { href: '/settings', label: '个人设置', icon: '⚙️' },
      ],
    },
  ];

  // 所有导航项（用于移动端）
  const allNavItems: NavItem[] = [
    ...mainNavItems,
    ...navGroups.flatMap((g) => g.items),
  ];

  // 点击外部关闭下拉菜单
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setOpenDropdown(null);
      }
      if (userMenuRef.current && !userMenuRef.current.contains(event.target as Node)) {
        setShowUserMenu(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const isActive = (href: string) => {
    if (href === '/') {
      return pathname === '/';
    }
    return pathname?.startsWith(href);
  };

  const isGroupActive = (group: NavGroup) => {
    return group.items.some((item) => isActive(item.href));
  };

  return (
    <nav className="bg-[#1a1625]/95 backdrop-blur-md border-b border-purple-900/30 shadow-lg sticky top-0 z-50">
      <div className="max-w-[1600px] mx-auto px-3 sm:px-4 lg:px-6">
        <div className="flex justify-between items-center h-14 gap-2">
          {/* Logo和首页链接 */}
          <div className="flex items-center flex-shrink-0 min-w-0">
            <Link
              href="/"
              className="flex items-center space-x-1.5 text-base font-bold text-white hover:text-purple-300 transition-all duration-300 whitespace-nowrap"
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img 
                src="/logo.png" 
                alt="自由是自律的泡沫" 
                width={32} 
                height={32} 
                className="rounded-lg flex-shrink-0"
                onError={(e) => {
                  e.currentTarget.style.display = 'none';
                  const span = document.createElement('span');
                  span.textContent = '🏥';
                  span.className = 'text-lg';
                  e.currentTarget.parentNode?.insertBefore(span, e.currentTarget);
                }}
              />
              <span className="hidden sm:inline text-sm tracking-tight truncate">自由是自律的泡沫</span>
            </Link>
          </div>

          {/* 桌面导航菜单 */}
          <div className="hidden lg:flex lg:items-center lg:gap-0.5 flex-1 justify-end" ref={dropdownRef}>
            {/* 主要导航项 */}
            {mainNavItems.slice(1).map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={`px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 flex items-center gap-1.5 whitespace-nowrap flex-shrink-0 ${
                  isActive(item.href)
                    ? 'bg-purple-600 text-white'
                    : 'text-gray-300 hover:bg-white/10 hover:text-white'
                }`}
              >
                <span className="text-base">{item.icon}</span>
                <span>{item.label}</span>
              </Link>
            ))}

            {/* 分组下拉菜单 */}
            {navGroups.map((group) => (
              <div key={group.label} className="relative flex-shrink-0">
                <button
                  onClick={() => setOpenDropdown(openDropdown === group.label ? null : group.label)}
                  className={`px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 flex items-center gap-1 whitespace-nowrap ${
                    isGroupActive(group)
                      ? 'bg-purple-600 text-white'
                      : 'text-gray-300 hover:bg-white/10 hover:text-white'
                  }`}
                >
                  <span className="text-base">{group.icon}</span>
                  <span>{group.label}</span>
                  <svg
                    className={`w-4 h-4 transition-transform ${openDropdown === group.label ? 'rotate-180' : ''}`}
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </button>

                {/* 下拉菜单内容 */}
                {openDropdown === group.label && (
                  <div className="absolute top-full left-0 mt-1 w-48 bg-[#252033] rounded-xl shadow-2xl border border-purple-900/50 py-2 z-50">
                    {group.items.map((item) => (
                      <Link
                        key={item.href}
                        href={item.href}
                        onClick={() => setOpenDropdown(null)}
                        className={`flex items-center gap-2.5 px-4 py-2.5 text-sm font-medium transition-all ${
                          isActive(item.href)
                            ? 'bg-purple-600/30 text-purple-300'
                            : 'text-gray-300 hover:bg-white/5 hover:text-white'
                        }`}
                      >
                        <span className="text-lg">{item.icon}</span>
                        <span>{item.label}</span>
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            ))}

            {/* 用户菜单 */}
            <div className="relative ml-2 pl-2 border-l border-purple-900/30 flex-shrink-0" ref={userMenuRef}>
              {!authLoading && (
                isAuthenticated ? (
                  <>
                    <button
                      onClick={() => setShowUserMenu(!showUserMenu)}
                      className="flex items-center gap-1.5 px-2 py-2 rounded-lg text-sm font-medium text-gray-300 hover:bg-white/10 hover:text-white transition-all"
                    >
                      <span className="w-7 h-7 bg-purple-600 rounded-full flex items-center justify-center text-white text-sm font-bold flex-shrink-0">
                        {user?.name?.charAt(0) || '?'}
                      </span>
                      <span className="hidden xl:inline truncate max-w-[100px]">{user?.name}</span>
                      <svg className={`w-4 h-4 transition-transform flex-shrink-0 ${showUserMenu ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                      </svg>
                    </button>
                    {showUserMenu && (
                      <div className="absolute top-full right-0 mt-1 w-44 bg-[#252033] rounded-xl shadow-2xl border border-purple-900/50 py-1.5 z-50">
                        <div className="px-3 py-2 border-b border-purple-900/30">
                          <p className="text-sm font-semibold text-white truncate">{user?.name}</p>
                          <p className="text-xs text-gray-400 truncate">{user?.email}</p>
                        </div>
                        <Link
                          href="/settings"
                          onClick={() => setShowUserMenu(false)}
                          className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-gray-300 hover:bg-white/5 hover:text-white transition-all"
                        >
                          <span>⚙️</span>
                          <span>个人设置</span>
                        </Link>
                        <Link
                          href="/profile"
                          onClick={() => setShowUserMenu(false)}
                          className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-gray-300 hover:bg-white/5 hover:text-white transition-all"
                        >
                          <span>👤</span>
                          <span>个人画像</span>
                        </Link>
                        {user?.is_admin && (
                          <>
                            <Link
                              href="/admin"
                              onClick={() => setShowUserMenu(false)}
                              className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-purple-400 hover:bg-purple-600/20 hover:text-purple-300 transition-all"
                            >
                              <span>🛡️</span>
                              <span>管理后台</span>
                            </Link>
                            <Link
                              href="/admin/applications"
                              onClick={() => setShowUserMenu(false)}
                              className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-purple-400 hover:bg-purple-600/20 hover:text-purple-300 transition-all"
                            >
                              <span>🎫</span>
                              <span>邀请码审批</span>
                            </Link>
                            <Link
                              href="/knowledge"
                              onClick={() => setShowUserMenu(false)}
                              className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-purple-400 hover:bg-purple-600/20 hover:text-purple-300 transition-all"
                            >
                              <span>📚</span>
                              <span>知识库管理</span>
                            </Link>
                          </>
                        )}
                        <button
                          onClick={() => { logout(); setShowUserMenu(false); }}
                          className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-red-400 hover:bg-red-600/20 transition-all w-full text-left"
                        >
                          <span>🚪</span>
                          <span>退出登录</span>
                        </button>
                      </div>
                    )}
                  </>
                ) : (
                  <div className="flex items-center gap-2">
                    <Link
                      href="/login"
                      className="px-3 py-2 rounded-lg text-sm font-medium text-gray-300 hover:bg-white/10 hover:text-white transition-all whitespace-nowrap"
                    >
                      登录
                    </Link>
                    <Link
                      href="/register"
                      className="px-3 py-2 rounded-lg text-sm font-medium bg-purple-600 text-white hover:bg-purple-500 transition-all whitespace-nowrap"
                    >
                      注册
                    </Link>
                  </div>
                )
              )}
            </div>
          </div>

          {/* 平板导航菜单 */}
          <div className="hidden md:flex lg:hidden md:items-center md:space-x-0.5">
            {mainNavItems.slice(1).map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={`px-2 py-1.5 rounded-lg text-sm font-medium transition-all duration-200 ${
                  isActive(item.href)
                    ? 'bg-purple-600 text-white'
                    : 'text-gray-300 hover:bg-white/10'
                }`}
                title={item.label}
              >
                <span className="text-base">{item.icon}</span>
              </Link>
            ))}
            {navGroups.flatMap((g) => g.items).slice(0, 4).map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={`px-2 py-1.5 rounded-lg text-sm font-medium transition-all duration-200 ${
                  isActive(item.href)
                    ? 'bg-purple-600 text-white'
                    : 'text-gray-300 hover:bg-white/10'
                }`}
                title={item.label}
              >
                <span className="text-base">{item.icon}</span>
              </Link>
            ))}
          </div>

          {/* 移动端菜单按钮 */}
          <div className="md:hidden">
            <button
              onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
              className="inline-flex items-center justify-center p-2 rounded-lg text-gray-300 hover:text-white hover:bg-white/10 focus:outline-none transition-all duration-200"
            >
              <span className="sr-only">打开主菜单</span>
              {isMobileMenuOpen ? (
                <svg className="block h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              ) : (
                <svg className="block h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
                </svg>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* 移动端下拉菜单 */}
      {isMobileMenuOpen && (
        <div className="md:hidden border-t border-purple-900/30 bg-[#1a1625]/98 backdrop-blur-md shadow-lg max-h-[80vh] overflow-y-auto">
          <div className="px-4 pt-3 pb-4 space-y-1">
            {/* 主要导航 */}
            {mainNavItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setIsMobileMenuOpen(false)}
                className={`flex items-center px-4 py-2.5 rounded-lg text-base font-medium transition-all ${
                  isActive(item.href)
                    ? 'bg-purple-600 text-white'
                    : 'text-gray-300 hover:bg-white/5'
                }`}
              >
                <span className="mr-3 text-lg">{item.icon}</span>
                {item.label}
              </Link>
            ))}

            {/* 分组导航 */}
            {navGroups.map((group) => (
              <div key={group.label} className="pt-2">
                <div className="px-4 py-2 text-xs font-bold text-gray-500 uppercase tracking-wider">
                  {group.icon} {group.label}
                </div>
                {group.items.map((item) => (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={() => setIsMobileMenuOpen(false)}
                    className={`flex items-center px-4 py-2.5 rounded-lg text-base font-medium transition-all ml-2 ${
                      isActive(item.href)
                        ? 'bg-purple-600 text-white'
                        : 'text-gray-300 hover:bg-white/5'
                    }`}
                  >
                    <span className="mr-3 text-lg">{item.icon}</span>
                    {item.label}
                  </Link>
                ))}
              </div>
            ))}

            {/* 移动端用户菜单 */}
            <div className="pt-4 mt-4 border-t border-purple-900/30">
              {!authLoading && (
                isAuthenticated ? (
                  <>
                    <div className="px-4 py-3 flex items-center gap-3">
                      <span className="w-9 h-9 bg-purple-600 rounded-full flex items-center justify-center text-white font-bold text-sm">
                        {user?.name?.charAt(0) || '?'}
                      </span>
                      <div>
                        <p className="font-semibold text-white">{user?.name}</p>
                        <p className="text-sm text-gray-400">{user?.email}</p>
                      </div>
                    </div>
                    <Link
                      href="/settings"
                      onClick={() => setIsMobileMenuOpen(false)}
                      className="flex items-center px-4 py-2.5 rounded-lg text-base font-medium text-gray-300 hover:bg-white/5"
                    >
                      <span className="mr-3 text-lg">⚙️</span>
                      个人设置
                    </Link>
                    <Link
                      href="/profile"
                      onClick={() => setIsMobileMenuOpen(false)}
                      className="flex items-center px-4 py-2.5 rounded-lg text-base font-medium text-gray-300 hover:bg-white/5"
                    >
                      <span className="mr-3 text-lg">👤</span>
                      个人画像
                    </Link>
                    {user?.is_admin && (
                      <>
                        <Link
                          href="/admin"
                          onClick={() => setIsMobileMenuOpen(false)}
                          className="flex items-center px-4 py-2.5 rounded-lg text-base font-medium text-purple-400 hover:bg-purple-600/20"
                        >
                          <span className="mr-3 text-lg">🛡️</span>
                          管理后台
                        </Link>
                        <Link
                          href="/admin/applications"
                          onClick={() => setIsMobileMenuOpen(false)}
                          className="flex items-center px-4 py-2.5 rounded-lg text-base font-medium text-purple-400 hover:bg-purple-600/20"
                        >
                          <span className="mr-3 text-lg">🎫</span>
                          邀请码审批
                        </Link>
                        <Link
                          href="/knowledge"
                          onClick={() => setIsMobileMenuOpen(false)}
                          className="flex items-center px-4 py-2.5 rounded-lg text-base font-medium text-purple-400 hover:bg-purple-600/20"
                        >
                          <span className="mr-3 text-lg">📚</span>
                          知识库管理
                        </Link>
                      </>
                    )}
                    <button
                      onClick={() => { logout(); setIsMobileMenuOpen(false); }}
                      className="flex items-center px-4 py-2.5 rounded-lg text-base font-medium text-red-400 hover:bg-red-600/20 w-full text-left"
                    >
                      <span className="mr-3 text-lg">🚪</span>
                      退出登录
                    </button>
                  </>
                ) : (
                  <div className="flex gap-3 px-4">
                    <Link
                      href="/login"
                      onClick={() => setIsMobileMenuOpen(false)}
                      className="flex-1 py-2.5 text-center rounded-lg text-base font-medium text-gray-300 bg-white/10 hover:bg-white/20"
                    >
                      登录
                    </Link>
                    <Link
                      href="/register"
                      onClick={() => setIsMobileMenuOpen(false)}
                      className="flex-1 py-2.5 text-center rounded-lg text-base font-medium text-white bg-purple-600 hover:bg-purple-500"
                    >
                      注册
                    </Link>
                  </div>
                )
              )}
            </div>
          </div>
        </div>
      )}
    </nav>
  );
}
