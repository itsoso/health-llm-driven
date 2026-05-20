'use client';

import { useState, useEffect, useCallback } from 'react';
import { api } from '@/services/api/client';
import { openclawSkillsApi } from '@/services/api/ai';
import { useAuth } from '@/contexts/AuthContext';

// API 路径前缀（代理 + Raw URL 共用）
const API_PREFIX = '/api';
// 公开 Raw URL 的域名前缀
const PUBLIC_URL = 'https://health.executor.life/api';

interface ApiKey {
  id: number;
  name: string;
  api_key: string | null;
  scopes: string;
  is_active: boolean;
  last_used_at: string | null;
  created_at: string;
}

interface SkillItem {
  name: string;
  description: string;
  version: string;
  slug: string;
}

interface SkillDetail {
  name: string;
  description: string;
  version: string;
  slug: string;
  content: string;
  raw_url: string;
}

interface InstalledSkill {
  name: string;
  description: string;
  version: string;
  enabled: boolean;
  has_env: boolean;
  env_keys: string[];
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
  if (navigator.clipboard) {
    navigator.clipboard.writeText(text).catch(() => {
      const ta = document.createElement('textarea');
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
    });
  }
}

type SkillFormat = 'openclaw' | 'claude-code';

function SkillCard({
  skill,
  token,
  isExpanded,
  onToggle,
  format,
  installed,
  isAdmin,
  isLoggedIn,
  onInstall,
  onUninstall,
  onToggleEnabled,
  installing,
}: {
  skill: SkillItem;
  token: string;
  isExpanded: boolean;
  onToggle: () => void;
  format: SkillFormat;
  installed: InstalledSkill | null;
  isAdmin: boolean;
  isLoggedIn: boolean;
  onInstall: () => void;
  onUninstall: () => void;
  onToggleEnabled: (enabled: boolean) => void;
  installing: boolean;
}) {
  const [copied, setCopied] = useState(false);
  const [detail, setDetail] = useState<SkillDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  useEffect(() => {
    if (isExpanded && !detail) {
      setLoadingDetail(true);
      fetch(`${API_PREFIX}/skills/${skill.slug}`)
        .then(res => res.json())
        .then(data => setDetail(data))
        .catch(() => {})
        .finally(() => setLoadingDetail(false));
    }
  }, [isExpanded, detail, skill.slug]);

  const getRawUrl = () => `${PUBLIC_URL}/skills/${skill.slug}/raw`;

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (detail) {
      copyToClipboard(detail.content);
    } else {
      copyToClipboard(getRawUrl());
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleCopyRawUrl = (e: React.MouseEvent) => {
    e.stopPropagation();
    copyToClipboard(getRawUrl());
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleInstall = (e: React.MouseEvent) => {
    e.stopPropagation();
    onInstall();
  };

  const handleUninstall = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (confirm(`确定从 OpenClaw 服务器删除 ${skill.name}？`)) {
      onUninstall();
    }
  };

  const handleToggleEnabled = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (installed) {
      onToggleEnabled(!installed.enabled);
    }
  };

  const color = COLOR_MAP[skill.slug] || 'from-gray-500 to-slate-500';
  const emoji = EMOJI_MAP[skill.slug] || '📦';

  return (
    <div className="bg-[#1e1a2e] rounded-xl border border-purple-900/30 overflow-hidden">
      <div
        className="flex items-center justify-between p-5 cursor-pointer hover:bg-white/[0.02] transition-colors"
        onClick={onToggle}
      >
        <div className="flex items-center gap-4">
          <div className={`w-12 h-12 rounded-xl bg-gradient-to-br ${color} flex items-center justify-center text-2xl shadow-lg`}>
            {emoji}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-lg font-semibold text-white">{skill.name}</h3>
              <span className="text-xs text-gray-500 font-mono">v{skill.version}</span>
              {installed && (
                <span className={`text-xs px-2 py-0.5 rounded-full ${
                  installed.enabled
                    ? 'bg-green-600/20 text-green-400 border border-green-500/30'
                    : 'bg-gray-600/20 text-gray-400 border border-gray-500/30'
                }`}>
                  {installed.enabled ? '已启用' : '已禁用'}
                </span>
              )}
            </div>
            <p className="text-sm text-gray-400 mt-0.5">{skill.description}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {/* 安装/管理按钮 (admin + openclaw mode) */}
          {isAdmin && format === 'openclaw' && (
            installed ? (
              <div className="flex items-center gap-1.5">
                <button
                  onClick={handleToggleEnabled}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                    installed.enabled
                      ? 'bg-yellow-600/20 text-yellow-300 border border-yellow-500/30 hover:bg-yellow-600/30'
                      : 'bg-green-600/20 text-green-300 border border-green-500/30 hover:bg-green-600/30'
                  }`}
                >
                  {installed.enabled ? '禁用' : '启用'}
                </button>
                <button
                  onClick={handleUninstall}
                  className="px-3 py-1.5 rounded-lg text-xs font-medium bg-red-600/20 text-red-300 border border-red-500/30 hover:bg-red-600/30 transition-all"
                >
                  卸载
                </button>
              </div>
            ) : (
              <button
                onClick={handleInstall}
                disabled={installing || !token}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                  installing
                    ? 'bg-purple-600/20 text-purple-300 border border-purple-500/30 cursor-wait'
                    : !token
                    ? 'bg-gray-600/20 text-gray-400 border border-gray-500/30 cursor-not-allowed'
                    : 'bg-purple-600 text-white hover:bg-purple-500 shadow-lg shadow-purple-600/20'
                }`}
              >
                {installing ? '安装中...' : '安装到 OpenClaw'}
              </button>
            )
          )}
          <button
            onClick={handleCopy}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
              copied
                ? 'bg-green-600/20 text-green-400 border border-green-500/30'
                : 'bg-white/5 text-gray-400 border border-purple-900/30 hover:bg-white/10 hover:text-white'
            }`}
          >
            {copied ? '已复制 ✓' : '复制'}
          </button>
          <svg
            className={`w-5 h-5 text-gray-400 transition-transform duration-200 ${isExpanded ? 'rotate-180' : ''}`}
            fill="none" viewBox="0 0 24 24" stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </div>
      {isExpanded && (
        <div className="border-t border-purple-900/30 p-5">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-mono text-gray-500">
              Raw URL: {PUBLIC_URL}/skills/{skill.slug}/raw
            </span>
            <div className="flex items-center gap-2">
              <button onClick={handleCopyRawUrl} className="text-xs px-3 py-1.5 rounded-md bg-white/5 text-gray-400 hover:bg-white/10 hover:text-white transition-all">
                复制 URL
              </button>
              <a
                href={getRawUrl()}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs px-3 py-1.5 rounded-md bg-white/5 text-gray-400 hover:bg-white/10 hover:text-white transition-all"
              >
                查看原文
              </a>
            </div>
          </div>
          {loadingDetail ? (
            <div className="text-center text-gray-500 text-sm py-8">加载中...</div>
          ) : detail ? (
            <>
              {isLoggedIn && token ? (
                <div className="mb-3 flex items-center gap-2 text-xs text-green-400">
                  <span>✓</span>
                  <span>已绑定 API Key</span>
                </div>
              ) : isLoggedIn ? (
                <div className="mb-3 flex items-center gap-2 text-xs text-amber-400">
                  <span>⚠</span>
                  <span>请先创建 API Key</span>
                </div>
              ) : null}
              <pre className="bg-[#0d0b14] rounded-lg p-4 overflow-x-auto text-sm text-gray-300 font-mono leading-relaxed border border-purple-900/20 max-h-[500px] overflow-y-auto whitespace-pre-wrap">
                {detail.content}
              </pre>
            </>
          ) : (
            <div className="text-center text-gray-500 text-sm py-8">加载失败</div>
          )}
        </div>
      )}
    </div>
  );
}

export default function SkillsPage() {
  const { user } = useAuth();
  const isLoggedIn = !!user;
  const isOwner = user?.email === 'itsoso@126.com';
  const isAdmin = isOwner;

  const [skills, setSkills] = useState<SkillItem[]>([]);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [apiKeys, setApiKeys] = useState<ApiKey[]>([]);
  const [activeToken, setActiveToken] = useState('');
  const [newKeyName, setNewKeyName] = useState('');
  const [creating, setCreating] = useState(false);
  const [newlyCreatedKey, setNewlyCreatedKey] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [skillsLoading, setSkillsLoading] = useState(true);
  const [skillFormat, setSkillFormat] = useState<SkillFormat>('openclaw');

  // OpenClaw 远程管理 state
  const [installedSkills, setInstalledSkills] = useState<InstalledSkill[]>([]);
  const [gatewayStatus, setGatewayStatus] = useState<{ status: string; uptime: string } | null>(null);
  const [installing, setInstalling] = useState<Record<string, boolean>>({});
  const [needRestart, setNeedRestart] = useState(false);
  const [restarting, setRestarting] = useState(false);
  const [loadingRemote, setLoadingRemote] = useState(false);

  // 从后端 API 加载 Skills（公开，无需认证）
  useEffect(() => {
    fetch(`${API_PREFIX}/skills`)
      .then(res => res.json())
      .then(data => setSkills(data))
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
      // ignore
    } finally {
      setLoading(false);
    }
  }, [isLoggedIn]);

  const loadRemoteStatus = useCallback(async () => {
    if (!isAdmin) return;
    setLoadingRemote(true);
    try {
      const [skillsRes, gwRes] = await Promise.all([
        openclawSkillsApi.listInstalled(),
        openclawSkillsApi.gatewayStatus(),
      ]);
      setInstalledSkills(skillsRes.data);
      setGatewayStatus(gwRes.data);
    } catch {
      // non-admin or server unreachable
    } finally {
      setLoadingRemote(false);
    }
  }, [isAdmin]);

  useEffect(() => { loadApiKeys(); }, [loadApiKeys]);
  useEffect(() => { loadRemoteStatus(); }, [loadRemoteStatus]);

  // 从 localStorage 恢复选中的 token
  useEffect(() => {
    const saved = localStorage.getItem('skills_active_token');
    if (saved) setActiveToken(saved);
  }, []);

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
        setActiveToken(key.api_key);
        localStorage.setItem('skills_active_token', key.api_key);
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

  // 安装 Skill 到 OpenClaw
  const handleInstallSkill = async (skill: SkillItem) => {
    if (!activeToken) {
      alert('请先创建 API Key');
      return;
    }
    setInstalling((prev) => ({ ...prev, [skill.slug]: true }));
    try {
      // 获取原始 SKILL.md 内容
      const res = await fetch(`${PUBLIC_URL}/skills/${skill.slug}/raw`);
      const skillContent = await res.text();
      await openclawSkillsApi.install(
        skill.slug,
        skillContent,
        true,
        { HEALTH_API_URL: PUBLIC_URL, HEALTH_API_TOKEN: activeToken },
        activeToken,
      );
      setNeedRestart(true);
      await loadRemoteStatus();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '安装失败';
      alert(`安装失败: ${msg}`);
    } finally {
      setInstalling((prev) => ({ ...prev, [skill.slug]: false }));
    }
  };

  const handleUninstallSkill = async (name: string) => {
    try {
      await openclawSkillsApi.remove(name);
      setNeedRestart(true);
      await loadRemoteStatus();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '卸载失败';
      alert(`卸载失败: ${msg}`);
    }
  };

  const handleToggleSkill = async (name: string, enabled: boolean) => {
    try {
      await openclawSkillsApi.toggle(name, enabled);
      setNeedRestart(true);
      await loadRemoteStatus();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '操作失败';
      alert(`操作失败: ${msg}`);
    }
  };

  const handleRestartGateway = async () => {
    setRestarting(true);
    try {
      await openclawSkillsApi.restartGateway();
      setNeedRestart(false);
      await loadRemoteStatus();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '重启失败';
      alert(`重启失败: ${msg}`);
    } finally {
      setRestarting(false);
    }
  };

  const getInstalledInfo = (slug: string): InstalledSkill | null => {
    return installedSkills.find((s) => s.name === slug) || null;
  };

  const [manifestCopied, setManifestCopied] = useState(false);
  const manifestUrl = `${PUBLIC_URL}/skills/manifest.json`;

  const handleCopyManifest = () => {
    copyToClipboard(manifestUrl);
    setManifestCopied(true);
    setTimeout(() => setManifestCopied(false), 2000);
  };

  return (
    <div className="min-h-screen bg-[#13111a] text-white">
      <div className="max-w-4xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-white mb-2">OpenClaw Skills</h1>
          <p className="text-gray-400">
            Health Management System 的 AI Skills 目录。其他 Claw 可直接安装使用。
          </p>
        </div>

        {/* 使用说明 */}
        <div className="bg-[#1e1a2e] rounded-xl border border-purple-900/30 p-5 mb-6">
          <h2 className="text-sm font-semibold text-purple-300 mb-3">使用说明</h2>
          <div className="space-y-3 text-sm text-gray-300 leading-7">
            <div className="flex items-start gap-3">
              <span className="mt-1 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-purple-600/30 text-xs text-purple-300">1</span>
              <div><span className="text-white font-medium">安装到本系统</span> — 点击下方 Skill 卡片的「安装」按钮，自动部署到 OpenClaw Gateway。</div>
            </div>
            <div className="flex items-start gap-3">
              <span className="mt-1 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-purple-600/30 text-xs text-purple-300">2</span>
              <div><span className="text-white font-medium">安装到其他 OpenClaw</span> — 复制 Skill 内容（点「查看内容」后复制），粘贴到目标 OpenClaw 对话中发送即可。</div>
            </div>
            <div className="flex items-start gap-3">
              <span className="mt-1 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-purple-600/30 text-xs text-purple-300">3</span>
              <div><span className="text-white font-medium">批量安装/更新</span> — 复制下方 Manifest URL，在 OpenClaw 中使用即可获取全部 Skills。</div>
            </div>
            <div className="flex items-start gap-3">
              <span className="mt-1 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-purple-600/30 text-xs text-purple-300">4</span>
              <div><span className="text-white font-medium">API 获取</span> — <code className="rounded bg-[#0d0b14] px-1.5 py-0.5 text-purple-300 text-xs">GET /api/v1/skills/{'{name}'}/raw</code> 返回完整 SKILL.md 内容，<code className="rounded bg-[#0d0b14] px-1.5 py-0.5 text-purple-300 text-xs">GET /api/v1/skills/{'{name}'}/install-command</code> 返回一键安装命令。</div>
            </div>
          </div>
          <p className="text-xs text-gray-500 mt-3">
            Skills 在每次后端部署时自动同步到 Gateway，无需手动更新。
          </p>
        </div>

        {/* Manifest URL - 一键安装 */}
        <div className="bg-[#1e1a2e] rounded-xl border border-purple-900/30 p-5 mb-6">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-purple-300 flex items-center gap-2">
              Skills Manifest
            </h2>
            <button
              onClick={handleCopyManifest}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                manifestCopied
                  ? 'bg-green-600/20 text-green-400 border border-green-500/30'
                  : 'bg-purple-600 text-white hover:bg-purple-500'
              }`}
            >
              {manifestCopied ? 'Copied' : 'Copy URL'}
            </button>
          </div>
          <div className="bg-[#0d0b14] rounded-lg p-4 border border-purple-900/20 font-mono text-sm space-y-2">
            <div className="flex items-start gap-3">
              <span className="text-gray-500 w-28 flex-shrink-0">Manifest URL:</span>
              <span className="text-purple-300 break-all cursor-pointer hover:text-purple-200 transition-colors" onClick={handleCopyManifest}>{manifestUrl}</span>
            </div>
            <div className="flex items-start gap-3">
              <span className="text-gray-500 w-28 flex-shrink-0">Auth Type:</span>
              <span className="text-gray-300">Bearer Token</span>
            </div>
            <div className="flex items-start gap-3">
              <span className="text-gray-500 w-28 flex-shrink-0">API Key:</span>
              <span className="text-gray-300">{activeToken ? activeToken : <span className="text-gray-500 italic">登录后创建 API Key</span>}</span>
            </div>
          </div>
          <p className="text-xs text-gray-500 mt-3">
            复制 Manifest URL 即可一键安装或更新所有 Skills。
          </p>
        </div>

        {/* Gateway 状态 (admin only) */}
        {isAdmin && skillFormat === 'openclaw' && (
          <div className={`rounded-xl border p-4 mb-6 ${
            needRestart
              ? 'bg-amber-900/20 border-amber-500/30'
              : 'bg-[#1e1a2e] border-purple-900/30'
          }`}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="text-lg">
                  {loadingRemote ? '...' : gatewayStatus?.status === 'active' ? '🟢' : '🔴'}
                </span>
                <div>
                  <h2 className="text-sm font-semibold text-white">OpenClaw Gateway</h2>
                  <p className="text-xs text-gray-400">
                    {loadingRemote
                      ? '正在连接服务器...'
                      : gatewayStatus
                      ? `状态: ${gatewayStatus.status} · 已安装 ${installedSkills.length} 个 Skills`
                      : '无法连接到 OpenClaw 服务器'}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {needRestart && (
                  <span className="text-xs text-amber-400 bg-amber-600/20 px-2.5 py-1 rounded-full border border-amber-500/30">
                    需要重启生效
                  </span>
                )}
                <button
                  onClick={handleRestartGateway}
                  disabled={restarting || loadingRemote}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                    needRestart
                      ? 'bg-amber-600 text-white hover:bg-amber-500 shadow-lg shadow-amber-600/20'
                      : 'bg-white/5 text-gray-300 border border-purple-900/30 hover:bg-white/10'
                  } disabled:opacity-50 disabled:cursor-not-allowed`}
                >
                  {restarting ? '重启中...' : '重启 Gateway'}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* 格式选择 + 使用说明 */}
        <div className="bg-[#1e1a2e] rounded-xl border border-purple-900/30 p-5 mb-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-purple-300">使用方法</h2>
            <div className="flex items-center gap-1 bg-[#0d0b14] rounded-lg p-1 border border-purple-900/30">
              <button
                onClick={() => setSkillFormat('openclaw')}
                className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                  skillFormat === 'openclaw'
                    ? 'bg-purple-600 text-white shadow-sm'
                    : 'text-gray-400 hover:text-white'
                }`}
              >
                OpenClaw
              </button>
              <button
                onClick={() => setSkillFormat('claude-code')}
                className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                  skillFormat === 'claude-code'
                    ? 'bg-purple-600 text-white shadow-sm'
                    : 'text-gray-400 hover:text-white'
                }`}
              >
                Claude Code
              </button>
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
            <div className="flex items-start gap-3">
              <span className="w-6 h-6 rounded-full bg-purple-600/30 text-purple-300 flex items-center justify-center text-xs font-bold flex-shrink-0">1</span>
              <div>
                <p className="text-white font-medium">浏览 Skills</p>
                <p className="text-gray-400 mt-0.5">点击展开查看详情和 API 文档</p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <span className="w-6 h-6 rounded-full bg-purple-600/30 text-purple-300 flex items-center justify-center text-xs font-bold flex-shrink-0">2</span>
              <div>
                <p className="text-white font-medium">获取 Raw URL</p>
                <p className="text-gray-400 mt-0.5">复制 SKILL.md 的直链地址</p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <span className="w-6 h-6 rounded-full bg-purple-600/30 text-purple-300 flex items-center justify-center text-xs font-bold flex-shrink-0">3</span>
              <div>
                <p className="text-white font-medium">安装到你的 Claw</p>
                <p className="text-gray-400 mt-0.5">
                  保存至 <code className="text-purple-300 bg-purple-900/30 px-1 rounded">
                    {skillFormat === 'openclaw' ? '~/.openclaw/skills/' : '~/.claude/skills/'}
                  </code>
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* API Key 管理（仅登录用户可见）*/}
        {isLoggedIn && (
          <div className="bg-[#1e1a2e] rounded-xl border border-purple-900/30 p-5 mb-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-base font-semibold text-white flex items-center gap-2">
                🔑 API Key 管理
              </h2>
              <div className="flex items-center gap-2 text-xs text-gray-500">
                <span className="inline-block w-2 h-2 rounded-full bg-green-500"></span>
                API: {PUBLIC_URL}
              </div>
            </div>

            {/* 创建新 Key */}
            <div className="flex gap-2 mb-4">
              <input
                type="text"
                value={newKeyName}
                onChange={(e) => setNewKeyName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.nativeEvent.isComposing || e.keyCode === 229) return;
                  if (e.key === 'Enter') handleCreateKey();
                }}
                placeholder="输入名称（如：OpenClaw、Claude Code）"
                className="flex-1 bg-[#0d0b14] border border-purple-900/30 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-purple-500/50"
              />
              <button
                onClick={handleCreateKey}
                disabled={creating || !newKeyName.trim()}
                className="px-4 py-2 bg-purple-600 hover:bg-purple-500 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg text-sm font-medium transition-all whitespace-nowrap"
              >
                {creating ? '创建中...' : '创建 Key'}
              </button>
            </div>

            {/* 新创建的 Key 提示 */}
            {newlyCreatedKey && (
              <div className="mb-4 p-3 bg-green-900/20 border border-green-500/30 rounded-lg">
                <div className="flex items-start gap-2">
                  <span className="text-green-400 text-sm mt-0.5">✓</span>
                  <div className="flex-1">
                    <p className="text-sm text-green-300 font-medium mb-1">API Key 创建成功！仅显示一次，请立即保存</p>
                    <div className="flex items-center gap-2">
                      <code className="text-xs bg-black/30 px-2 py-1 rounded text-green-200 font-mono break-all">{newlyCreatedKey}</code>
                      <button
                        onClick={() => copyToClipboard(newlyCreatedKey)}
                        className="text-xs px-2 py-1 bg-green-600/30 text-green-300 rounded hover:bg-green-600/40 transition-all whitespace-nowrap"
                      >
                        复制
                      </button>
                    </div>
                  </div>
                  <button onClick={() => setNewlyCreatedKey(null)} className="text-gray-500 hover:text-white text-xs">✕</button>
                </div>
              </div>
            )}

            {/* 已有 Key 列表 */}
            {loading ? (
              <div className="text-center text-gray-500 text-sm py-4">加载中...</div>
            ) : apiKeys.length === 0 ? (
              <div className="text-center text-gray-500 text-sm py-4">
                暂无 API Key，创建后即可安装 Skills
              </div>
            ) : (
              <div className="space-y-2">
                {apiKeys.map((k) => (
                  <div key={k.id} className="flex items-center justify-between px-3 py-2.5 bg-[#0d0b14] rounded-lg border border-purple-900/20">
                    <div className="flex items-center gap-3">
                      <span className={`w-2 h-2 rounded-full ${k.is_active ? 'bg-green-500' : 'bg-gray-600'}`}></span>
                      <div>
                        <span className="text-sm text-white font-medium">{k.name}</span>
                        <span className="text-xs text-gray-500 ml-2">
                          {k.scopes} · {new Date(k.created_at).toLocaleDateString('zh-CN')}
                        </span>
                      </div>
                    </div>
                    <button
                      onClick={() => handleDeleteKey(k.id)}
                      className="text-xs text-red-400/60 hover:text-red-400 transition-all px-2 py-1"
                    >
                      删除
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Skill Cards */}
        {skillsLoading ? (
          <div className="flex justify-center py-20">
            <div className="w-8 h-8 border-2 border-purple-300 border-t-purple-600 rounded-full animate-spin" />
          </div>
        ) : (
          <div className="space-y-4">
            {skills.map((skill) => (
              <SkillCard
                key={skill.slug}
                skill={skill}
                token={activeToken}
                isExpanded={expandedId === skill.slug}
                onToggle={() => setExpandedId(expandedId === skill.slug ? null : skill.slug)}
                format={skillFormat}
                installed={getInstalledInfo(skill.slug)}
                isAdmin={isAdmin}
                isLoggedIn={isLoggedIn}
                onInstall={() => handleInstallSkill(skill)}
                onUninstall={() => handleUninstallSkill(skill.slug)}
                onToggleEnabled={(enabled) => handleToggleSkill(skill.slug, enabled)}
                installing={installing[skill.slug] || false}
              />
            ))}
          </div>
        )}

        {/* 安全说明 */}
        <div className="mt-8 bg-[#1e1a2e] rounded-xl border border-amber-500/30 p-5">
          <div className="flex items-start gap-3">
            <span className="text-xl">🔐</span>
            <div>
              <h2 className="text-sm font-semibold text-amber-300 mb-2">数据安全说明</h2>
              <ul className="text-sm text-gray-300 space-y-1.5">
                <li>每个用户使用<strong className="text-white">自己的 API Key</strong>，Key 与账号绑定，仅能访问本人数据</li>
                <li>Skills 使用环境变量 <code className="text-purple-300 bg-purple-900/30 px-1 rounded">$HEALTH_API_TOKEN</code> 引用 Key，不硬编码</li>
                <li>请勿将 Key 分享给他人或提交到公开代码仓库</li>
                {!isLoggedIn && (
                  <li className="text-amber-300">登录后可创建 API Key 并一键安装 Skills</li>
                )}
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
