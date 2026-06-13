'use client';

import { useQuery } from '@tanstack/react-query';
import { Database, Loader2, ShieldCheck, AlertTriangle, XCircle } from 'lucide-react';
import {
  getDataIntegrity,
  type IntegritySeverity,
} from '@/services/api/dataHealth';

const SEVERITY_STYLE: Record<
  IntegritySeverity,
  { badge: string; icon: typeof AlertTriangle; label: string }
> = {
  error: { badge: 'bg-red-100 text-red-700', icon: XCircle, label: '错误' },
  warning: { badge: 'bg-amber-100 text-amber-700', icon: AlertTriangle, label: '警告' },
  info: { badge: 'bg-sky-100 text-sky-700', icon: AlertTriangle, label: '提示' },
};

export default function DataIntegritySection() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['data-integrity'],
    queryFn: getDataIntegrity,
  });

  return (
    <section className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
      <header className="flex items-center gap-2 mb-1">
        <Database className="w-5 h-5 text-teal-600" />
        <h2 className="text-lg font-semibold text-gray-800">数据自检</h2>
      </header>
      <p className="text-sm text-gray-500 mb-4">
        检查你的健康数据有没有量纲错、范围越界、来源断连等静默损坏。空清单 = 健康。
      </p>

      {isLoading ? (
        <div className="flex items-center gap-2 text-sm text-gray-400 py-6 justify-center">
          <Loader2 className="w-4 h-4 animate-spin" /> 检查中…
        </div>
      ) : isError ? (
        <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">
          自检失败,请稍后重试。
        </p>
      ) : data ? (
        data.healthy ? (
          <div className="flex items-center gap-2 text-sm text-emerald-700 bg-emerald-50 rounded-xl px-4 py-4">
            <ShieldCheck className="w-4 h-4 flex-shrink-0" />
            数据自检通过,未发现异常。
          </div>
        ) : (
          <>
            <p className="text-sm text-gray-600 mb-3">
              发现 <span className="font-semibold">{data.issue_count}</span> 项可疑数据:
            </p>
            <ul className="space-y-3">
              {data.issues.map((issue, idx) => {
                const style = SEVERITY_STYLE[issue.severity] ?? SEVERITY_STYLE.info;
                const Icon = style.icon;
                return (
                  <li
                    key={`${issue.code}-${idx}`}
                    className="border border-gray-100 rounded-xl p-4"
                  >
                    <div className="flex items-start gap-2">
                      <Icon className="w-4 h-4 text-gray-400 mt-0.5 flex-shrink-0" />
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span
                            className={`px-2 py-0.5 rounded-full text-xs font-medium ${style.badge}`}
                          >
                            {style.label}
                          </span>
                          {issue.count > 1 && (
                            <span className="text-xs text-gray-400">
                              {issue.count} 处
                            </span>
                          )}
                        </div>
                        <p className="text-sm text-gray-800 mt-1.5">{issue.detail}</p>
                        {issue.fix_hint && (
                          <p className="text-sm text-gray-500 mt-1">
                            建议:{issue.fix_hint}
                          </p>
                        )}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          </>
        )
      ) : null}
    </section>
  );
}
