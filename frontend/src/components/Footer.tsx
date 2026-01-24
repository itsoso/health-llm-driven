/**
 * 页脚组件 - 包含备案信息
 */
export default function Footer() {
  return (
    <footer className="mt-auto py-4 px-4 border-t border-gray-200 bg-white">
      <div className="max-w-7xl mx-auto">
        <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-2 text-xs text-gray-600">
          {/* 公安备案 */}
          <a
            href="http://www.beian.gov.cn/portal/registerSystemInfo?recordcode=33010602014266"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center space-x-1 hover:text-blue-600 transition-colors"
          >
            <img
              src="https://beian.mps.gov.cn/web/assets/logo01.6189a29f.png"
              alt="公安备案图标"
              className="w-3.5 h-3.5"
            />
            <span>浙公网安备33010602014266号</span>
          </a>
          
          {/* ICP 备案 */}
          <a
            href="https://beian.miit.gov.cn/"
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-blue-600 transition-colors"
          >
            浙ICP备2025212705号-3
          </a>
          
          {/* 版权信息 */}
          <span className="text-gray-500">
            © {new Date().getFullYear()} Executor.Life. All rights reserved.
          </span>
        </div>
      </div>
    </footer>
  );
}
