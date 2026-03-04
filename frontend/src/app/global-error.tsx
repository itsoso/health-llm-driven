'use client';

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="zh-CN">
      <body className="bg-gray-50">
        <div className="min-h-screen flex items-center justify-center p-6">
          <div className="text-center max-w-md">
            <div className="text-5xl mb-4">:(</div>
            <h2 className="text-xl font-bold text-gray-800 mb-2">应用出现了严重错误</h2>
            <p className="text-gray-500 text-sm mb-6">
              {error.message || '请刷新页面重试'}
            </p>
            <button
              onClick={reset}
              className="px-6 py-2.5 bg-indigo-600 text-white rounded-xl font-medium hover:bg-indigo-700"
            >
              刷新页面
            </button>
          </div>
        </div>
      </body>
    </html>
  );
}
