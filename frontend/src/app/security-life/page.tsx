'use client'

import { useQuery } from '@tanstack/react-query'
import Link from 'next/link'
import { securityLifeApi } from '@/services/api'
import { basketDefaults } from '@/data/security-life/basketDefaults'
import { redLineDefinitions } from '@/data/security-life/redLineDefinitions'
import { systemDefinitions } from '@/data/security-life/systemDefinitions'
import { selfTestQuestions } from '@/data/security-life/selfTestQuestions'
import { dontList } from '@/data/security-life/dontList'

function formatNum(n: number): string {
  if (n >= 1e8) return (n / 1e8).toFixed(1) + ' 亿'
  if (n >= 1e4) return (n / 1e4).toFixed(1) + ' 万'
  return n.toLocaleString()
}

function RedLineCard({ lineId, status, definition }: {
  lineId: number
  status: string
  definition: (typeof redLineDefinitions)[0]
}) {
  const colors = {
    met: 'border-green-300 bg-green-50',
    partial: 'border-yellow-300 bg-yellow-50',
    unmet: 'border-red-300 bg-red-50',
  }
  const labels = { met: '已达标', partial: '部分达标', unmet: '未达标' }
  const dots = { met: 'bg-green-500', partial: 'bg-yellow-500', unmet: 'bg-red-500' }
  const s = status as keyof typeof colors

  return (
    <div className={`rounded-lg border-2 p-4 ${colors[s] || colors.unmet}`}>
      <div className="flex items-center gap-2 mb-1">
        <span className={`w-2.5 h-2.5 rounded-full ${dots[s] || dots.unmet}`} />
        <span className="text-xs font-medium text-gray-500">红线 {lineId}</span>
        <span className="text-xs font-semibold ml-auto">{labels[s] || '未达标'}</span>
      </div>
      <p className="text-sm font-semibold text-gray-800">{definition.title}</p>
      <p className="text-xs text-gray-500 mt-1">{definition.target}</p>
    </div>
  )
}

