'use client';

import { useState } from 'react';

/* eslint-disable @typescript-eslint/no-explicit-any */
export function DebugPanel({ debug }: { debug: any }) {
  const [expandedSources, setExpandedSources] = useState<Set<string>>(new Set());

  const toggleSource = (key: string) => {
    setExpandedSources(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  };

  return (
    <div className="bg-gradient-to-br from-purple-50 to-indigo-50 rounded-xl p-5 mb-6 border border-purple-200">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-purple-800 flex items-center gap-2">
          <span>🔍</span> AI 决策过程
        </h3>
        {debug.performance?.['总耗时'] && (
          <span className="text-sm font-mono bg-purple-100 text-purple-700 px-3 py-1 rounded-full">
            ⏱ {debug.performance['总耗时']}
          </span>
        )}
      </div>

      {/* Steps with Timing */}
      {debug.steps?.length > 0 && (
        <div className="mb-4">
          <h4 className="text-sm font-semibold text-purple-700 mb-2">📋 执行步骤</h4>
          <div className="space-y-1.5">
            {debug.steps.map((step: string, index: number) => {
              const stepName = step.replace(/^\d+\.\s*/, '');
              const duration = debug.performance?.[stepName];
              return (
                <div key={index} className="flex items-center gap-2 bg-white/70 rounded-lg px-3 py-2">
                  <span className="text-purple-600 font-bold min-w-[24px] text-center bg-purple-100 rounded px-1.5 py-0.5 text-xs">
                    {index + 1}
                  </span>
                  <span className="flex-1 text-sm text-gray-700">{stepName}</span>
                  {duration && (
                    <span className="text-xs font-mono text-purple-500 bg-purple-50 px-2 py-0.5 rounded">
                      {duration}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Reasoning */}
      {debug.reasoning?.length > 0 && (
        <div className="mb-4">
          <h4 className="text-sm font-semibold text-purple-700 mb-2">💡 推理过程</h4>
          <div className="space-y-1">
            {debug.reasoning.map((reason: string, index: number) => {
              const isError = reason.includes('❌');
              const isWarning = reason.includes('⚠️');
              const isSuccess = reason.includes('✅');
              const bgColor = isError
                ? 'bg-red-50 border-red-200'
                : isWarning
                ? 'bg-yellow-50 border-yellow-200'
                : isSuccess
                ? 'bg-green-50 border-green-200'
                : 'bg-white/60 border-gray-200';

              return (
                <div key={index} className={`${bgColor} rounded-lg px-3 py-2 border text-sm`}>
                  <span className="text-gray-700 leading-relaxed whitespace-pre-wrap">{reason}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Data Sources */}
      {debug.data_sources && Object.keys(debug.data_sources).length > 0 && (
        <div className="mb-4">
          <h4 className="text-sm font-semibold text-purple-700 mb-2">📊 数据来源</h4>
          <div className="space-y-1.5">
            {Object.entries(debug.data_sources).map(([key, value]) => (
              <div key={key} className="bg-white/70 rounded-lg border border-gray-200 overflow-hidden">
                <button
                  onClick={() => toggleSource(key)}
                  className="w-full flex items-center justify-between px-3 py-2 text-sm text-left hover:bg-white/90 transition-colors"
                >
                  <span className="font-medium text-gray-700">{key}</span>
                  <span className="text-gray-400 text-xs">{expandedSources.has(key) ? '收起 ▲' : '展开 ▼'}</span>
                </button>
                {expandedSources.has(key) && (
                  <div className="px-3 pb-2 border-t border-gray-100">
                    <pre className="text-xs text-gray-600 whitespace-pre-wrap break-all max-h-60 overflow-y-auto mt-2 font-mono">
                      {typeof value === 'string' ? value : JSON.stringify(value, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Performance Metrics */}
      {debug.performance && Object.keys(debug.performance).length > 1 && (
        <div>
          <h4 className="text-sm font-semibold text-purple-700 mb-2">⚡ 性能指标</h4>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
            {Object.entries(debug.performance).map(([key, value]) => (
              <div key={key} className="bg-white/70 rounded-lg p-2 border border-gray-200">
                <div className="text-purple-600 truncate">{key}</div>
                <div className="text-gray-800 font-mono font-medium">{String(value)}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
