'use client'

import { dontList } from '@/data/security-life/dontList'
import { XCircle } from 'lucide-react'

export default function DontListPage() {
  return (
    <div className="space-y-6">
      <h2 className="text-lg font-bold text-gray-900">不要清单</h2>
      <p className="text-sm text-gray-500">
        以下为强烈建议不要做的事项。在任何决策前检查一遍，避免因恐慌、贪婪或信息差做出高风险操作。
      </p>

      <div className="space-y-4">
        {dontList.map(item => (
          <div key={item.id} className="rounded-lg border border-red-200 bg-red-50/50 p-5">
            <div className="flex items-start gap-3">
              <XCircle size={20} className="text-red-500 shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-semibold text-gray-800">{item.text}</p>
                <p className="text-sm text-gray-600 mt-2">{item.detail}</p>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
