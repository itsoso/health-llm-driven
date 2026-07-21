'use client';

import { useCallback, useEffect, useState } from 'react';
import type { MouseEvent } from 'react';
import { api } from '@/services/api/client';
import { useAuth } from '@/contexts/AuthContext';

const API_PREFIX = '/api';
const PUBLIC_URL = 'https://health.executor.life/api';

interface ApiKey {
  id: number;
  name: string;
  api_key: string | null;
  scopes: string;
  is_active: boolean;
  created_at: string;
}

interface SkillItem {
  name: string;
  description: string;
  version: string;
  slug: string;
}

interface SkillDetail extends SkillItem {
  content: string;
  raw_url: string;
}

const EMOJI_MAP: Record<string, string> = {
  'health-query': '🔍',
  'health-record': '📝',
  'health-analysis': '🧠',
  'rhinitis-tracker': '👃',
  'multi-model-analyze': '🤖',
};

const COLOR_MAP: Record<string, string> = {
  'health-query': 'from-blue-500 to-cyan-500',
  'health-record': 'from-green-500 to-emerald-500',
  'health-analysis': 'from-purple-500 to-pink-500',
  'rhinitis-tracker': 'from-orange-500 to-amber-500',
  'multi-model-analyze': 'from-indigo-500 to-violet-500',
};

function copyToClipboard(text: string) {
  if (!navigator.clipboard) return;
  navigator.clipboard.writeText(text).catch(() => {});
}

