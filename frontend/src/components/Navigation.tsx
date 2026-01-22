'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState, useRef, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import {
  Home,
  LayoutDashboard,
  Sparkles,
  Heart,
  Activity,
  Dumbbell,
  Target,
  Scale,
  CloudSun,
  ClipboardList,
  CheckSquare,
  Pill,
  Flag,
  Wind,
  Utensils,
  Droplets,
  Watch,
  LineChart,
  BookOpen,
  Settings,
  FileText,
  Database,
  ChevronDown,
  User,
  LogOut,
  Shield,
  Ticket,
  Book,
  Menu,
  X,
  Stethoscope,
  Thermometer
} from 'lucide-react';

interface NavItem {
  href: string;
  label: string;
  icon: React.ReactNode;
}

interface NavGroup {
  label: string;
  icon: React.ReactNode;
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
    { href: '/', label: '首页', icon: <Home className="w-4 h-4" /> },
    { href: '/overview', label: '健康概览', icon: <LayoutDashboard className="w-4 h-4" /> },
    { href: '/daily-insights', label: '今日建议', icon: <Sparkles className="w-4 h-4" /> },
  ];

  // 分组下拉菜单
  const navGroups: NavGroup[] = [
    {
      label: '健康追踪',
      icon: <Heart className="w-4 h-4" />,
      items: [
        { href: '/dashboard', label: '仪表盘', icon: <Activity className="w-4 h-4" /> },
        { href: '/workout', label: '运动训练', icon: <Dumbbell className="w-4 h-4" /> },
        { href: '/workout-guidance', label: '运动指导', icon: <Target className="w-4 h-4" /> },
        { href: '/heart-rate', label: '心率监测', icon: <Heart className="w-4 h-4" /> },
        { href: '/weight', label: '体重追踪', icon: <Scale className="w-4 h-4" /> },
        { href: '/blood-pressure', label: '血压追踪', icon: <Activity className="w-4 h-4" /> },
        { href: '/environment', label: '环境健康', icon: <CloudSun className="w-4 h-4" /> },
        { href: '/disease', label: '疾病管理', icon: <Thermometer className="w-4 h-4" /> },
      ],
    },
    {
      label: '每日记录',
      icon: <ClipboardList className="w-4 h-4" />,
      items: [
        { href: '/supplements', label: '补剂管理', icon: <Pill className="w-4 h-4" /> },
        { href: '/checkin', label: '运动打卡', icon: <Flag className="w-4 h-4" /> },
        { href: '/rhinitis', label: '鼻炎追踪', icon: <Wind className="w-4 h-4" /> },
        { href: '/diet', label: '饮食记录', icon: <Utensils className="w-4 h-4" /> },
        { href: '/diet-recommendation', label: '饮食推荐', icon: <Sparkles className="w-4 h-4" /> },
        { href: '/water', label: '饮水追踪', icon: <Droplets className="w-4 h-4" /> },
        { href: '/garmin', label: 'Garmin数据', icon: <Watch className="w-4 h-4" /> },
        { href: '/analysis', label: '健康分析', icon: <LineChart className="w-4 h-4" /> },
      ],
    },
    {
      label: '每日复盘',
      icon: <BookOpen className="w-4 h-4" />,
      items: [
        { href: '/review', label: '每日复盘', icon: <BookOpen className="w-4 h-4" /> },
      ],
    },
    {
      label: '管理中心',
      icon: <Settings className="w-4 h-4" />,
      items: [
        { href: '/goals', label: '目标管理', icon: <Target className="w-4 h-4" /> },
        { href: '/medical-exams', label: '体检记录', icon: <FileText className="w-4 h-4" /> },
        { href: '/data-collection', label: '数据收集', icon: <Database className="w-4 h-4" /> },
        { href: '/settings', label: '个人设置', icon: <Settings className="w-4 h-4" /> },
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
    <nav className="bg-[#1a1625]/90 backdrop-blur-xl border-b border-purple-900/20 shadow-sm sticky top-0 z-50 font-sans">
      <div className="max-w-[1600px] mx-auto px-4 lg:px-6">
        <div className="flex justify-between items-center h-16 gap-4">
          {/* Logo和首页链接 */}
          <div className="flex items-center flex-shrink-0 min-w-0">
            <Link
              href="/"
              className="flex items-center space-x-2 text-base font-bold text-white hover:text-purple-300 transition-all duration-300 whitespace-nowrap group"
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img 
                src="/logo.png" 
                alt="自由是自律的泡沫" 
                width={32} 
                height={32} 
                className="rounded-lg flex-shrink-0 shadow-md group-hover:shadow-purple-500/20 transition-all"
                onError={(e) => {
                  e.currentTarget.style.display = 'none';
                  const span = document.createElement('span');
                  span.textContent = '🏥';
                  span.className = 'text-lg';
                  e.currentTarget.parentNode?.insertBefore(span, e.currentTarget);
                }}
              />
              <span className="hidden sm:inline text-xl tracking-wide font-semibold text-gray-100 group-hover:text-white transition-colors">自由是自律的泡沫</span>
            </Link>
          </div>

          {/* 桌面导航菜单 */}
          <div className="hidden lg:flex lg:items-center lg:gap-1 flex-1 justify-end" ref={dropdownRef}>
            {/* 主要导航项 */}
            {mainNavItems.slice(1).map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={`px-3 py-2 rounded-md text-lg font-medium transition-all duration-200 flex items-center gap-2 whitespace-nowrap flex-shrink-0 ${
                  isActive(item.href)
                    ? 'bg-purple-600/90 text-white shadow-sm'
                    : 'text-gray-300 hover:bg-white/5 hover:text-white'
                }`}
              >
                {item.icon}
                <span>{item.label}</span>
              </Link>
            ))}

            {/* 分组下拉菜单 */}
            {navGroups.map((group) => (
              <div key={group.label} className="relative flex-shrink-0">
                <button
                  onClick={() => setOpenDropdown(openDropdown === group.label ? null : group.label)}
                  className={`px-3 py-2 rounded-md text-lg font-medium transition-all duration-200 flex items-center gap-1.5 whitespace-nowrap ${
                    isGroupActive(group)
                      ? 'bg-purple-600/90 text-white shadow-sm'
                      : 'text-gray-300 hover:bg-white/5 hover:text-white'
                  }`}
                >
                  {group.icon}
                  <span>{group.label}</span>
                  <ChevronDown
                    className={`w-3.5 h-3.5 transition-transform duration-200 ${openDropdown === group.label ? 'rotate-180' : ''}`}
                  />
                </button>

                {/* 下拉菜单内容 */}
                {openDropdown === group.label && (
                  <div className="absolute top-full left-0 mt-2 w-52 bg-[#252033] rounded-lg shadow-xl border border-purple-900/40 py-1.5 z-50 backdrop-blur-3xl animate-in fade-in zoom-in-95 duration-100">
                    {group.items.map((item) => (
                      <Link
                        key={item.href}
                        href={item.href}
                        onClick={() => setOpenDropdown(null)}
                        className={`flex items-center gap-3 px-4 py-2.5 text-lg font-medium transition-all ${
                          isActive(item.href)
                            ? 'bg-purple-600/20 text-purple-300'
                            : 'text-gray-300 hover:bg-white/5 hover:text-white'
                        }`}
                      >
                        <span className="text-gray-400 group-hover:text-white">{item.icon}</span>
                        <span>{item.label}</span>
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            ))}

            {/* 用户菜单 */}
            <div className="relative ml-3 pl-3 border-l border-purple-900/30 flex-shrink-0" ref={userMenuRef}>
              {!authLoading && (
                isAuthenticated ? (
                  <>
                    <button
                      onClick={() => setShowUserMenu(!showUserMenu)}
                      className="flex items-center gap-2 px-2 py-1.5 rounded-full text-lg font-medium text-gray-300 hover:bg-white/5 hover:text-white transition-all border border-transparent hover:border-purple-500/30"
                    >
                      <span className="w-8 h-8 bg-gradient-to-br from-purple-500 to-purple-700 rounded-full flex items-center justify-center text-white text-xs font-bold flex-shrink-0 shadow-inner">
                        {user?.name?.charAt(0) || '?'}
                      </span>
                      <span className="hidden xl:inline truncate max-w-[100px] text-base font-medium tracking-wide">{user?.name}</span>
                      <ChevronDown className={`w-3.5 h-3.5 transition-transform duration-200 ${showUserMenu ? 'rotate-180' : ''}`} />
                    </button>
                    {showUserMenu && (
                      <div className="absolute top-full right-0 mt-2 w-56 bg-[#252033] rounded-lg shadow-xl border border-purple-900/40 py-1.5 z-50 backdrop-blur-3xl animate-in fade-in zoom-in-95 duration-100">
                        <div className="px-4 py-3 border-b border-purple-900/30">
                          <p className="text-base font-semibold text-white truncate">{user?.name}</p>
                          <p className="text-sm text-gray-400 truncate font-mono mt-0.5">{user?.email}</p>
                        </div>
                        <div className="py-1">
                          <Link
                            href="/settings"
                            onClick={() => setShowUserMenu(false)}
                            className="flex items-center gap-3 px-4 py-2 text-lg font-medium text-gray-300 hover:bg-white/5 hover:text-white transition-all"
                          >
                            <Settings className="w-4 h-4" />
                            <span>个人设置</span>
                          </Link>
                          <Link
                            href="/profile"
                            onClick={() => setShowUserMenu(false)}
                            className="flex items-center gap-3 px-4 py-2 text-lg font-medium text-gray-300 hover:bg-white/5 hover:text-white transition-all"
                          >
                            <User className="w-4 h-4" />
                            <span>个人画像</span>
                          </Link>
                        </div>
                        {user?.is_admin && (
                          <div className="border-t border-purple-900/30 py-1">
                            <Link
                              href="/admin"
                              onClick={() => setShowUserMenu(false)}
                              className="flex items-center gap-3 px-4 py-2 text-lg font-medium text-purple-400 hover:bg-purple-600/10 hover:text-purple-300 transition-all"
                            >
                              <Shield className="w-4 h-4" />
                              <span>管理后台</span>
                            </Link>
                            <Link
                              href="/admin/applications"
                              onClick={() => setShowUserMenu(false)}
                              className="flex items-center gap-3 px-4 py-2 text-lg font-medium text-purple-400 hover:bg-purple-600/10 hover:text-purple-300 transition-all"
                            >
                              <Ticket className="w-4 h-4" />
                              <span>邀请码审批</span>
                            </Link>
                            <Link
                              href="/knowledge"
                              onClick={() => setShowUserMenu(false)}
                              className="flex items-center gap-3 px-4 py-2 text-lg font-medium text-purple-400 hover:bg-purple-600/10 hover:text-purple-300 transition-all"
                            >
                              <Book className="w-4 h-4" />
                              <span>知识库管理</span>
                            </Link>
                          </div>
                        )}
                        <div className="border-t border-purple-900/30 py-1">
                          <button
                            onClick={() => { logout(); setShowUserMenu(false); }}
                            className="flex items-center gap-3 px-4 py-2 text-lg font-medium text-red-400 hover:bg-red-600/10 transition-all w-full text-left"
                          >
                            <LogOut className="w-4 h-4" />
                            <span>退出登录</span>
                          </button>
                        </div>
                      </div>
                    )}
                  </>
                ) : (
                  <div className="flex items-center gap-3">
                    <Link
                      href="/login"
                      className="px-4 py-2 rounded-md text-lg font-medium text-gray-300 hover:bg-white/10 hover:text-white transition-all whitespace-nowrap"
                    >
                      登录
                    </Link>
                    <Link
                      href="/register"
                      className="px-4 py-2 rounded-md text-lg font-medium bg-purple-600 text-white hover:bg-purple-500 transition-all whitespace-nowrap shadow-lg shadow-purple-900/20"
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
                className={`p-2 rounded-md text-sm font-medium transition-all duration-200 ${
                  isActive(item.href)
                    ? 'bg-purple-600/90 text-white shadow-sm'
                    : 'text-gray-300 hover:bg-white/10'
                }`}
                title={item.label}
              >
                {item.icon}
              </Link>
            ))}
            {navGroups.flatMap((g) => g.items).slice(0, 4).map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={`p-2 rounded-md text-sm font-medium transition-all duration-200 ${
                  isActive(item.href)
                    ? 'bg-purple-600/90 text-white shadow-sm'
                    : 'text-gray-300 hover:bg-white/10'
                }`}
                title={item.label}
              >
                {item.icon}
              </Link>
            ))}
          </div>

          {/* 移动端菜单按钮 */}
          <div className="md:hidden">
            <button
              onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
              className="inline-flex items-center justify-center p-2 rounded-md text-gray-300 hover:text-white hover:bg-white/10 focus:outline-none transition-all duration-200"
            >
              <span className="sr-only">打开主菜单</span>
              {isMobileMenuOpen ? (
                <X className="block h-6 w-6" />
              ) : (
                <Menu className="block h-6 w-6" />
              )}
            </button>
          </div>
        </div>
      </div>

      {/* 移动端下拉菜单 */}
      {isMobileMenuOpen && (
        <div className="md:hidden border-t border-purple-900/30 bg-[#1a1625]/95 backdrop-blur-xl shadow-lg max-h-[85vh] overflow-y-auto">
          <div className="px-4 pt-4 pb-6 space-y-2">
            {/* 主要导航 */}
            {mainNavItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setIsMobileMenuOpen(false)}
                className={`flex items-center px-4 py-3 rounded-lg text-base font-medium transition-all ${
                  isActive(item.href)
                    ? 'bg-purple-600/90 text-white shadow-sm'
                    : 'text-gray-300 hover:bg-white/5'
                }`}
              >
                <span className="mr-3">{item.icon}</span>
                {item.label}
              </Link>
            ))}

            {/* 分组导航 */}
            {navGroups.map((group) => (
              <div key={group.label} className="pt-3">
                <div className="px-4 py-2 text-xs font-bold text-gray-500 uppercase tracking-wider flex items-center gap-2">
                  {group.icon} {group.label}
                </div>
                <div className="space-y-1 mt-1">
                  {group.items.map((item) => (
                    <Link
                      key={item.href}
                      href={item.href}
                      onClick={() => setIsMobileMenuOpen(false)}
                      className={`flex items-center px-4 py-3 rounded-lg text-base font-medium transition-all ml-2 ${
                        isActive(item.href)
                          ? 'bg-purple-600/90 text-white shadow-sm'
                          : 'text-gray-300 hover:bg-white/5'
                      }`}
                    >
                      <span className="mr-3">{item.icon}</span>
                      {item.label}
                    </Link>
                  ))}
                </div>
              </div>
            ))}

            {/* 移动端用户菜单 */}
            <div className="pt-6 mt-6 border-t border-purple-900/30">
              {!authLoading && (
                isAuthenticated ? (
                  <>
                    <div className="px-4 py-3 flex items-center gap-3 mb-2">
                      <span className="w-10 h-10 bg-gradient-to-br from-purple-500 to-purple-700 rounded-full flex items-center justify-center text-white font-bold text-sm shadow-inner">
                        {user?.name?.charAt(0) || '?'}
                      </span>
                      <div>
                        <p className="font-semibold text-white">{user?.name}</p>
                        <p className="text-sm text-gray-400 font-mono">{user?.email}</p>
                      </div>
                    </div>
                    <Link
                      href="/settings"
                      onClick={() => setIsMobileMenuOpen(false)}
                      className="flex items-center px-4 py-3 rounded-lg text-lg font-medium text-gray-300 hover:bg-white/5"
                    >
                      <Settings className="mr-3 w-5 h-5" />
                      个人设置
                    </Link>
                    <Link
                      href="/profile"
                      onClick={() => setIsMobileMenuOpen(false)}
                      className="flex items-center px-4 py-3 rounded-lg text-lg font-medium text-gray-300 hover:bg-white/5"
                    >
                      <User className="mr-3 w-5 h-5" />
                      个人画像
                    </Link>
                    {user?.is_admin && (
                      <>
                        <Link
                          href="/admin"
                          onClick={() => setIsMobileMenuOpen(false)}
                          className="flex items-center px-4 py-3 rounded-lg text-lg font-medium text-purple-400 hover:bg-purple-600/10"
                        >
                          <Shield className="mr-3 w-5 h-5" />
                          管理后台
                        </Link>
                        <Link
                          href="/admin/applications"
                          onClick={() => setIsMobileMenuOpen(false)}
                          className="flex items-center px-4 py-3 rounded-lg text-lg font-medium text-purple-400 hover:bg-purple-600/10"
                        >
                          <Ticket className="mr-3 w-5 h-5" />
                          邀请码审批
                        </Link>
                        <Link
                          href="/knowledge"
                          onClick={() => setIsMobileMenuOpen(false)}
                          className="flex items-center px-4 py-3 rounded-lg text-lg font-medium text-purple-400 hover:bg-purple-600/10"
                        >
                          <Book className="mr-3 w-5 h-5" />
                          知识库管理
                        </Link>
                      </>
                    )}
                    <button
                      onClick={() => { logout(); setIsMobileMenuOpen(false); }}
                      className="flex items-center px-4 py-3 rounded-lg text-lg font-medium text-red-400 hover:bg-red-600/10 w-full text-left mt-2"
                    >
                      <LogOut className="mr-3 w-5 h-5" />
                      退出登录
                    </button>
                  </>
                ) : (
                  <div className="flex gap-3 px-4">
                    <Link
                      href="/login"
                      onClick={() => setIsMobileMenuOpen(false)}
                      className="flex-1 py-3 text-center rounded-lg text-lg font-medium text-gray-300 bg-white/10 hover:bg-white/20"
                    >
                      登录
                    </Link>
                    <Link
                      href="/register"
                      onClick={() => setIsMobileMenuOpen(false)}
                      className="flex-1 py-3 text-center rounded-lg text-lg font-medium text-white bg-purple-600 hover:bg-purple-500 shadow-lg"
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