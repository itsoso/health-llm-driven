'use client';

import { useState, useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import ProtectedRoute from '@/components/ProtectedRoute';
import { assistantOpenclawBindingApi, AssistantOpenClawBindingStatus } from '@/services/api/ai';
import { formatDateTime } from '@/utils/timezone';
import GarminSection, { extractErrorMsg } from './components/GarminSection';
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
  const assistantOpenclawSectionRef = useRef<HTMLDivElement>(null);

  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [highlightGarmin, setHighlightGarmin] = useState(false);
  const [highlightAssistantOpenClaw, setHighlightAssistantOpenClaw] = useState(false);
  const [showQuickRecordSection, setShowQuickRecordSection] = useState(true);
  const [assistantOpenclawForm, setAssistantOpenclawForm] = useState({
    display_name: '我的 OpenClaw',
    gateway_url: 'http://127.0.0.1:28789',
    gateway_token: '',
    enabled: false,
  });

  const { data: assistantBinding, isLoading: assistantBindingLoading, refetch: refetchAssistantBinding } = useQuery({
    queryKey: ['assistant-openclaw-binding'],
    queryFn: async () => {
      const res = await assistantOpenclawBindingApi.getMe();
      return res.data as AssistantOpenClawBindingStatus;
    },
    enabled: !!token,
  });

  useEffect(() => {
    if (!assistantBinding) return;
    setAssistantOpenclawForm(prev => ({
      ...prev,
      display_name: assistantBinding.display_name || '我的 OpenClaw',
      gateway_url: assistantBinding.gateway_url || 'http://127.0.0.1:28789',
      gateway_token: '',
      enabled: assistantBinding.enabled,
    }));
  }, [assistantBinding]);

  const saveAssistantOpenclawMutation = useMutation({
    mutationFn: async () => {
      const payload: {
        display_name: string;
        gateway_url: string;
        enabled: boolean;
        gateway_token?: string;
      } = {
        display_name: assistantOpenclawForm.display_name.trim() || '我的 OpenClaw',
        gateway_url: assistantOpenclawForm.gateway_url.trim(),
        enabled: assistantOpenclawForm.enabled,
      };
      if (assistantOpenclawForm.gateway_token.trim()) {
        payload.gateway_token = assistantOpenclawForm.gateway_token.trim();
      }
      return assistantOpenclawBindingApi.update(payload);
    },
    onSuccess: async (res) => {
      setMessage({ type: 'success', text: res.data.message || 'OpenClaw 绑定已保存' });
      setAssistantOpenclawForm(prev => ({ ...prev, gateway_token: '' }));
      await refetchAssistantBinding();
    },
    onError: (error: any) => {
      setMessage({ type: 'error', text: extractErrorMsg(error, '保存 OpenClaw 绑定失败') });
    },
  });

  const testAssistantOpenclawMutation = useMutation({
    mutationFn: async () => {
      const payload: { gateway_url?: string; gateway_token?: string } = {};
      const normalizedUrl = assistantOpenclawForm.gateway_url.trim();
      const normalizedToken = assistantOpenclawForm.gateway_token.trim();
      const hasSavedBinding = !!assistantBinding?.configured;
      const savedUrl = assistantBinding?.gateway_url?.trim() || '';
      const usingSavedConfig =
        hasSavedBinding &&
        !normalizedToken &&
        normalizedUrl === savedUrl;

      if (!usingSavedConfig) {
        if (normalizedUrl) {
          payload.gateway_url = normalizedUrl;
        }
        if (normalizedToken) {
          payload.gateway_token = normalizedToken;
        }
      }
      return assistantOpenclawBindingApi.test(payload);
    },
    onSuccess: (res) => {
      const result = res.data;
      setMessage({
        type: result.status === 'active' ? 'success' : 'error',
        text: `${result.message}${result.latency_ms ? `（${result.latency_ms}ms）` : ''}`,
      });
      refetchAssistantBinding();
    },
    onError: (error: any) => {
      setMessage({ type: 'error', text: extractErrorMsg(error, '测试 OpenClaw 连接失败') });
    },
  });

  const deleteAssistantOpenclawMutation = useMutation({
    mutationFn: async () => assistantOpenclawBindingApi.remove(),
    onSuccess: async () => {
      setMessage({ type: 'success', text: '已解绑智能助理专用 OpenClaw' });
      setAssistantOpenclawForm({
        display_name: '我的 OpenClaw',
        gateway_url: 'http://127.0.0.1:28789',
        gateway_token: '',
        enabled: false,
      });
      await refetchAssistantBinding();
    },
    onError: (error: any) => {
      setMessage({ type: 'error', text: extractErrorMsg(error, '解绑 OpenClaw 失败') });
    },
  });

  // 未登录跳转
  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login');
    }
  }, [authLoading, isAuthenticated, router]);

  // 处理 URL hash 滚动到设置区块
  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (window.location.hash === '#assistant-openclaw') {
      const timer = setTimeout(() => {
        assistantOpenclawSectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        setHighlightAssistantOpenClaw(true);
        setTimeout(() => setHighlightAssistantOpenClaw(false), 3000);
      }, 500);
      return () => clearTimeout(timer);
    }
  }, []);

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

        {/* 智能助理专用 OpenClaw */}
        <div
          ref={assistantOpenclawSectionRef}
          id="assistant-openclaw"
          className={`bg-white rounded-xl shadow-lg p-6 mb-6 border transition-all duration-500 ${
            highlightAssistantOpenClaw
              ? 'border-cyan-400 ring-4 ring-cyan-100 shadow-xl'
              : 'border-gray-100'
          }`}
        >
          <h2 className="text-xl font-bold text-gray-900 mb-4 flex items-center gap-2">
            🦀 智能助理专用 OpenClaw
            {highlightAssistantOpenClaw && (
              <span className="px-2 py-0.5 bg-cyan-100 text-cyan-700 text-xs rounded-full animate-pulse">
                请在此配置
              </span>
            )}
          </h2>

          <p className="text-gray-600 text-sm mb-4">
            该绑定仅作用于「智能助理」中的「我的 OpenClaw」模式，不会影响系统现有的 OpenClaw 功能。
          </p>

          <div className="rounded-lg border border-cyan-100 bg-cyan-50 p-4 text-sm text-cyan-900 mb-4 space-y-1">
            <div>允许地址：`127.0.0.1`、`localhost` 或系统白名单中的可信域名。</div>
            <div>推荐你当前使用：`http://127.0.0.1:28789`</div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">显示名称</label>
              <input
                type="text"
                value={assistantOpenclawForm.display_name}
                onChange={(e) => setAssistantOpenclawForm(prev => ({ ...prev, display_name: e.target.value }))}
                className="w-full p-3 border border-gray-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-cyan-500 focus:border-cyan-500"
                placeholder="我的 OpenClaw"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">网关地址</label>
              <input
                type="text"
                value={assistantOpenclawForm.gateway_url}
                onChange={(e) => setAssistantOpenclawForm(prev => ({ ...prev, gateway_url: e.target.value }))}
                className="w-full p-3 border border-gray-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-cyan-500 focus:border-cyan-500"
                placeholder="http://127.0.0.1:28789"
              />
            </div>
            <div className="md:col-span-2">
              <label className="block text-sm font-medium text-gray-700 mb-2">OpenClaw Token</label>
              <input
                type="password"
                value={assistantOpenclawForm.gateway_token}
                onChange={(e) => setAssistantOpenclawForm(prev => ({ ...prev, gateway_token: e.target.value }))}
                className="w-full p-3 border border-gray-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-cyan-500 focus:border-cyan-500"
                placeholder={assistantBinding?.configured ? '留空表示保留当前 Token' : '请输入你的 OpenClaw Token'}
              />
              {assistantBinding?.configured && assistantBinding.gateway_token_last4 && (
                <p className="mt-2 text-xs text-gray-500">当前已保存 Token 后四位：{assistantBinding.gateway_token_last4}</p>
              )}
            </div>
          </div>

          <div className="flex items-center justify-between gap-4 flex-wrap mb-5">
            <label className="inline-flex items-center gap-3 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={assistantOpenclawForm.enabled}
                onChange={(e) => setAssistantOpenclawForm(prev => ({ ...prev, enabled: e.target.checked }))}
                className="w-4 h-4 rounded border-gray-300 text-cyan-600 focus:ring-cyan-500"
              />
              启用「我的 OpenClaw」模式
            </label>
            <div className="text-sm text-gray-600">
              当前状态：
              <span className={`ml-2 inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${
                assistantBinding?.status === 'active'
                  ? 'bg-green-100 text-green-700'
                  : assistantBinding?.status === 'invalid'
                    ? 'bg-red-100 text-red-700'
                    : assistantBinding?.status === 'disabled'
                      ? 'bg-gray-100 text-gray-700'
                      : 'bg-amber-100 text-amber-700'
              }`}>
                {assistantBindingLoading
                  ? '加载中'
                  : assistantBinding?.status === 'active'
                    ? '可用'
                    : assistantBinding?.status === 'invalid'
                      ? '连接异常'
                      : assistantBinding?.status === 'disabled'
                        ? '已停用'
                        : '未配置'}
              </span>
            </div>
          </div>

          {(assistantBinding?.last_error || assistantBinding?.last_tested_at) && (
            <div className="mb-4 rounded-lg bg-gray-50 border border-gray-200 p-4 text-sm text-gray-700 space-y-1">
              {assistantBinding.last_tested_at && (
                <div>最近测试时间：{formatDateTime(assistantBinding.last_tested_at)}</div>
              )}
              {assistantBinding.last_error && (
                <div className="text-red-600">最近错误：{assistantBinding.last_error}</div>
              )}
            </div>
          )}

          <div className="flex flex-wrap gap-3">
            <button
              onClick={() => testAssistantOpenclawMutation.mutate()}
              disabled={!assistantOpenclawForm.gateway_url.trim() || testAssistantOpenclawMutation.isPending}
              className="px-4 py-2 bg-cyan-500 text-white rounded-lg hover:bg-cyan-600 disabled:opacity-50"
            >
              {testAssistantOpenclawMutation.isPending ? '测试中...' : '测试连接'}
            </button>
            <button
              onClick={() => saveAssistantOpenclawMutation.mutate()}
              disabled={!assistantOpenclawForm.gateway_url.trim() || saveAssistantOpenclawMutation.isPending}
              className="px-4 py-2 bg-indigo-500 text-white rounded-lg hover:bg-indigo-600 disabled:opacity-50"
            >
              {saveAssistantOpenclawMutation.isPending ? '保存中...' : '保存绑定'}
            </button>
            {assistantBinding?.configured && (
              <button
                onClick={() => {
                  if (confirm('确定要解绑这个智能助理专用 OpenClaw 吗？')) {
                    deleteAssistantOpenclawMutation.mutate();
                  }
                }}
                disabled={deleteAssistantOpenclawMutation.isPending}
                className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 disabled:opacity-50"
              >
                {deleteAssistantOpenclawMutation.isPending ? '解绑中...' : '解绑'}
              </button>
            )}
          </div>
        </div>

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

              {/* 第一步：复制 Token */}
              <div className="bg-green-50 rounded-lg p-4 border border-green-200">
                <h3 className="font-semibold text-green-900 mb-2">第一步：复制你的专属 Token</h3>
                <p className="text-sm text-green-800 mb-3">
                  安装快捷指令后需要填入此 Token 作为身份凭证，点击下方一键复制。
                </p>
                {token ? (
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(token);
                      alert('✅ Token 已复制！\n\n安装快捷指令后，编辑第一步的「文本」块，将 YOUR_TOKEN_HERE 替换为此 Token。');
                    }}
                    className="w-full flex items-center justify-between gap-2 bg-white border-2 border-green-300 hover:bg-green-100 active:scale-[0.99] transition-all rounded-lg px-4 py-3 text-left cursor-pointer"
                  >
                    <span className="text-xs font-mono text-green-900 break-all flex-1">
                      {token.slice(0, 28)}...{token.slice(-8)}
                    </span>
                    <span className="text-green-700 font-semibold text-sm whitespace-nowrap">📋 点击复制</span>
                  </button>
                ) : (
                  <p className="text-sm text-green-800">请先登录后查看专属 Token。</p>
                )}
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

              {/* 第三步：填入 Token */}
              <div className="bg-orange-50 rounded-lg p-4 border border-orange-200">
                <h3 className="font-semibold text-orange-900 mb-2">第三步：填入你的 Token</h3>
                <ol className="text-sm text-orange-800 space-y-1 list-decimal list-inside">
                  <li>打开「快捷指令」App，找到「健康记录」</li>
                  <li>点右上角 <strong>···</strong> 进入编辑</li>
                  <li>找到顶部的<strong>「文本」块</strong>（内容为 <code className="bg-orange-100 px-1 rounded text-xs">YOUR_TOKEN_HERE</code>）</li>
                  <li>替换为第一步复制的 Token，保存</li>
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
                {token ? (
                  <button
                    onClick={() => {
                      const url = `https://health.executor.life/quick-record?token=${token}`;
                      navigator.clipboard.writeText(url);
                      alert('✅ 链接已复制！\n\n① 用手机浏览器打开此链接\n② 浏览器菜单 →「添加到桌面」\n③ 桌面出现图标，一点即可语音记录');
                    }}
                    className="inline-flex items-center gap-2 bg-purple-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-purple-700 transition-colors"
                  >
                    📋 复制语音快捷记录链接
                  </button>
                ) : (
                  <p className="text-sm text-purple-800">请先登录后获取专属链接。</p>
                )}
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
