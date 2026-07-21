'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { useQueryClient } from '@tanstack/react-query';
import ProtectedRoute from '@/components/ProtectedRoute';
import GarminSection from './components/GarminSection';
import UserProfileSection from './components/UserProfileSection';
import PrivacySection from './components/PrivacySection';
import AppleWatchSection from './components/AppleWatchSection';
import WithingsSection from './components/WithingsSection';
import ApiKeySection from './components/ApiKeySection';

function SettingsContent() {
  const router = useRouter();
  const { token, isAuthenticated, isLoading: authLoading } = useAuth();
  const queryClient = useQueryClient();

  useEffect(() => { document.title = '设置 | 健康管理'; }, []);

  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [highlightGarmin, setHighlightGarmin] = useState(false);
  const [showQuickRecordSection, setShowQuickRecordSection] = useState(true);

  // 未登录跳转
  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login');
    }
  }, [authLoading, isAuthenticated, router]);

  if (authLoading || !isAuthenticated) {
    return (
      <main className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 pt-4 pb-8 px-4">
        <div className="max-w-4xl mx-auto text-center py-20">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">加载中...</p>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 pt-4 pb-8 px-4">
      <div className="max-w-4xl mx-auto">
        {/* 消息提示 */}
        {message && (
          <div className={`mb-6 p-4 rounded-lg ${
            message.type === 'success'
              ? 'bg-green-50 border border-green-200 text-green-800'
              : 'bg-red-50 border border-red-200 text-red-800'
          }`}>
            {!/^[✅❌⚠️🔐⏳]/.test(message.text) && (message.type === 'success' ? '✅ ' : '❌ ')}
            {message.text}
            <button
              onClick={() => setMessage(null)}
              className="float-right text-gray-500 hover:text-gray-700"
            >
              ✕
            </button>
          </div>
        )}

        {/* 用户信息卡片 */}
        <UserProfileSection token={token} setMessage={setMessage} />

        {/* Garmin设置卡片 */}
        <GarminSection
          token={token}
          message={message}
          setMessage={setMessage}
          queryClient={queryClient}
          highlightGarmin={highlightGarmin}
          setHighlightGarmin={setHighlightGarmin}
        />

        {/* 快捷记录饮食说明 */}
        <div className="bg-white rounded-xl shadow-lg p-6 mb-6 border border-gray-100">
          <div
            className="flex items-center justify-between cursor-pointer"
            onClick={() => setShowQuickRecordSection(!showQuickRecordSection)}
          >
            <h2 className="text-xl font-bold text-gray-900 flex items-center gap-2">
              📱 快捷记录饮食
            </h2>
            <span className="text-gray-400 text-2xl">
              {showQuickRecordSection ? '▼' : '›'}
            </span>
          </div>

          {showQuickRecordSection && (
            <div className="mt-4 space-y-4 text-gray-700">
              <p className="text-gray-600 text-sm">
                通过 iPhone 快捷指令，一键语音记录饮食、运动、打卡等健康数据。说出刚做过的事即可自动识别并保存。
              </p>

              {/* 第一步：创建可撤销的外部访问凭证 */}
              <div className="bg-green-50 rounded-lg p-4 border border-green-200">
                <h3 className="font-semibold text-green-900 mb-2">第一步：创建快捷记录 API Key</h3>
                <p className="text-sm text-green-800 mb-3">
                  Web 登录凭证不会暴露给页面。请创建一个可单独撤销的 API Key，供快捷指令使用。
                </p>
                <button
                  onClick={() => router.push('/skills')}
                  className="inline-flex items-center gap-2 rounded-lg bg-green-700 px-4 py-2 text-sm font-medium text-white hover:bg-green-800"
                >
                  管理 API Key
                </button>
              </div>

              {/* 第二步：安装快捷指令模板 */}
              <div className="bg-blue-50 rounded-lg p-4 border border-blue-200">
                <h3 className="font-semibold text-blue-900 mb-2">第二步：安装快捷指令模板</h3>
                <p className="text-sm text-blue-800 mb-3">
                  用 iPhone / iPad 的 <strong>Safari</strong> 打开下方链接，点「添加快捷指令」完成安装。
                </p>
                <a
                  href="https://www.icloud.com/shortcuts/ad3061e9a2094555acb8b42b93f57c6c"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
                >
                  📥 获取「健康记录」快捷指令
                </a>
              </div>

              {/* 第三步：填入 API Key */}
              <div className="bg-orange-50 rounded-lg p-4 border border-orange-200">
                <h3 className="font-semibold text-orange-900 mb-2">第三步：填入 API Key</h3>
                <ol className="text-sm text-orange-800 space-y-1 list-decimal list-inside">
                  <li>打开「快捷指令」App，找到「健康记录」</li>
                  <li>点右上角 <strong>···</strong> 进入编辑</li>
                  <li>找到顶部的<strong>「文本」块</strong>（内容为 <code className="bg-orange-100 px-1 rounded text-xs">YOUR_TOKEN_HERE</code>）</li>
                  <li>替换为第一步创建的 API Key，保存</li>
                </ol>
                <p className="text-xs text-orange-600 mt-2">只需设置一次，之后每次运行无需重新输入。</p>
              </div>

              {/* 第四步：设置触发方式 */}
              <div className="space-y-3">
                <h3 className="font-semibold text-gray-800">第四步：设置触发方式</h3>

                <div className="space-y-2">
                  <h4 className="font-medium text-gray-700 text-sm">方式一：辅助触控浮钮（推荐）</h4>
                  <ol className="list-decimal list-inside text-sm space-y-1 text-gray-600">
                    <li><strong>设置</strong> → <strong>辅助功能</strong> → <strong>触控</strong> → <strong>辅助触控</strong>，开启</li>
                    <li>在「自定顶层菜单」或「轻点两下」中，选择运行「健康记录」快捷指令</li>
                    <li>使用时点击浮钮，按提示说出内容即可</li>
                  </ol>
                </div>

                <div className="space-y-2">
                  <h4 className="font-medium text-gray-700 text-sm">方式二：轻点背面</h4>
                  <ol className="list-decimal list-inside text-sm space-y-1 text-gray-600">
                    <li><strong>设置</strong> → <strong>辅助功能</strong> → <strong>触控</strong> → <strong>轻点背面</strong></li>
                    <li>选择「轻点两下」→ 选择「健康记录」快捷指令</li>
                  </ol>
                </div>

                <div className="space-y-2">
                  <h4 className="font-medium text-gray-700 text-sm">其他方式</h4>
                  <ul className="list-disc list-inside text-sm text-gray-600 space-y-1">
                    <li><strong>控制中心</strong>：下滑即可触发</li>
                    <li><strong>主屏幕小组件</strong>：桌面一键运行</li>
                    <li><strong>Pro 操作按钮</strong>：iPhone 15 Pro+ 侧边按钮直接触发</li>
                  </ul>
                </div>
              </div>

              {/* 安卓/华为用户专属 */}
              <div className="bg-purple-50 rounded-lg p-4 border border-purple-200">
                <h3 className="font-semibold text-purple-900 mb-2">安卓 / 华为用户</h3>
                <p className="text-sm text-purple-800 mb-3">
                  安卓手机无法使用 iPhone 快捷指令，可用下方「语音快捷记录」页面，添加到桌面后一点即用，体验一致。
                </p>
                <button
                  onClick={() => {
                    navigator.clipboard.writeText('https://health.executor.life/quick-record');
                    alert('✅ 链接已复制！\n\n① 先在浏览器登录\n② 打开此链接\n③ 浏览器菜单 →「添加到桌面」');
                  }}
                  className="inline-flex items-center gap-2 bg-purple-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-purple-700 transition-colors"
                >
                  📋 复制语音快捷记录链接
                </button>
              </div>

              {/* 支持的语音指令 */}
              <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
                <h3 className="font-semibold text-gray-800 mb-2">支持的语音指令</h3>
                <p className="text-sm text-gray-600 mb-2">
                  不止饮食，还支持运动、打卡、鼻炎等各类健康记录：
                </p>
                <ul className="text-sm text-gray-600 space-y-1">
                  <li>「吃了两个鸡蛋、一碗米饭、炒青菜」→ 自动记录饮食和营养</li>
                  <li>「刚跑步40分钟」→ 记录运动</li>
                  <li>「做了50个俯卧撑」→ 打卡记录</li>
                  <li>「洗了鼻子」→ 记录鼻炎护理</li>
                  <li>「吃了维生素D」→ 记录补剂</li>
                  <li>「喝了一杯水」→ 记录饮水</li>
                </ul>
              </div>
            </div>
          )}
        </div>

        {/* 隐私设置卡片 */}
        <PrivacySection token={token} setMessage={setMessage} queryClient={queryClient} />

        {/* Apple Watch 设备管理 */}
        <AppleWatchSection token={token} setMessage={setMessage} queryClient={queryClient} />

        {/* Withings 体重秤 */}
        <WithingsSection token={token} setMessage={setMessage} queryClient={queryClient} />

        {/* 数据连接与授权 */}
        <div className="bg-white rounded-xl shadow-md p-6 mb-6 border border-gray-200">
          <button
            type="button"
            onClick={() => router.push('/data-connections')}
            className="flex w-full items-center justify-between text-left group"
          >
            <div className="flex items-center gap-3">
              <span className="text-3xl">{'\u{1F510}'}</span>
              <div>
                <h2 className="text-xl font-bold text-gray-900 group-hover:text-indigo-600 transition-colors">数据连接与授权</h2>
                <p className="text-sm text-gray-600">查看数据源、授权 scope、同步状态和连接健康</p>
              </div>
            </div>
            <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 text-gray-400 group-hover:text-indigo-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
            </svg>
          </button>
        </div>

        {/* API Key 管理 */}
        <ApiKeySection token={token} setMessage={setMessage} />

        {/* NFC 快速记录指南 */}
        <div className="bg-white rounded-xl shadow-md p-6 mb-6 border border-gray-200">
          <a href="/settings/nfc-guide" className="flex items-center justify-between group">
            <div className="flex items-center gap-3">
              <span className="text-3xl">{'\u{1F4F1}'}</span>
              <div>
                <h2 className="text-xl font-bold text-gray-900 group-hover:text-indigo-600 transition-colors">NFC 快速记录</h2>
                <p className="text-sm text-gray-600">通过 NFC 标签碰一下手机，自动记录饮水和排泄数据</p>
              </div>
            </div>
            <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 text-gray-400 group-hover:text-indigo-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
            </svg>
          </a>
        </div>
      </div>
    </main>
  );
}

// 导出受保护的页面
export default function SettingsPage() {
  return (
    <ProtectedRoute>
      <SettingsContent />
    </ProtectedRoute>
  );
}