export default function SecurityLifeDashboard() {
  const { data, isLoading } = useQuery({
    queryKey: ['security-life-dashboard'],
    queryFn: () => securityLifeApi.getDashboard().then(r => r.data),
  })

  if (isLoading) {
    return <div className="text-center py-12 text-gray-400">加载中...</div>
  }

  const d = data || {} as Record<string, unknown>
  const redLines = (d.red_lines || []) as Array<{ line_id: number; status: string; value_json?: string }>
  const baskets = (d.baskets || []) as Array<{ basket_id: string; amount: number }>
  const basketTotal = (d.basket_total || 0) as number
  const cashRunway = d.cash_runway_months as number | null
  const secondShare = d.second_layer_share as number | null
  const checklistTotal = (d.checklist_total || 0) as number
  const checklistCompleted = (d.checklist_completed || 0) as number

  return (
    <div className="space-y-8">
      {/* 共识框架 */}
      <section className="rounded-lg border border-gray-200 bg-gray-50 p-4 text-sm text-gray-700">
        <p className="font-semibold text-gray-800 mb-1">共识框架：反向对冲</p>
        <p>
          收入/房产/社交已强绑定中国宏观与长三角区域，金融资产应做「反向对冲」：更流动、更分散对手方、更分散币种/司法辖区。
          目标：现金流不断、资产不被锁死、选择权还在。
        </p>
      </section>

      {/* 三条红线 */}
      <section>
        <h3 className="text-sm font-semibold text-gray-700 mb-3">三条红线</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {redLineDefinitions.map(def => {
            const rl = redLines.find(r => r.line_id === def.id)
            return (
              <RedLineCard
                key={def.id}
                lineId={def.id}
                status={rl?.status || 'unmet'}
                definition={def}
              />
            )
          })}
        </div>
      </section>

      {/* KPI 卡片 */}
      <section className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
          <div className="text-xs text-gray-500">第二层资产占比</div>
          <div className="mt-1 text-2xl font-bold text-gray-800">
            {secondShare != null ? `${secondShare.toFixed(1)}%` : '—'}
          </div>
        </div>
        <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
          <div className="text-xs text-gray-500">生存现金可撑月数</div>
          <div className="mt-1 text-2xl font-bold text-gray-800">
            {cashRunway != null ? `${cashRunway} 月` : '—'}
          </div>
          <p className="text-xs text-gray-400 mt-1">目标 18–24 月</p>
        </div>
        <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
          <div className="text-xs text-gray-500">四大篮子总规模</div>
          <div className="mt-1 text-2xl font-bold text-gray-800">
            {basketTotal > 0 ? formatNum(basketTotal) : '—'}
          </div>
        </div>
        <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
          <div className="text-xs text-gray-500">90 天清单进度</div>
          <div className="mt-1 text-2xl font-bold text-gray-800">
            {checklistCompleted} / {checklistTotal}
          </div>
        </div>
      </section>

      {/* 五大系统 */}
      <section>
        <h3 className="text-sm font-semibold text-gray-700 mb-3">五大系统</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
          {systemDefinitions.map(sys => (
            <div key={sys.id} className="rounded-lg border border-gray-200 bg-white p-3">
              <div className="text-xs text-gray-400 mb-1">系统 {sys.id}</div>
              <div className="text-sm font-semibold text-gray-800">{sys.name}</div>
              <p className="text-xs text-gray-500 mt-1">{sys.description}</p>
            </div>
          ))}
        </div>
      </section>

      {/* 篮子占比 */}
      <section>
        <h3 className="text-sm font-semibold text-gray-700 mb-3">资产篮子占比与建议区间</h3>
        <div className="space-y-2">
          {basketDefaults.map(def => {
            const b = baskets.find(x => x.basket_id === def.id)
            const pct = basketTotal > 0 && b ? (b.amount / basketTotal) * 100 : 0
            const inRange = pct >= def.minPercent && pct <= def.maxPercent
            return (
              <div key={def.id} className="flex items-center gap-3">
                <span className="w-24 text-sm text-gray-600 shrink-0">{def.name}</span>
                <div className="flex-1 h-5 bg-gray-100 rounded overflow-hidden">
                  <div
                    className="h-full rounded transition-all"
                    style={{
                      width: `${Math.min(100, pct)}%`,
                      backgroundColor: basketTotal === 0 ? '#cbd5e1'
                        : inRange ? '#22c55e' : pct > def.maxPercent ? '#eab308' : '#94a3b8',
                    }}
                  />
                </div>
                <span className="text-xs text-gray-500 w-36 text-right">
                  {pct.toFixed(0)}%（建议 {def.minPercent}–{def.maxPercent}%）
                </span>
              </div>
            )
          })}
        </div>
      </section>

      {/* 自测三问 */}
      <section className="rounded-lg border border-amber-200 bg-amber-50/60 p-4">
        <h3 className="text-sm font-semibold text-gray-700 mb-2">自测三问</h3>
        <p className="text-xs text-gray-500 mb-2">三问都答「是」，则比多数高净值家庭更安全。</p>
        <ul className="space-y-2 text-sm text-gray-700">
          {selfTestQuestions.map((q, i) => (
            <li key={i} className="flex gap-2">
              <span className="shrink-0 font-semibold">{i + 1}.</span>
              {q}
            </li>
          ))}
        </ul>
      </section>

      {/* 不要清单摘要 */}
      <section>
        <h3 className="text-sm font-semibold text-gray-700 mb-2">不要清单</h3>
        <ul className="space-y-1 text-sm text-gray-600">
          {dontList.slice(0, 3).map(item => (
            <li key={item.id}>· {item.text}</li>
          ))}
        </ul>
        <Link
          href="/security-life/dont-list"
          className="mt-2 inline-block text-sm font-medium text-blue-600 hover:text-blue-800"
        >
          查看全部 {dontList.length} 条 →
        </Link>
      </section>

      {/* 快速入口 */}
      <section>
        <h3 className="text-sm font-semibold text-gray-700 mb-3">快速入口</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[
            { href: '/security-life/assets', label: '两层资产', desc: '第一层与第二层录入与占比' },
            { href: '/security-life/baskets', label: '资产篮子', desc: '四大篮子 + 三层现金水库' },
            { href: '/security-life/checklist', label: '90天清单', desc: '5系统 × 3阶段，可自定义' },
            { href: '/security-life/risk', label: '风险与应对', desc: '6 点风险、6 个盲点、4 个风控动作' },
            { href: '/security-life/dont-list', label: '不要清单', desc: '6 条「不要」常驻展示' },
            { href: '/security-life/profile', label: '防御设置', desc: '月支出、风险偏好、家庭情况' },
          ].map(({ href, label, desc }) => (
            <Link
              key={href}
              href={href}
              className="block p-4 rounded-lg border border-gray-200 bg-white hover:border-gray-300 hover:shadow-sm transition-shadow"
            >
              <span className="font-semibold text-gray-800">{label}</span>
              <p className="mt-1 text-sm text-gray-500">{desc}</p>
            </Link>
          ))}
        </div>
      </section>
    </div>
  )
}
