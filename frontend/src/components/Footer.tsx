/**
 * 页脚组件 - 包含备案信息
 */
export default function Footer() {
  return (
    <footer className="mt-auto py-6 px-4 border-t border-gray-200 bg-white">
      <div className="max-w-7xl mx-auto">
        <div className="flex flex-col items-center justify-center space-y-2">
          {/* 公安备案 */}
          <div className="flex items-center space-x-2">
            <a
              href="http://www.beian.gov.cn/portal/registerSystemInfo?recordcode=33010602014266"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center space-x-1 hover:text-blue-600 transition-colors text-xs text-gray-600"
            >
              <img
                src="https://beian.mps.gov.cn/web/assets/logo01.6189a29f.png"
                alt="公安备案图标"
                className="w-3.5 h-3.5"
              />
              <span>浙公网安备33010602014266号</span>
            </a>
          </div>
          
          {/* ICP 备案 */}
          <div className="flex items-center">
            <a
              href="https://beian.miit.gov.cn/"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-blue-600 transition-colors text-xs text-gray-600"
            >
              浙ICP备2025212705号-3
            </a>
          </div>
          
          {/* 版权信息 */}
          <div className="text-gray-500 text-xs">
            © {new Date().getFullYear()} Executor.Life. All rights reserved.
          </div>
        </div>
      </div>
    </footer>
  );
}
