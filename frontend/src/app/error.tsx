'use client';

import { useEffect } from 'react';

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error('页面错误:', error);
  }, [error]);

  return (
    <div className="min-h-[60vh] flex items-center justify-center p-6">
      <div className="text-center max-w-md">
        <div className="text-5xl mb-4">:(</div>
        <h2 className="text-xl font-bold text-gray-800 mb-2">页面出现了问题</h2>
        <p className="text-gray-500 text-sm mb-6">
          {error.message || '发生了未知错误，请尝试刷新页面'}
        </p>
        <div className="flex gap-3 justify-center">
          <button
            onClick={reset}
            className="px-6 py-2.5 bg-indigo-600 text-white rounded-xl font-medium hover:bg-indigo-700 transition"
          >
            重试
          </button>
          <button
            onClick={() => window.location.href = '/dashboard'}
            className="px-6 py-2.5 border border-gray-300 text-gray-600 rounded-xl font-medium hover:bg-gray-50 transition"
          >
            返回首页
          </button>
        </div>
      </div>
    </div>
  );
}
