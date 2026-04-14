'use client'

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { securityLifeApi } from '@/services/api/content';
import { Plus, Trash2, Save, X } from 'lucide-react'

const PROPERTY_TYPES = ['自住核心区', '投资非核心', '西部避险']

export default function AssetsPage() {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['sl-assets'],
    queryFn: () => securityLifeApi.getAssets().then(r => r.data),
  })

  const updateAssets = useMutation({
    mutationFn: (d: Record<string, unknown>) => securityLifeApi.updateAssets(d),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sl-assets'] }),
  })

  const addProperty = useMutation({
    mutationFn: (d: Record<string, unknown>) => securityLifeApi.addProperty(d),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sl-assets'] }),
  })

  const deleteProperty = useMutation({
    mutationFn: (id: number) => securityLifeApi.deleteProperty(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sl-assets'] }),
  })

  const [showAddProp, setShowAddProp] = useState(false)
  const [newProp, setNewProp] = useState({ type: '自住核心区', address: '', valuation: 0, plan_to_dispose: false, note: '' })

  if (isLoading) return <div className="text-center py-12 text-gray-400">加载中...</div>

  const asset = data || { career_description: '', career_valuation: 0, career_note: '', second_layer_total: 0, properties: [], first_layer_total: 0, second_layer_share: null }

  function formatNum(n: number) {
    if (n >= 1e8) return (n / 1e8).toFixed(1) + ' 亿'
    if (n >= 1e4) return (n / 1e4).toFixed(1) + ' 万'
    return n.toLocaleString()
  }

  return (
    <div className="space-y-8">
      <h2 className="text-lg font-bold text-gray-900">两层资产</h2>

      {/* 概览卡片 */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="rounded-lg border bg-white p-4">
          <div className="text-xs text-gray-500">第一层（职业+房产）</div>
          <div className="text-xl font-bold mt-1">{formatNum(asset.first_layer_total || 0)}</div>
        </div>
        <div className="rounded-lg border bg-white p-4">
          <div className="text-xs text-gray-500">第二层（可投资金融资产）</div>
          <div className="text-xl font-bold mt-1">{formatNum(asset.second_layer_total || 0)}</div>
        </div>
        <div className="rounded-lg border bg-white p-4">
          <div className="text-xs text-gray-500">第二层占比</div>
          <div className="text-xl font-bold mt-1">
            {asset.second_layer_share != null ? `${asset.second_layer_share.toFixed(1)}%` : '—'}
          </div>
        </div>
      </div>

      {/* 职业/股权 */}
      <section className="rounded-lg border bg-white p-5">
        <h3 className="text-sm font-semibold text-gray-700 mb-4">职业 / 股权</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs text-gray-500 mb-1">描述</label>
            <input
              className="w-full border rounded-md px-3 py-2 text-sm"
              defaultValue={asset.career_description || ''}
              onBlur={e => updateAssets.mutate({ career_description: e.target.value })}
            />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">估值（元）</label>
            <input
              type="number"
              className="w-full border rounded-md px-3 py-2 text-sm"
              defaultValue={asset.career_valuation || 0}
              onBlur={e => updateAssets.mutate({ career_valuation: Number(e.target.value) })}
            />
          </div>
        </div>
        <div className="mt-3">
          <label className="block text-xs text-gray-500 mb-1">备注</label>
          <input
            className="w-full border rounded-md px-3 py-2 text-sm"
            defaultValue={asset.career_note || ''}
            onBlur={e => updateAssets.mutate({ career_note: e.target.value })}
          />
        </div>
      </section>

      {/* 第二层总额 */}
      <section className="rounded-lg border bg-white p-5">
        <h3 className="text-sm font-semibold text-gray-700 mb-4">可投资金融资产总额</h3>
        <div>
          <label className="block text-xs text-gray-500 mb-1">金额（元）</label>
          <input
            type="number"
            className="w-full border rounded-md px-3 py-2 text-sm"
            defaultValue={asset.second_layer_total || 0}
            onBlur={e => updateAssets.mutate({ second_layer_total: Number(e.target.value) })}
          />
        </div>
      </section>

      {/* 房产列表 */}
      <section className="rounded-lg border bg-white p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-gray-700">房产</h3>
          <button
            onClick={() => setShowAddProp(true)}
            className="flex items-center gap-1 text-sm text-blue-600 hover:text-blue-800"
          >
            <Plus size={16} /> 添加
          </button>
        </div>

        {showAddProp && (
          <div className="border rounded-lg p-4 mb-4 bg-gray-50 space-y-3">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <select
                className="border rounded-md px-3 py-2 text-sm"
                value={newProp.type}
                onChange={e => setNewProp({ ...newProp, type: e.target.value })}
              >
                {PROPERTY_TYPES.map(t => <option key={t}>{t}</option>)}
              </select>
              <input
                className="border rounded-md px-3 py-2 text-sm"
                placeholder="地址"
                value={newProp.address}
                onChange={e => setNewProp({ ...newProp, address: e.target.value })}
              />
              <input
                type="number"
                className="border rounded-md px-3 py-2 text-sm"
                placeholder="估值（元）"
                value={newProp.valuation || ''}
                onChange={e => setNewProp({ ...newProp, valuation: Number(e.target.value) })}
              />
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => {
                  if (newProp.address) {
                    addProperty.mutate(newProp)
                    setNewProp({ type: '自住核心区', address: '', valuation: 0, plan_to_dispose: false, note: '' })
                    setShowAddProp(false)
                  }
                }}
                className="px-3 py-1.5 bg-gray-900 text-white rounded-md text-sm"
              >
                <Save size={14} className="inline mr-1" /> 保存
              </button>
              <button onClick={() => setShowAddProp(false)} className="px-3 py-1.5 border rounded-md text-sm">
                <X size={14} className="inline mr-1" /> 取消
              </button>
            </div>
          </div>
        )}

        {(asset.properties || []).length === 0 ? (
          <p className="text-sm text-gray-400">暂无房产记录</p>
        ) : (
          <div className="space-y-3">
            {(asset.properties || []).map((p: { id: number; type: string; address: string; valuation: number; plan_to_dispose: boolean }) => (
              <div key={p.id} className="flex items-center gap-3 p-3 border rounded-lg">
                <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded">{p.type}</span>
                <span className="text-sm text-gray-800 flex-1">{p.address}</span>
                <span className="text-sm font-medium">{formatNum(p.valuation)}</span>
                {p.plan_to_dispose && (
                  <span className="text-xs text-orange-600 bg-orange-50 px-2 py-0.5 rounded">拟处置</span>
                )}
                <button
                  onClick={() => deleteProperty.mutate(p.id)}
                  className="text-gray-400 hover:text-red-500"
                >
                  <Trash2 size={16} />
                </button>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
