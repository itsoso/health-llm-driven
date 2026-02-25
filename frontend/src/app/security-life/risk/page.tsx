'use client'

import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { riskItems } from '@/data/security-life/riskItems'
import { blindSpotItems } from '@/data/security-life/blindSpots'
import { riskControlActions } from '@/data/security-life/riskControlActions'

function AccordionBlock({ title, children, defaultOpen = false }: {
  title: string
  children: React.ReactNode
  defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="border rounded-lg bg-white">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between p-4 text-left"
      >
        <span className="text-sm font-semibold text-gray-800">{title}</span>
        {open ? <ChevronDown size={18} className="text-gray-400" /> : <ChevronRight size={18} className="text-gray-400" />}
      </button>
      {open && <div className="px-4 pb-4">{children}</div>}
    </div>
  )
}

export default function RiskPage() {
  return (
    <div className="space-y-8">
      <h2 className="text-lg font-bold text-gray-900">风险与应对</h2>

      {/* 6 点风险 */}
      <section>
        <h3 className="text-sm font-semibold text-gray-700 mb-3">6 点风险与应对</h3>
        <div className="space-y-2">
          {riskItems.map(item => (
            <AccordionBlock key={item.id} title={item.title}>
              <ul className="space-y-2">
                {item.points.map((p, i) => (
                  <li key={i} className="text-sm text-gray-600 flex gap-2">
                    <span className="text-gray-400 shrink-0">•</span>
                    {p}
                  </li>
                ))}
              </ul>
            </AccordionBlock>
          ))}
        </div>
      </section>

      {/* 6 个盲点 */}
      <section>
        <h3 className="text-sm font-semibold text-gray-700 mb-3">高管更高频的 6 个盲点</h3>
        <div className="space-y-2">
          {blindSpotItems.map(item => (
            <AccordionBlock key={item.id} title={`${item.letter}. ${item.title}`}>
              <ul className="space-y-2">
                {item.points.map((p, i) => (
                  <li key={i} className="text-sm text-gray-600 flex gap-2">
                    <span className="text-gray-400 shrink-0">•</span>
                    {p}
                  </li>
                ))}
              </ul>
            </AccordionBlock>
          ))}
        </div>
      </section>

      {/* 4 个风控动作 */}
      <section>
        <h3 className="text-sm font-semibold text-gray-700 mb-3">安全布局关键：4 个风控动作</h3>
        <div className="space-y-2">
          {riskControlActions.map(item => (
            <AccordionBlock key={item.id} title={`${item.index}. ${item.title}`}>
              <ul className="space-y-2">
                {item.points.map((p, i) => (
                  <li key={i} className="text-sm text-gray-600 flex gap-2">
                    <span className="text-gray-400 shrink-0">•</span>
                    {p}
                  </li>
                ))}
              </ul>
            </AccordionBlock>
          ))}
        </div>
      </section>
    </div>
  )
}