function SkillCard({
  skill,
  isExpanded,
  onToggle,
}: {
  skill: SkillItem;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const [detail, setDetail] = useState<SkillDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const color = COLOR_MAP[skill.slug] || 'from-gray-500 to-slate-500';
  const emoji = EMOJI_MAP[skill.slug] || '📦';
  const rawUrl = `${PUBLIC_URL}/skills/${skill.slug}/raw`;

  useEffect(() => {
    if (!isExpanded || detail || loadingDetail) return;
    setLoadingDetail(true);
    fetch(`${API_PREFIX}/skills/${skill.slug}`)
      .then((res) => res.json())
      .then((data) => setDetail(data))
      .catch(() => {})
      .finally(() => setLoadingDetail(false));
  }, [isExpanded, detail, loadingDetail, skill.slug]);

  const handleCopy = (text: string, e?: MouseEvent) => {
    e?.stopPropagation();
    copyToClipboard(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  };

  return (
    <div className="overflow-hidden rounded-xl border border-purple-900/30 bg-[#1e1a2e]">
      <div
        className="flex cursor-pointer items-center justify-between gap-4 p-5 transition-colors hover:bg-white/[0.03]"
        onClick={onToggle}
      >
        <div className="flex items-center gap-4">
          <div className={`flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br ${color} text-2xl shadow-lg`}>
            {emoji}
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-lg font-semibold text-white">{skill.name}</h3>
              <span className="font-mono text-xs text-gray-500">v{skill.version}</span>
            </div>
            <p className="mt-0.5 text-sm text-gray-400">{skill.description}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={(e) => handleCopy(detail?.content || rawUrl, e)}
            className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition-all ${
              copied
                ? 'border-green-500/30 bg-green-600/20 text-green-400'
                : 'border-purple-900/30 bg-white/5 text-gray-400 hover:bg-white/10 hover:text-white'
            }`}
          >
            {copied ? '已复制' : '复制'}
          </button>
          <svg
            className={`h-5 w-5 text-gray-400 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </div>
      {isExpanded && (
        <div className="border-t border-purple-900/30 p-5">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2 text-xs">
            <span className="break-all font-mono text-gray-500">Raw URL: {rawUrl}</span>
            <button
              onClick={(e) => handleCopy(rawUrl, e)}
              className="rounded-md bg-white/5 px-3 py-1.5 text-gray-400 transition-all hover:bg-white/10 hover:text-white"
            >
              复制 URL
            </button>
          </div>
          {loadingDetail ? (
            <div className="py-8 text-center text-sm text-gray-500">加载中...</div>
          ) : detail ? (
            <pre className="max-h-[500px] overflow-auto whitespace-pre-wrap rounded-lg border border-purple-900/20 bg-[#0d0b14] p-4 font-mono text-sm leading-relaxed text-gray-300">
              {detail.content}
            </pre>
          ) : (
            <div className="py-8 text-center text-sm text-gray-500">加载失败</div>
          )}
        </div>
      )}
    </div>
  );
}

export default function SkillsPage() {
  const { user } = useAuth();
  const isLoggedIn = !!user;
  const [skills, setSkills] = useState<SkillItem[]>([]);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [apiKeys, setApiKeys] = useState<ApiKey[]>([]);
  const [newKeyName, setNewKeyName] = useState('');
  const [newlyCreatedKey, setNewlyCreatedKey] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [skillsLoading, setSkillsLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [manifestCopied, setManifestCopied] = useState(false);
  const manifestUrl = `${PUBLIC_URL}/skills/manifest.json`;

  useEffect(() => {
    fetch(`${API_PREFIX}/skills`)
      .then((res) => res.json())
      .then((data) => setSkills(data))
      .catch(() => {})
      .finally(() => setSkillsLoading(false));
  }, []);

  const loadApiKeys = useCallback(async () => {
    if (!isLoggedIn) {
      setLoading(false);
      return;
    }
    try {
      const res = await api.get('/v1/user-api-keys');
      setApiKeys(res.data);
    } catch {
      // keep page readable when API key management is unavailable
    } finally {
      setLoading(false);
    }
  }, [isLoggedIn]);

  useEffect(() => {
    loadApiKeys();
  }, [loadApiKeys]);

  const handleCopyManifest = () => {
    copyToClipboard(manifestUrl);
    setManifestCopied(true);
    setTimeout(() => setManifestCopied(false), 1800);
  };

  const handleCreateKey = async () => {
    if (!newKeyName.trim()) return;
    setCreating(true);
    try {
      const res = await api.post('/v1/user-api-keys', {
        name: newKeyName.trim(),
        scopes: 'read,write',
      });
      const key = res.data;
      if (key.api_key) {
        setNewlyCreatedKey(key.api_key);
      }
      setNewKeyName('');
      loadApiKeys();
    } catch {
      alert('创建失败，每个用户最多 10 个 API Key');
    } finally {
      setCreating(false);
    }
  };

  const handleDeleteKey = async (id: number) => {
    if (!confirm('确定删除此 API Key？')) return;
    try {
      await api.delete(`/v1/user-api-keys/${id}`);
      loadApiKeys();
    } catch {
      // ignore
    }
  };

  return (
    <div className="min-h-screen bg-[#13111a] text-white">
      <div className="mx-auto max-w-4xl px-4 py-8">
        <div className="mb-8">
          <h1 className="mb-2 text-2xl font-bold">Agent Skills</h1>
          <p className="text-gray-400">
            小巴自有 Agent 可用的健康技能目录。这里保留读取、复制、Manifest 和 API Key 管理，不再分发到外部网关。
          </p>
        </div>

        <div className="mb-6 rounded-xl border border-purple-900/30 bg-[#1e1a2e] p-5">
          <h2 className="mb-3 text-sm font-semibold text-purple-300">使用方式</h2>
          <div className="grid gap-4 text-sm md:grid-cols-3">
            {[
              ['浏览 Skills', '展开卡片查看 SKILL.md 内容和 API 说明'],
              ['复制 Raw URL', '给研发 Agent 或内部工具读取技能定义'],
              ['使用 API Key', '外部自动化只通过本人 API Key 访问本人数据'],
            ].map(([title, desc], index) => (
              <div key={title} className="flex items-start gap-3">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-purple-600/30 text-xs font-bold text-purple-300">
                  {index + 1}
                </span>
                <div>
                  <p className="font-medium text-white">{title}</p>
                  <p className="mt-0.5 text-gray-400">{desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="mb-6 rounded-xl border border-purple-900/30 bg-[#1e1a2e] p-5">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-purple-300">Skills Manifest</h2>
            <button
              onClick={handleCopyManifest}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-all ${
                manifestCopied ? 'bg-green-600/20 text-green-400' : 'bg-purple-600 text-white hover:bg-purple-500'
              }`}
            >
              {manifestCopied ? '已复制' : '复制 URL'}
            </button>
          </div>
          <div className="rounded-lg border border-purple-900/20 bg-[#0d0b14] p-4 font-mono text-sm">
            <span className="break-all text-purple-300">{manifestUrl}</span>
          </div>
        </div>

        {isLoggedIn && (
          <div className="mb-6 rounded-xl border border-purple-900/30 bg-[#1e1a2e] p-5">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-base font-semibold">API Key 管理</h2>
              <span className="text-xs text-gray-500">API: {PUBLIC_URL}</span>
            </div>
            <div className="mb-4 flex gap-2">
              <input
                type="text"
                value={newKeyName}
                onChange={(e) => setNewKeyName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.nativeEvent.isComposing || e.keyCode === 229) return;
                  if (e.key === 'Enter') handleCreateKey();
                }}
                placeholder="输入名称（如：小巴研发 Agent）"
                className="flex-1 rounded-lg border border-purple-900/30 bg-[#0d0b14] px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-purple-500/50 focus:outline-none"
              />
              <button
                onClick={handleCreateKey}
                disabled={creating || !newKeyName.trim()}
                className="rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium transition-all hover:bg-purple-500 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {creating ? '创建中...' : '创建 Key'}
              </button>
            </div>
            {newlyCreatedKey && (
              <div className="mb-4 rounded-lg border border-green-500/30 bg-green-900/20 p-3">
                <p className="mb-2 text-sm font-medium text-green-300">API Key 创建成功，仅显示一次。</p>
                <div className="flex items-center gap-2">
                  <code className="break-all rounded bg-black/30 px-2 py-1 font-mono text-xs text-green-200">{newlyCreatedKey}</code>
                  <button
                    onClick={() => copyToClipboard(newlyCreatedKey)}
                    className="whitespace-nowrap rounded bg-green-600/30 px-2 py-1 text-xs text-green-300 hover:bg-green-600/40"
                  >
                    复制
                  </button>
                </div>
              </div>
            )}
            {loading ? (
              <div className="py-4 text-center text-sm text-gray-500">加载中...</div>
            ) : apiKeys.length === 0 ? (
              <div className="py-4 text-center text-sm text-gray-500">暂无 API Key</div>
            ) : (
              <div className="space-y-2">
                {apiKeys.map((k) => (
                  <div key={k.id} className="flex items-center justify-between rounded-lg border border-purple-900/20 bg-[#0d0b14] px-3 py-2.5">
                    <div className="flex items-center gap-3">
                      <span className={`h-2 w-2 rounded-full ${k.is_active ? 'bg-green-500' : 'bg-gray-600'}`} />
                      <div>
                        <span className="text-sm font-medium text-white">{k.name}</span>
                        <span className="ml-2 text-xs text-gray-500">{k.scopes} · {new Date(k.created_at).toLocaleDateString('zh-CN')}</span>
                      </div>
                    </div>
                    <button
                      onClick={() => handleDeleteKey(k.id)}
                      className="px-2 py-1 text-xs text-red-400/70 transition-all hover:text-red-400"
                    >
                      删除
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {skillsLoading ? (
          <div className="flex justify-center py-20">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-purple-300 border-t-purple-600" />
          </div>
        ) : (
          <div className="space-y-4">
            {skills.map((skill) => (
              <SkillCard
                key={skill.slug}
                skill={skill}
                isExpanded={expandedId === skill.slug}
                onToggle={() => setExpandedId(expandedId === skill.slug ? null : skill.slug)}
              />
            ))}
          </div>
        )}

        <div className="mt-8 rounded-xl border border-amber-500/30 bg-[#1e1a2e] p-5">
          <h2 className="mb-2 text-sm font-semibold text-amber-300">数据安全说明</h2>
          <ul className="space-y-1.5 text-sm text-gray-300">
            <li>每个用户使用自己的 API Key，Key 与账号绑定，仅能访问本人数据。</li>
            <li>内部 Agent 通过受控 API 调用技能，不再依赖外部分发网关。</li>
            <li>请勿将 Key 分享给他人或提交到公开代码仓库。</li>
          </ul>
        </div>
      </div>
    </div>
  );
}
