'use client';

import Link from 'next/link';

export default function NotFound() {
  return (
    <main className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 flex items-center justify-center p-4">
      <div className="text-center">
        <h1 className="text-9xl font-bold bg-gradient-to-r from-indigo-600 to-purple-600 bg-clip-text text-transparent">
          404
        </h1>
        <p className="text-2xl font-semibold text-gray-800 mt-4 mb-2">
          页面不存在
        </p>
        <p className="text-gray-500 mb-8">
          你访问的页面可能已被移除或地址有误
        </p>
        <div className="flex gap-4 justify-center">
          <Link
            href="/dashboard"
            className="px-6 py-3 bg-gradient-to-r from-indigo-600 to-purple-600 text-white font-semibold rounded-lg hover:from-indigo-700 hover:to-purple-700 shadow-md transition-all"
          >
            返回首页
          </Link>
          <Link
            href="/dashboard"
            className="px-6 py-3 bg-white text-indigo-600 font-semibold rounded-lg border-2 border-indigo-200 hover:border-indigo-400 shadow-md transition-all"
          >
            仪表盘
          </Link>
        </div>
      </div>
    </main>
  );
}
