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
    { href: '/daily-insights', label: '今日建议', icon: '💪' },
    { href: '/dashboard', label: '仪表盘', icon: '📊' },
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
        { href: '/diet', label: '饮食记录', icon: '🍽️' },
        { href: '/water', label: '饮水追踪', icon: '💧' },
      ],
    },
    {
      label: '健康追踪',
      icon: '❤️',
      items: [
        { href: '/heart-rate', label: '心率监测', icon: '❤️' },
        { href: '/weight', label: '体重追踪', icon: '⚖️' },
        { href: '/blood-pressure', label: '血压追踪', icon: '🩺' },
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
    <nav className="bg-white/95 backdrop-blur-md border-b border-indigo-200/50 shadow-md sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between items-center h-16 gap-4">
          {/* Logo和首页链接 */}
          <div className="flex items-center flex-shrink-0">
            <Link
              href="/"
              className="flex items-center space-x-2 text-xl font-extrabold bg-gradient-to-r from-indigo-600 via-purple-600 to-purple-700 bg-clip-text text-transparent hover:from-indigo-700 hover:via-purple-700 hover:to-purple-800 transition-all duration-300 whitespace-nowrap"
            >
              <span className="text-2xl">🏥</span>
              <span className="hidden sm:inline tracking-tight">健康自律靠AI</span>
            </Link>
          </div>

          {/* 桌面导航菜单 */}
          <div className="hidden lg:flex lg:items-center lg:space-x-1" ref={dropdownRef}>
            {/* 主要导航项 */}
            {mainNavItems.slice(1).map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={`px-3 py-2 rounded-lg text-sm font-semibold transition-all duration-200 flex items-center gap-1.5 ${
                  isActive(item.href)
                    ? 'bg-gradient-to-r from-indigo-500 to-purple-500 text-white shadow-md'
                    : 'text-gray-700 hover:bg-indigo-50 hover:text-indigo-700'
                }`}
              >
                <span>{item.icon}</span>
                <span>{item.label}</span>
              </Link>
            ))}

            {/* 分组下拉菜单 */}
            {navGroups.map((group) => (
              <div key={group.label} className="relative">
                <button
                  onClick={() => setOpenDropdown(openDropdown === group.label ? null : group.label)}
                  className={`px-3 py-2 rounded-lg text-sm font-semibold transition-all duration-200 flex items-center gap-1.5 ${
                    isGroupActive(group)
                      ? 'bg-gradient-to-r from-indigo-500 to-purple-500 text-white shadow-md'
                      : 'text-gray-700 hover:bg-indigo-50 hover:text-indigo-700'
                  }`}
                >
                  <span>{group.icon}</span>
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
                  <div className="absolute top-full left-0 mt-1 w-48 bg-white rounded-xl shadow-xl border border-gray-200 py-2 z-50">
                    {group.items.map((item) => (
                      <Link
                        key={item.href}
                        href={item.href}
                        onClick={() => setOpenDropdown(null)}
                        className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium transition-all ${
                          isActive(item.href)
                            ? 'bg-indigo-50 text-indigo-700'
                            : 'text-gray-700 hover:bg-gray-50 hover:text-indigo-600'
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
            <div className="relative ml-2 pl-2 border-l border-gray-200" ref={userMenuRef}>
              {!authLoading && (
                isAuthenticated ? (
                  <>
                    <button
                      onClick={() => setShowUserMenu(!showUserMenu)}
                      className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-semibold text-gray-700 hover:bg-indigo-50 hover:text-indigo-700 transition-all"
                    >
                      <span className="w-8 h-8 bg-gradient-to-r from-indigo-500 to-purple-500 rounded-full flex items-center justify-center text-white text-sm font-bold">
                        {user?.name?.charAt(0) || '?'}
                      </span>
                      <span className="hidden xl:inline">{user?.name}</span>
                      <svg className={`w-4 h-4 transition-transform ${showUserMenu ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                      </svg>
                    </button>
                    {showUserMenu && (
                      <div className="absolute top-full right-0 mt-1 w-48 bg-white rounded-xl shadow-xl border border-gray-200 py-2 z-50">
                        <div className="px-4 py-2 border-b border-gray-100">
                          <p className="text-sm font-semibold text-gray-900">{user?.name}</p>
                          <p className="text-xs text-gray-500">{user?.email}</p>
                        </div>
                        <Link
                          href="/settings"
                          onClick={() => setShowUserMenu(false)}
                          className="flex items-center gap-2 px-4 py-2.5 text-sm font-medium text-gray-700 hover:bg-gray-50 hover:text-indigo-600 transition-all"
                        >
                          <span>⚙️</span>
                          <span>个人设置</span>
                        </Link>
                        {user?.is_admin && (
                          <Link
                            href="/admin"
                            onClick={() => setShowUserMenu(false)}
                            className="flex items-center gap-2 px-4 py-2.5 text-sm font-medium text-purple-700 hover:bg-purple-50 hover:text-purple-800 transition-all"
                          >
                            <span>🛡️</span>
                            <span>管理后台</span>
                          </Link>
                        )}
                        <button
                          onClick={() => { logout(); setShowUserMenu(false); }}
                          className="flex items-center gap-2 px-4 py-2.5 text-sm font-medium text-red-600 hover:bg-red-50 transition-all w-full text-left"
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
                      className="px-3 py-2 rounded-lg text-sm font-semibold text-gray-700 hover:bg-indigo-50 hover:text-indigo-700 transition-all"
                    >
                      登录
                    </Link>
                    <Link
                      href="/register"
                      className="px-3 py-2 rounded-lg text-sm font-semibold bg-gradient-to-r from-indigo-500 to-purple-500 text-white hover:from-indigo-600 hover:to-purple-600 transition-all shadow-md"
                    >
                      注册
                    </Link>
                  </div>
                )
              )}
            </div>
          </div>

          {/* 平板导航菜单 */}
          <div className="hidden md:flex lg:hidden md:items-center md:space-x-1">
            {mainNavItems.slice(1).map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={`px-2 py-2 rounded-lg text-sm font-semibold transition-all duration-200 ${
                  isActive(item.href)
                    ? 'bg-gradient-to-r from-indigo-500 to-purple-500 text-white shadow-md'
                    : 'text-gray-700 hover:bg-indigo-50'
                }`}
                title={item.label}
              >
                <span className="text-lg">{item.icon}</span>
              </Link>
            ))}
            {navGroups.flatMap((g) => g.items).slice(0, 4).map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={`px-2 py-2 rounded-lg text-sm font-semibold transition-all duration-200 ${
                  isActive(item.href)
                    ? 'bg-gradient-to-r from-indigo-500 to-purple-500 text-white shadow-md'
                    : 'text-gray-700 hover:bg-indigo-50'
                }`}
                title={item.label}
              >
                <span className="text-lg">{item.icon}</span>
              </Link>
            ))}
          </div>

          {/* 移动端菜单按钮 */}
          <div className="md:hidden">
            <button
              onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
              className="inline-flex items-center justify-center p-2 rounded-lg text-gray-700 hover:text-indigo-600 hover:bg-indigo-50 focus:outline-none transition-all duration-200"
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
        <div className="md:hidden border-t border-indigo-200/50 bg-white/95 backdrop-blur-md shadow-lg max-h-[80vh] overflow-y-auto">
          <div className="px-4 pt-3 pb-4 space-y-1">
            {/* 主要导航 */}
            {mainNavItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setIsMobileMenuOpen(false)}
                className={`flex items-center px-4 py-3 rounded-lg text-base font-semibold transition-all ${
                  isActive(item.href)
                    ? 'bg-gradient-to-r from-indigo-500 to-purple-500 text-white shadow-md'
                    : 'text-gray-700 hover:bg-indigo-50'
                }`}
              >
                <span className="mr-3 text-xl">{item.icon}</span>
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
                    className={`flex items-center px-4 py-3 rounded-lg text-base font-semibold transition-all ml-2 ${
                      isActive(item.href)
                        ? 'bg-gradient-to-r from-indigo-500 to-purple-500 text-white shadow-md'
                        : 'text-gray-700 hover:bg-indigo-50'
                    }`}
                  >
                    <span className="mr-3 text-xl">{item.icon}</span>
                    {item.label}
                  </Link>
                ))}
              </div>
            ))}

            {/* 移动端用户菜单 */}
            <div className="pt-4 mt-4 border-t border-gray-200">
              {!authLoading && (
                isAuthenticated ? (
                  <>
                    <div className="px-4 py-3 flex items-center gap-3">
                      <span className="w-10 h-10 bg-gradient-to-r from-indigo-500 to-purple-500 rounded-full flex items-center justify-center text-white font-bold">
                        {user?.name?.charAt(0) || '?'}
                      </span>
                      <div>
                        <p className="font-semibold text-gray-900">{user?.name}</p>
                        <p className="text-sm text-gray-500">{user?.email}</p>
                      </div>
                    </div>
                    <Link
                      href="/settings"
                      onClick={() => setIsMobileMenuOpen(false)}
                      className="flex items-center px-4 py-3 rounded-lg text-base font-semibold text-gray-700 hover:bg-indigo-50"
                    >
                      <span className="mr-3 text-xl">⚙️</span>
                      个人设置
                    </Link>
                    {user?.is_admin && (
                      <Link
                        href="/admin"
                        onClick={() => setIsMobileMenuOpen(false)}
                        className="flex items-center px-4 py-3 rounded-lg text-base font-semibold text-purple-700 hover:bg-purple-50"
                      >
                        <span className="mr-3 text-xl">🛡️</span>
                        管理后台
                      </Link>
                    )}
                    <button
                      onClick={() => { logout(); setIsMobileMenuOpen(false); }}
                      className="flex items-center px-4 py-3 rounded-lg text-base font-semibold text-red-600 hover:bg-red-50 w-full text-left"
                    >
                      <span className="mr-3 text-xl">🚪</span>
                      退出登录
                    </button>
                  </>
                ) : (
                  <div className="flex gap-3 px-4">
                    <Link
                      href="/login"
                      onClick={() => setIsMobileMenuOpen(false)}
                      className="flex-1 py-3 text-center rounded-lg text-base font-semibold text-gray-700 bg-gray-100 hover:bg-gray-200"
                    >
                      登录
                    </Link>
                    <Link
                      href="/register"
                      onClick={() => setIsMobileMenuOpen(false)}
                      className="flex-1 py-3 text-center rounded-lg text-base font-semibold text-white bg-gradient-to-r from-indigo-500 to-purple-500 hover:from-indigo-600 hover:to-purple-600"
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
