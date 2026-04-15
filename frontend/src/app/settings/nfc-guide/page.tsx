'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { api } from '@/services/api/client';

interface SupplementDef {
  id: number;
  name: string;
  dosage: string;
  timing: string;
  category: string;
}

export default function NfcGuidePage() {
  const router = useRouter();
  const { user } = useAuth();
  const [copied, setCopied] = useState<string | null>(null);
  const [supplements, setSupplements] = useState<SupplementDef[]>([]);

  const apiBase = 'https://health.executor.life/api/v1';

  useEffect(() => {
    api.get('/supplements/me/definitions').then(res => {
      const active = (res.data || []).filter((s: any) => s.is_active);
      setSupplements(active);
    }).catch(() => {});
  }, []);

  const copyToClipboard = (text: string, label: string) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(label);
      setTimeout(() => setCopied(null), 2000);
    });
  };

  const steps = [
    {
      title: '1. 准备 NFC 标签',
      content: '购买 3 个空白 NFC 贴纸（NTAG215/216，淘宝搜"NFC 贴纸"，约 5-10 元一版）。分别贴在：',
      items: ['水杯旁或饮水机上 — 饮水', '马桶左侧墙壁 — 大便', '马桶右侧墙壁 — 小便'],
    },
    {
      title: '2. 获取 API Key',
      content: '在「设置」页面的「API Key 管理」中创建一个新的 Key。API Key 不会过期，比 JWT Token 更适合快捷指令长期使用。',
      action: { label: '前往设置', onClick: () => router.push('/settings') },
    },
    {
      title: '3. 创建快捷指令',
      content: '打开 iOS「快捷指令」App，创建 3 个新快捷指令。每个快捷指令的动作流程相同，只是请求体不同：',
      sub: [
        {
          name: '饮水快捷指令',
          body: '{"action":"water"}',
          note: '碰一下 = 记录 250ml 饮水',
        },
        {
          name: '大便快捷指令',
          body: '{"action":"bowel"}',
          note: '第一次碰 = 开始计时，第二次碰 = 结束并记录时长',
        },
        {
          name: '小便快捷指令',
          body: '{"action":"urine"}',
          note: '碰一下 = 记录一次小便',
        },
      ],
    },
    {
      title: '4. 设置 NFC 自动化',
      content: '在「快捷指令」App → 自动化 → + → NFC → 扫描标签 → 绑定对应的快捷指令 → 关闭"运行前询问"。',
      items: ['每个家庭成员在自己手机上设置，使用自己的 API Key', '同一组 NFC 标签，全家共用'],
    },
  ];

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-950 to-slate-900 text-white">
      <div className="mx-auto max-w-2xl px-4 py-8">
        {/* 返回 */}
        <button onClick={() => router.back()} className="mb-6 flex items-center gap-2 text-sm text-slate-400 hover:text-white transition-colors">
          <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
          </svg>
          返回
        </button>

        {/* 标题 */}
        <div className="mb-8">
          <div className="mb-3 flex items-center gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-500/20 text-blue-400">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M8.288 15.038a5.25 5.25 0 017.424 0M5.106 11.856c3.807-3.808 9.98-3.808 13.788 0M1.924 8.674c5.565-5.565 14.587-5.565 20.152 0M12.53 18.22l-.53.53-.53-.53a.75.75 0 011.06 0z" />
              </svg>
            </div>
            <h1 className="text-2xl font-bold">NFC 快速记录</h1>
          </div>
          <p className="text-slate-300 leading-7">
            通过 NFC 标签 + iOS 快捷指令，碰一下手机即可自动记录饮水、排泄数据。无需打开 App，全程不到 1 秒。
          </p>
        </div>

        {/* 步骤 */}
        <div className="space-y-6">
          {steps.map((step, i) => (
            <div key={i} className="rounded-2xl border border-white/10 bg-white/5 p-5">
              <h2 className="mb-3 text-lg font-semibold text-white">{step.title}</h2>
              <p className="mb-3 text-sm leading-7 text-slate-300">{step.content}</p>

              {step.items && (
                <ul className="ml-4 space-y-1.5">
                  {step.items.map((item, j) => (
                    <li key={j} className="flex items-start gap-2 text-sm text-slate-200">
                      <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-blue-400" />
                      {item}
                    </li>
                  ))}
                </ul>
              )}

              {step.action && (
                <button
                  onClick={step.action.onClick}
                  className="mt-3 rounded-xl bg-blue-500/20 px-4 py-2 text-sm text-blue-300 hover:bg-blue-500/30 transition-colors"
                >
                  {step.action.label}
                </button>
              )}

              {step.sub && (
                <div className="mt-3 space-y-4">
                  {step.sub.map((s, j) => (
                    <div key={j} className="rounded-xl bg-slate-800/60 p-4">
                      <div className="mb-2 flex items-center justify-between">
                        <span className="font-medium text-white">{s.name}</span>
                        <span className="text-xs text-slate-400">{s.note}</span>
                      </div>
                      <div className="text-xs text-slate-400 mb-2">快捷指令动作配置：</div>
                      <div className="space-y-2 text-sm">
                        <div className="flex items-center justify-between rounded-lg bg-slate-900/80 px-3 py-2">
                          <span className="text-slate-400">URL</span>
                          <div className="flex items-center gap-2">
                            <code className="text-blue-300 text-xs">{apiBase}/nfc/tap</code>
                            <button
                              onClick={() => copyToClipboard(`${apiBase}/nfc/tap`, `url-${j}`)}
                              className="text-slate-500 hover:text-white"
                            >
                              {copied === `url-${j}` ? '!' : '\u2398'}
                            </button>
                          </div>
                        </div>
                        <div className="flex items-center justify-between rounded-lg bg-slate-900/80 px-3 py-2">
                          <span className="text-slate-400">Method</span>
                          <span className="text-emerald-300">POST</span>
                        </div>
                        <div className="flex items-center justify-between rounded-lg bg-slate-900/80 px-3 py-2">
                          <span className="text-slate-400">Header</span>
                          <code className="text-yellow-300 text-xs">X-API-Key: 你的Key</code>
                        </div>
                        <div className="flex items-center justify-between rounded-lg bg-slate-900/80 px-3 py-2">
                          <span className="text-slate-400">Body</span>
                          <div className="flex items-center gap-2">
                            <code className="text-emerald-300 text-xs">{s.body}</code>
                            <button
                              onClick={() => copyToClipboard(s.body, `body-${j}`)}
                              className="text-slate-500 hover:text-white"
                            >
                              {copied === `body-${j}` ? '!' : '\u2398'}
                            </button>
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>

        {/* 家庭成员代记 */}
        <div className="mt-6 rounded-2xl border border-amber-500/20 bg-amber-500/5 p-5">
          <h2 className="mb-3 text-lg font-semibold text-amber-200">家庭成员代记</h2>
          <p className="mb-3 text-sm leading-7 text-slate-300">
            管理员可以为没有手机的家庭成员（小孩、老人）代记数据。在请求体中添加 <code className="rounded bg-slate-800 px-1.5 py-0.5 text-amber-300">on_behalf_of</code> 参数：
          </p>
          <div className="rounded-xl bg-slate-900/80 p-3">
            <code className="text-sm text-emerald-300">
              {`{"action":"water","on_behalf_of":用户ID}`}
            </code>
          </div>
          <p className="mt-2 text-xs text-slate-400">
            快捷指令中可添加「从菜单中选择」步骤，让用户选择为谁记录。
          </p>
        </div>

        {/* 排泄规律分析 */}
        <div className="mt-6 rounded-2xl border border-white/10 bg-white/5 p-5">
          <h2 className="mb-3 text-lg font-semibold text-white">数据分析</h2>
          <p className="text-sm leading-7 text-slate-300">
            积累 1-2 周数据后，系统可以分析排泄规律：排便频率、高峰时段、平均时长、规律性评分、夜尿次数等。在 AI 助手中直接问"分析我的排泄规律"即可。
          </p>
        </div>

        {/* 功能说明 */}
        <div className="mt-6 rounded-2xl border border-white/10 bg-white/5 p-5">
          <h2 className="mb-3 text-lg font-semibold text-white">防误触机制</h2>
          <ul className="space-y-2">
            <li className="flex items-start gap-2 text-sm text-slate-300">
              <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-400" />
              饮水和小便：8 秒内重复碰触自动去重
            </li>
            <li className="flex items-start gap-2 text-sm text-slate-300">
              <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-400" />
              大便计时：超过 60 分钟自动过期，不会记录错误数据
            </li>
            <li className="flex items-start gap-2 text-sm text-slate-300">
              <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-400" />
              计时器持久化：服务器重启不会丢失正在进行的计时
            </li>
          </ul>
        </div>

        {/* 补剂 NFC 打卡 */}
        <div className="mt-6 rounded-2xl border border-emerald-500/20 bg-emerald-500/5 p-5">
          <div className="mb-3 flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-500/20 text-emerald-400">
              <span className="text-lg">💊</span>
            </div>
            <h2 className="text-lg font-semibold text-emerald-200">补剂 NFC 打卡</h2>
          </div>
          <p className="mb-4 text-sm leading-7 text-slate-300">
            每个药瓶/药盒贴一个 NFC 标签，碰一下即完成打卡。推荐使用<strong className="text-white">分组打卡</strong>：只需 4 个标签（早/午/晚/睡前），一碰打卡该时段所有补剂。
          </p>

          {/* 分组打卡（推荐） */}
          <div className="mb-4">
            <h3 className="mb-2 text-sm font-semibold text-emerald-300">方式一：分组打卡（推荐）</h3>
            <p className="mb-3 text-xs text-slate-400">4 个标签覆盖全部补剂，贴在药盒/桌面上</p>
            <div className="space-y-2">
              {[
                { timing: 'morning', label: '早上', emoji: '🌅' },
                { timing: 'noon', label: '午间', emoji: '☀️' },
                { timing: 'evening', label: '晚间', emoji: '🌆' },
                { timing: 'bedtime', label: '睡前', emoji: '🌙' },
              ].map(({ timing, label, emoji }) => {
                const count = supplements.filter(s => s.timing === timing).length;
                if (count === 0) return null;
                const body = JSON.stringify({ action: 'supplement_group', timing });
                return (
                  <div key={timing} className="rounded-xl bg-slate-800/60 p-3">
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-white">
                        {emoji} {label}（{count} 种）
                      </span>
                      <div className="flex items-center gap-2">
                        <code className="text-xs text-emerald-300">{body}</code>
                        <button
                          onClick={() => copyToClipboard(body, `group-${timing}`)}
                          className="text-slate-500 hover:text-white text-xs"
                        >
                          {copied === `group-${timing}` ? '✓' : '复制'}
                        </button>
                      </div>
                    </div>
                    <div className="mt-1 text-xs text-slate-500">
                      {supplements.filter(s => s.timing === timing).map(s => s.name).join('、')}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* 单个补剂打卡 */}
          <details className="group">
            <summary className="mb-2 cursor-pointer text-sm font-semibold text-slate-400 hover:text-white">
              方式二：单个补剂打卡（点击展开）
            </summary>
            <p className="mb-3 text-xs text-slate-400">每个药瓶贴独立标签，碰一下只打卡该补剂</p>
            <div className="space-y-1.5 max-h-64 overflow-y-auto">
              {supplements.map(s => {
                const body = JSON.stringify({ action: 'supplement', supplement_id: s.id });
                return (
                  <div key={s.id} className="flex items-center justify-between rounded-lg bg-slate-900/60 px-3 py-2">
                    <span className="text-xs text-slate-200 truncate max-w-[160px]">{s.name}</span>
                    <div className="flex items-center gap-2">
                      <code className="text-[10px] text-emerald-300/70">{`id:${s.id}`}</code>
                      <button
                        onClick={() => copyToClipboard(body, `supp-${s.id}`)}
                        className="text-slate-500 hover:text-white text-xs"
                      >
                        {copied === `supp-${s.id}` ? '✓' : '复制'}
                      </button>
                    </div>
                  </div>
                );
              })}
              {supplements.length === 0 && (
                <p className="text-xs text-slate-500 py-2">暂无活跃补剂</p>
              )}
            </div>
          </details>

          {/* 快捷指令配置 */}
          <div className="mt-4 rounded-xl bg-slate-900/80 p-3">
            <div className="text-xs text-slate-400 mb-2">快捷指令配置（和饮水相同）：</div>
            <div className="space-y-1.5 text-xs">
              <div className="flex items-center justify-between">
                <span className="text-slate-500">URL</span>
                <code className="text-blue-300">{apiBase}/nfc/tap</code>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-500">Method</span>
                <span className="text-emerald-300">POST</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-500">Header</span>
                <code className="text-yellow-300">X-API-Key: 你的Key</code>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-500">Body</span>
                <span className="text-slate-300">按上方复制的内容</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
