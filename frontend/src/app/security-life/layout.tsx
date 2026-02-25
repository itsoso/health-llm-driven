'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import ProtectedRoute from '@/components/ProtectedRoute'
import {
  LayoutDashboard, Layers, PieChart, CheckSquare,
  AlertTriangle, XCircle, Settings
} from 'lucide-react'

const navItems = [
  { href: '/security-life', label: '总览', icon: LayoutDashboard },
  { href: '/security-life/assets', label: '两层资产', icon: Layers },
  { href: '/security-life/baskets', label: '资产篮子', icon: PieChart },
  { href: '/security-life/checklist', label: '90天清单', icon: CheckSquare },
  { href: '/security-life/risk', label: '风险与应对', icon: AlertTriangle },
  { href: '/security-life/dont-list', label: '不要清单', icon: XCircle },
  { href: '/security-life/profile', label: '防御设置', icon: Settings },
]

export default function SecurityLifeLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()

  return (
    <ProtectedRoute>
      <div className="min-h-screen bg-white">
        <div className="max-w-6xl mx-auto px-4 py-6">
          <div className="mb-6">
            <h1 className="text-xl font-bold text-gray-900">资产防御与布局</h1>
            <p className="text-sm text-gray-500 mt-1">基于「反向对冲」思路 · 5 个系统 · 3 条红线 · 90 天上线</p>
          </div>

          {/* 子导航 */}
          <nav className="flex overflow-x-auto gap-1 mb-6 pb-2 border-b border-gray-200">
            {navItems.map(({ href, label, icon: Icon }) => {
              const isActive = pathname === href
              return (
                <Link
                  key={href}
                  href={href}
                  className={`flex items-center gap-1.5 px-3 py-2 rounded-md text-sm font-medium whitespace-nowrap transition-colors ${
                    isActive
                      ? 'bg-gray-900 text-white'
                      : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                  }`}
                >
                  <Icon size={16} />
                  {label}
                </Link>
              )
            })}
          </nav>

          {children}
        </div>
      </div>
    </ProtectedRoute>
  )
}
