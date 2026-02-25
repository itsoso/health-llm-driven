'use client'

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { securityLifeApi } from '@/services/api'
import { systemDefinitions } from '@/data/security-life/systemDefinitions'
import { Plus, Trash2, X } from 'lucide-react'

const PHASES = [
  { key: '0-2', title: '第 0–2 周：做「家庭风控资产负债表」的底表' },
  { key: '3-6', title: '第 3–6 周：把跑道做出来 + 把杠杆收住' },
  { key: '7-12', title: '第 7–12 周：启动 Plan B，搭建海外增长仓' },
]

interface ChecklistItem {
  id: number
  phase: string
  system_id: number
  label: string
  detail?: string
  is_default: boolean
  completed: boolean
}

export default function ChecklistPage() {
  const qc = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [newItem, setNewItem] = useState({ phase: '0-2', system_id: 1, label: '', detail: '' })
  const [expandedDetail, setExpandedDetail] = useState<number | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['sl-checklist'],
    queryFn: () => securityLifeApi.getChecklist().then(r => r.data),
  })

  const toggle = useMutation({
    mutationFn: (id: number) => securityLifeApi.toggleChecklistItem(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sl-checklist'] }),
  })

  const addItem = useMutation({
    mutationFn: (d: Record<string, unknown>) => securityLifeApi.addChecklistItem(d),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sl-checklist'] })
      setShowAdd(false)
      setNewItem({ phase: '0-2', system_id: 1, label: '', detail: '' })
    },
  })

  const deleteItem = useMutation({
    mutationFn: (id: number) => securityLifeApi.deleteChecklistItem(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sl-checklist'] }),
  })

  if (isLoading) return <div className="text-center py-12 text-gray-400">加载中...</div>

  const items: ChecklistItem[] = data?.items || []
  const phases = data?.phases || {}
  const total = data?.total || 0
  const completedCount = data?.completed_count || 0

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-gray-900">90 天清单</h2>
          <p className="text-sm text-gray-500 mt-1">
            已完成 {completedCount}/{total} 项
            {total > 0 && (
              <span className="ml-2 text-gray-400">
                ({((completedCount / total) * 100).toFixed(0)}%)
              </span>
            )}
          </p>
        </div>
        <button
          onClick={() => setShowAdd(true)}
          className="flex items-center gap-1 px-3 py-2 bg-gray-900 text-white rounded-md text-sm"
        >
          <Plus size={16} /> 自定义项
        </button>
      </div>

      {/* 总进度 */}
      <div className="h-3 bg-gray-100 rounded-full overflow-hidden">
        <div
          className="h-full bg-green-500 rounded-full transition-all"
          style={{ width: total > 0 ? `${(completedCount / total) * 100}%` : '0%' }}
        />
      </div>

      {/* 添加新项 */}
      {showAdd && (
        <div className="border rounded-lg p-4 bg-gray-50 space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <select
              className="border rounded-md px-3 py-2 text-sm"
              value={newItem.phase}
              onChange={e => setNewItem({ ...newItem, phase: e.target.value })}
            >
              {PHASES.map(p => <option key={p.key} value={p.key}>第 {p.key} 周</option>)}
            </select>
            <select
              className="border rounded-md px-3 py-2 text-sm"
              value={newItem.system_id}
              onChange={e => setNewItem({ ...newItem, system_id: Number(e.target.value) })}
            >
              {systemDefinitions.map(s => (
                <option key={s.id} value={s.id}>{s.id}. {s.name}</option>
              ))}
            </select>
            <input
              className="border rounded-md px-3 py-2 text-sm"
              placeholder="任务描述"
              value={newItem.label}
              onChange={e => setNewItem({ ...newItem, label: e.target.value })}
            />
          </div>
          <input
            className="w-full border rounded-md px-3 py-2 text-sm"
            placeholder="详细说明（可选）"
            value={newItem.detail}
            onChange={e => setNewItem({ ...newItem, detail: e.target.value })}
          />
          <div className="flex gap-2">
            <button
              onClick={() => newItem.label && addItem.mutate(newItem)}
              className="px-3 py-1.5 bg-gray-900 text-white rounded-md text-sm"
            >
              保存
            </button>
            <button onClick={() => setShowAdd(false)} className="px-3 py-1.5 border rounded-md text-sm">
              <X size={14} className="inline mr-1" /> 取消
            </button>
          </div>
        </div>
      )}

      {/* 按阶段分组 */}
      {PHASES.map(phase => {
        const phaseItems = items.filter(i => i.phase === phase.key)
        const phaseStat = (phases as Record<string, { total: number; completed: number }>)[phase.key]
        const phaseCompleted = phaseStat?.completed || 0
        const phaseTotal = phaseStat?.total || 0

        return (
          <section key={phase.key} className="rounded-lg border bg-white p-5">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-gray-800">{phase.title}</h3>
              <span className="text-xs text-gray-500">
                {phaseCompleted}/{phaseTotal}
              </span>
            </div>
            {/* 阶段进度 */}
            <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden mb-4">
              <div
                className="h-full bg-green-500 rounded-full transition-all"
                style={{ width: phaseTotal > 0 ? `${(phaseCompleted / phaseTotal) * 100}%` : '0%' }}
              />
            </div>

            <div className="space-y-2">
              {phaseItems.map(item => {
                const sys = systemDefinitions.find(s => s.id === item.system_id)
                return (
                  <div key={item.id}>
                    <div className="flex items-start gap-3 p-2 rounded-lg hover:bg-gray-50">
                      <input
                        type="checkbox"
                        checked={item.completed}
                        onChange={() => toggle.mutate(item.id)}
                        className="mt-0.5 h-4 w-4 rounded border-gray-300"
                      />
                      <div className="flex-1 min-w-0">
                        <p className={`text-sm ${item.completed ? 'text-gray-400 line-through' : 'text-gray-800'}`}>
                          {item.label}
                        </p>
                        {item.detail && (
                          <button
                            onClick={() => setExpandedDetail(expandedDetail === item.id ? null : item.id)}
                            className="text-xs text-blue-500 mt-0.5"
                          >
                            {expandedDetail === item.id ? '收起' : '详情'}
                          </button>
                        )}
                        {expandedDetail === item.id && item.detail && (
                          <p className="text-xs text-gray-500 mt-1 bg-gray-50 p-2 rounded">{item.detail}</p>
                        )}
                      </div>
                      <span className="text-xs bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded shrink-0">
                        {sys?.name?.slice(0, 4) || `系统${item.system_id}`}
                      </span>
                      {!item.is_default && (
                        <button
                          onClick={() => deleteItem.mutate(item.id)}
                          className="text-gray-300 hover:text-red-500"
                        >
                          <Trash2 size={14} />
                        </button>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          </section>
        )
      })}
    </div>
  )
}
