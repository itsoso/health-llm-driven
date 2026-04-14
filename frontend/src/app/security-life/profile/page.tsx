'use client'

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { securityLifeApi } from '@/services/api/content';

export default function ProfilePage() {
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['sl-profile'],
    queryFn: () => securityLifeApi.getProfile().then(r => r.data),
  })

  const update = useMutation({
    mutationFn: (d: Record<string, unknown>) => securityLifeApi.updateProfile(d),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sl-profile'] }),
  })

  if (isLoading) return <div className="text-center py-12 text-gray-400">加载中...</div>

  const p = data || {}

  return (
    <div className="space-y-8">
      <h2 className="text-lg font-bold text-gray-900">防御设置</h2>

      <section className="rounded-lg border bg-white p-5 space-y-5">
        <h3 className="text-sm font-semibold text-gray-700">基础信息</h3>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs text-gray-500 mb-1">家庭月支出（元）</label>
            <input
              type="number"
              className="w-full border rounded-md px-3 py-2 text-sm"
              defaultValue={p.monthly_expense || 0}
              onBlur={e => update.mutate({ monthly_expense: Number(e.target.value) })}
            />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">风险偏好</label>
            <select
              className="w-full border rounded-md px-3 py-2 text-sm"
              defaultValue={p.risk_tolerance || 'balanced'}
              onChange={e => update.mutate({ risk_tolerance: e.target.value })}
            >
              <option value="conservative">保守型</option>
              <option value="balanced">平衡型</option>
              <option value="aggressive">进取型</option>
            </select>
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">最大可承受回撤 (%)</label>
            <input
              type="number"
              className="w-full border rounded-md px-3 py-2 text-sm"
              defaultValue={p.max_drawdown_percent || 30}
              onBlur={e => update.mutate({ max_drawdown_percent: Number(e.target.value) })}
            />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">房产占净资产比例 (%)</label>
            <input
              type="number"
              className="w-full border rounded-md px-3 py-2 text-sm"
              defaultValue={p.property_net_asset_ratio || ''}
              onBlur={e => update.mutate({ property_net_asset_ratio: Number(e.target.value) || null })}
            />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">总负债率 (%)</label>
            <input
              type="number"
              className="w-full border rounded-md px-3 py-2 text-sm"
              defaultValue={p.total_debt_ratio || ''}
              onBlur={e => update.mutate({ total_debt_ratio: Number(e.target.value) || null })}
            />
          </div>
        </div>
      </section>

      <section className="rounded-lg border bg-white p-5 space-y-4">
        <h3 className="text-sm font-semibold text-gray-700">家庭情况</h3>
        <div className="space-y-3">
          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              className="h-4 w-4 rounded border-gray-300"
              defaultChecked={p.has_kids_education || false}
              onChange={e => update.mutate({ has_kids_education: e.target.checked })}
            />
            <span className="text-sm text-gray-700">有孩子教育需求</span>
          </label>
          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              className="h-4 w-4 rounded border-gray-300"
              defaultChecked={p.has_elderly_medical || false}
              onChange={e => update.mutate({ has_elderly_medical: e.target.checked })}
            />
            <span className="text-sm text-gray-700">有老人医疗需求</span>
          </label>
          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              className="h-4 w-4 rounded border-gray-300"
              defaultChecked={p.has_investment_property || false}
              onChange={e => update.mutate({ has_investment_property: e.target.checked })}
            />
            <span className="text-sm text-gray-700">有投资房</span>
          </label>
        </div>
      </section>

      <section className="rounded-lg border bg-white p-5">
        <h3 className="text-sm font-semibold text-gray-700 mb-3">备注</h3>
        <textarea
          className="w-full border rounded-md px-3 py-2 text-sm"
          rows={4}
          defaultValue={p.notes || ''}
          onBlur={e => update.mutate({ notes: e.target.value })}
          placeholder="记录你的想法、顾虑或待办..."
        />
      </section>
    </div>
  )
}
