'use client';

import { Activity } from 'lucide-react';
import ProtectedRoute from '@/components/ProtectedRoute';
import DeprescribingSection from '@/components/health-extras/DeprescribingSection';
import ConnectionSection from '@/components/health-extras/ConnectionSection';
import CausalLinksSection from '@/components/health-extras/CausalLinksSection';
import DataIntegritySection from '@/components/health-extras/DataIntegritySection';

function HealthExtrasContent() {
  return (
    <main className="min-h-screen bg-gradient-to-br from-sky-50 via-white to-violet-50 pt-4 pb-12 px-4 sm:px-8">
      <div className="max-w-3xl mx-auto">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-gray-800 flex items-center gap-2">
            <Activity className="w-6 h-6 text-indigo-600" />
            健康洞察补充
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            用药梳理、社会连接、用药-指标关联与数据自检。均为趋势/提示,非诊断,任何调整请与医生确认。
          </p>
        </div>

        <div className="space-y-6">
          <DeprescribingSection />
          <ConnectionSection />
          <CausalLinksSection />
          <DataIntegritySection />
        </div>
      </div>
    </main>
  );
}

export default function HealthExtrasPage() {
  return (
    <ProtectedRoute>
      <HealthExtrasContent />
    </ProtectedRoute>
  );
}
