'use client'

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { securityLifeApi } from '@/services/api/content';
import { basketDefaults } from '@/data/security-life/basketDefaults'

const CASH_LAYER_DEFS = [
  { id: 'T0', name: 'T+0（3-6 月）', desc: '活期/货基/高流动性存款' },
  { id: 'T7', name: 'T+7（6-12 月）', desc: '短久期、波动小、赎回清晰' },
  { id: 'T30', name: 'T+30（6-12 月）', desc: '稳健利率资产梯形配置' },
]

function formatNum(n: number) {
  if (n >= 1e8) return (n / 1e8).toFixed(1) + ' 亿'
  if (n >= 1e4) return (n / 1e4).toFixed(1) + ' 万'
  return n.toLocaleString()
}

export default function BasketsPage() {
  const qc = useQueryClient()

  const { data: basketData, isLoading: loadingBaskets } = useQuery({
    queryKey: ['sl-baskets'],
    queryFn: () => securityLifeApi.getBaskets().then(r => r.data),
  })

  const { data: cashData, isLoading: loadingCash } = useQuery({
    queryKey: ['sl-cash-layers'],
    queryFn: () => securityLifeApi.getCashLayers().then(r => r.data),
  })

  const { data: profileData } = useQuery({
    queryKey: ['sl-profile'],
    queryFn: () => securityLifeApi.getProfile().then(r => r.data),
  })

  const updateBasket = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Record<string, unknown> }) =>
      securityLifeApi.updateBasket(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sl-baskets'] }),
  })

  const updateCashLayers = useMutation({
    mutationFn: (layers: Array<{ layer: string; amount: number; institution?: string; note?: string }>) =>
      securityLifeApi.updateCashLayers({ layers }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sl-cash-layers'] }),
  })

  const updateProfile = useMutation({
    mutationFn: (d: Record<string, unknown>) => securityLifeApi.updateProfile(d),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sl-profile'] }),
  })

  if (loadingBaskets || loadingCash) return <div className="text-center py-12 text-gray-400">加载中...</div>

  const baskets = basketData?.baskets || []
  const total = basketData?.total || 0
  const cashLayers = cashData || []
  const monthlyExpense = profileData?.monthly_expense || 0

  const survivalAmount = baskets.find((b: { basket_id: string }) => b.basket_id === 'survival_cash')?.amount || 0
  const cashMonths = monthlyExpense > 0 ? (survivalAmount / monthlyExpense).toFixed(1) : null

  return (
    <div className="space-y-8">
      <h2 className="text-lg font-bold text-gray-900">资产篮子</h2>

      {/* 月支出 */}
      <section className="rounded-lg border bg-white p-5">
        <h3 className="text-sm font-semibold text-gray-700 mb-3">家庭月支出</h3>
        <div className="flex items-center gap-4">
          <input
            type="number"
            className="border rounded-md px-3 py-2 text-sm w-48"
            defaultValue={monthlyExpense}
            onBlur={e => updateProfile.mutate({ monthly_expense: Number(e.target.value) })}
          />
          <span className="text-sm text-gray-500">元/月</span>
          {cashMonths && (
            <span className="text-sm text-gray-500">
              → 生存现金可撑 <strong className="text-gray-800">{cashMonths}</strong> 月
            </span>
          )}
        </div>
      </section>

      {/* 四大篮子 */}
      <section className="rounded-lg border bg-white p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-gray-700">四大篮子</h3>
          <span className="text-sm text-gray-500">总计：{formatNum(total)}</span>
        </div>
        <div className="space-y-4">
          {basketDefaults.map(def => {
            const b = baskets.find((x: { basket_id: string }) => x.basket_id === def.id)
            const amount = b?.amount || 0
            const pct = total > 0 ? ((amount / total) * 100).toFixed(1) : '0'
            const inRange = total > 0 && Number(pct) >= def.minPercent && Number(pct) <= def.maxPercent

            return (
              <div key={def.id} className="border rounded-lg p-4">
                <div className="flex items-center justify-between mb-2">
                  <div>
                    <span className="text-sm font-semibold text-gray-800">{def.name}</span>
                    <span className="text-xs text-gray-400 ml-2">{def.purpose}</span>
                  </div>
                  <div className="text-right">
                    <span className={`text-sm font-semibold ${inRange ? 'text-green-600' : 'text-gray-800'}`}>
                      {pct}%
                    </span>
                    <span className="text-xs text-gray-400 ml-1">
                      (目标 {def.minPercent}–{def.maxPercent}%)
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <input
                    type="number"
                    className="border rounded-md px-3 py-2 text-sm flex-1"
                    defaultValue={amount}
                    onBlur={e => updateBasket.mutate({ id: def.id, data: { amount: Number(e.target.value) } })}
                  />
                  <span className="text-xs text-gray-400 w-20">{formatNum(amount)}</span>
                </div>
                {/* 进度条 */}
                <div className="mt-2 h-2 bg-gray-100 rounded overflow-hidden">
                  <div
                    className="h-full rounded transition-all"
                    style={{
                      width: `${Math.min(100, Number(pct))}%`,
                      backgroundColor: total === 0 ? '#cbd5e1' : inRange ? '#22c55e' : '#94a3b8',
                    }}
                  />
                </div>
              </div>
            )
          })}
        </div>
      </section>

      {/* 三层现金水库 */}
      <section className="rounded-lg border bg-white p-5">
        <h3 className="text-sm font-semibold text-gray-700 mb-4">三层现金水库</h3>
        <p className="text-xs text-gray-500 mb-4">把现金做成三层水库，明确什么钱在危机里能取出。</p>
        <div className="space-y-4">
          {CASH_LAYER_DEFS.map(def => {
            const layer = (cashLayers as Array<{ layer: string; amount: number; institution: string; note: string }>)
              .find(c => c.layer === def.id)
            return (
              <div key={def.id} className="border rounded-lg p-4">
                <div className="flex items-center justify-between mb-2">
                  <div>
                    <span className="text-sm font-semibold text-gray-800">{def.name}</span>
                    <span className="text-xs text-gray-400 ml-2">{def.desc}</span>
                  </div>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <input
                    type="number"
                    className="border rounded-md px-3 py-2 text-sm"
                    placeholder="金额（元）"
                    defaultValue={layer?.amount || 0}
                    onBlur={e => {
                      const layers = CASH_LAYER_DEFS.map(d => {
                        const existing = (cashLayers as Array<{ layer: string; amount: number; institution: string; note: string }>)
                          .find(c => c.layer === d.id)
                        if (d.id === def.id) {
                          return { layer: d.id, amount: Number(e.target.value), institution: existing?.institution || '', note: existing?.note || '' }
                        }
                        return { layer: d.id, amount: existing?.amount || 0, institution: existing?.institution || '', note: existing?.note || '' }
                      })
                      updateCashLayers.mutate(layers)
                    }}
                  />
                  <input
                    className="border rounded-md px-3 py-2 text-sm"
                    placeholder="存放机构"
                    defaultValue={layer?.institution || ''}
                  />
                  <input
                    className="border rounded-md px-3 py-2 text-sm"
                    placeholder="备注"
                    defaultValue={layer?.note || ''}
                  />
                </div>
              </div>
            )
          })}
        </div>
      </section>
    </div>
  )
}
