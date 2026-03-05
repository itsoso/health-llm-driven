'use client';

import { useState, useEffect, useCallback } from 'react';
import ProtectedRoute from '@/components/ProtectedRoute';
import { api, openclawSkillsApi } from '@/services/api';
import { useAuth } from '@/contexts/AuthContext';

const API_URL = 'https://health.executor.life/api/v1';

interface ApiKey {
  id: number;
  name: string;
  api_key: string | null;
  scopes: string;
  is_active: boolean;
  last_used_at: string | null;
  created_at: string;
}

interface SkillDef {
  id: string;
  name: string;
  description: string;
  icon: string;
  color: string;
  toolCount: number;
  template: string;
}

interface InstalledSkill {
  name: string;
  description: string;
  version: string;
  enabled: boolean;
  has_env: boolean;
  env_keys: string[];
}

// SKILL.md 模板，用 {{API_URL}} 和 {{API_TOKEN}} 作占位符
const skillDefs: SkillDef[] = [
  {
    id: 'health-query',
    name: '健康数据查询',
    description: '查询步数、心率、睡眠、体重、血压、运动、饮食、打卡等健康数据',
    icon: '🔍',
    color: 'from-blue-500 to-cyan-500',
    toolCount: 13,
    template: `---
name: health-query
description: Query health data from the Health Management System - steps, heart rate, sleep, weight, blood pressure, workouts, diet, checkin status, and achievements. Use when the user asks about their health metrics, fitness data, or daily stats.
version: 1.0.0
metadata:
  openclaw:
    requires:
      env: [HEALTH_API_URL, HEALTH_API_TOKEN]
      bins: [curl]
    primaryEnv: HEALTH_API_TOKEN
    emoji: "🔍"
---

You have access to a Health Management System API. Use curl to query health data.

## Authentication
- URL: {{API_URL}}
- Header: \`Authorization: Bearer {{API_TOKEN}}\`

## Available Endpoints

### 综合健康数据（Garmin）
\`\`\`bash
curl -s -H "Authorization: Bearer {{API_TOKEN}}" "{{API_URL}}/garmin-analysis/me/comprehensive?days=7"
\`\`\`
返回：步数、心率、睡眠、压力、Body Battery 综合分析

### 睡眠数据
\`\`\`bash
curl -s -H "Authorization: Bearer {{API_TOKEN}}" "{{API_URL}}/garmin-analysis/me/sleep?days=7"
\`\`\`

### 心率数据
\`\`\`bash
curl -s -H "Authorization: Bearer {{API_TOKEN}}" "{{API_URL}}/garmin-analysis/me/heart-rate?days=7"
\`\`\`

### 活动数据
\`\`\`bash
curl -s -H "Authorization: Bearer {{API_TOKEN}}" "{{API_URL}}/garmin-analysis/me/activity?days=7"
\`\`\`

### 体重记录
\`\`\`bash
curl -s -H "Authorization: Bearer {{API_TOKEN}}" "{{API_URL}}/weight/records/me?limit=7"
\`\`\`

### 血压记录
\`\`\`bash
curl -s -H "Authorization: Bearer {{API_TOKEN}}" "{{API_URL}}/blood-pressure/records/me?limit=7"
\`\`\`

### 今日饮水
\`\`\`bash
curl -s -H "Authorization: Bearer {{API_TOKEN}}" "{{API_URL}}/water/records/me/date/$(date +%Y-%m-%d)"
\`\`\`

### 饮水统计
\`\`\`bash
curl -s -H "Authorization: Bearer {{API_TOKEN}}" "{{API_URL}}/water/records/me/stats?days=7"
\`\`\`

### 今日打卡
\`\`\`bash
curl -s -H "Authorization: Bearer {{API_TOKEN}}" "{{API_URL}}/checkin/records/today"
\`\`\`

### 打卡统计
\`\`\`bash
curl -s -H "Authorization: Bearer {{API_TOKEN}}" "{{API_URL}}/checkin/stats"
\`\`\`

### 运动记录
\`\`\`bash
curl -s -H "Authorization: Bearer {{API_TOKEN}}" "{{API_URL}}/workout/me?days=7"
\`\`\`

### 成就徽章
\`\`\`bash
curl -s -H "Authorization: Bearer {{API_TOKEN}}" "{{API_URL}}/achievements/me"
\`\`\`

### 健康评分
\`\`\`bash
curl -s -H "Authorization: Bearer {{API_TOKEN}}" "{{API_URL}}/health-score/daily/me"
\`\`\`

## Response Rules
- Always format responses in readable Chinese
- Include units (步, bpm, 分, kg, mmHg, ml)
- Highlight anomalies or notable changes
- Compare with targets when available`,
  },
  {
    id: 'health-record',
    name: '健康数据记录',
    description: '记录饮水、体重、血压、打卡、饮食等健康数据',
    icon: '📝',
    color: 'from-green-500 to-emerald-500',
    toolCount: 5,
    template: `---
name: health-record
description: Record health data - water intake, weight, blood pressure, checkins, and diet entries. Use when the user wants to log drinking water, weight, blood pressure, checkins, or meals.
version: 1.0.0
metadata:
  openclaw:
    requires:
      env: [HEALTH_API_URL, HEALTH_API_TOKEN]
      bins: [curl]
    primaryEnv: HEALTH_API_TOKEN
    emoji: "📝"
---

You can record health data via the Health Management System API.

## Authentication
- URL: {{API_URL}}
- Header: \`Authorization: Bearer {{API_TOKEN}}\`
- Content-Type: \`application/json\`

## Available Actions

### 记录饮水（快速）
\`\`\`bash
curl -s -X POST -H "Authorization: Bearer {{API_TOKEN}}" "{{API_URL}}/water/records/quick?amount=250"
\`\`\`
默认250ml，可修改 amount 参数。

### 记录体重
\`\`\`bash
curl -s -X POST -H "Authorization: Bearer {{API_TOKEN}}" -H "Content-Type: application/json" \\
  "{{API_URL}}/weight/records" \\
  -d '{"record_date":"'$(date +%Y-%m-%d)'","weight":72.5}'
\`\`\`

### 记录血压
\`\`\`bash
curl -s -X POST -H "Authorization: Bearer {{API_TOKEN}}" -H "Content-Type: application/json" \\
  "{{API_URL}}/blood-pressure/records" \\
  -d '{"record_date":"'$(date +%Y-%m-%d)'","systolic":120,"diastolic":80,"pulse":72}'
\`\`\`

### 快速打卡
先查询可用模板：
\`\`\`bash
curl -s -H "Authorization: Bearer {{API_TOKEN}}" "{{API_URL}}/checkin/templates"
\`\`\`
然后打卡（用模板ID）：
\`\`\`bash
curl -s -X POST -H "Authorization: Bearer {{API_TOKEN}}" -H "Content-Type: application/json" \\
  "{{API_URL}}/checkin/records/quick" \\
  -d '{"template_id":1,"value":30}'
\`\`\`

### 记录饮食
\`\`\`bash
curl -s -X POST -H "Authorization: Bearer {{API_TOKEN}}" -H "Content-Type: application/json" \\
  "{{API_URL}}/diet/records" \\
  -d '{"record_date":"'$(date +%Y-%m-%d)'","meal_type":"LUNCH","food_items":"鸡胸肉沙拉","calories":400}'
\`\`\`
meal_type: BREAKFAST / LUNCH / DINNER / EXTRA

## Rules
- Confirm the action with the user before recording
- After successful recording, report what was saved
- Parse natural language: "喝了一杯水" → 250ml, "喝了两杯" → 500ml
- Parse weight: "体重72公斤" → 72.0, "72.5kg" → 72.5
- Parse blood pressure: "血压120/80" → systolic=120, diastolic=80
- Always respond in Chinese`,
  },
  {
    id: 'health-analysis',
    name: '健康分析建议',
    description: 'AI 健康分析、趋势预测、风险评估、每日建议',
    icon: '🧠',
    color: 'from-purple-500 to-pink-500',
    toolCount: 6,
    template: `---
name: health-analysis
description: Get AI health analysis, daily recommendations, health trend predictions, and health scores. Use when the user asks for health advice, trend analysis, risk assessment, or wellness recommendations.
version: 1.0.0
metadata:
  openclaw:
    requires:
      env: [HEALTH_API_URL, HEALTH_API_TOKEN]
      bins: [curl]
    primaryEnv: HEALTH_API_TOKEN
    emoji: "🧠"
---

You can request health analysis and recommendations from the Health Management System.

## Authentication
- URL: {{API_URL}}
- Header: \`Authorization: Bearer {{API_TOKEN}}\`

## Available Endpoints

### 健康问题检测
\`\`\`bash
curl -s -H "Authorization: Bearer {{API_TOKEN}}" "{{API_URL}}/analysis/me/issues"
\`\`\`
返回潜在健康问题及严重程度。

### 今日推荐（刷新）
\`\`\`bash
curl -s -X POST -H "Authorization: Bearer {{API_TOKEN}}" "{{API_URL}}/daily-recommendation/me/refresh?use_llm=true"
\`\`\`
AI 生成个性化运动、饮食、作息建议。

### 健康趋势概览
\`\`\`bash
curl -s -H "Authorization: Bearer {{API_TOKEN}}" "{{API_URL}}/health-trends/latest"
\`\`\`
返回各维度（体重、睡眠、运动、综合）趋势方向、洞察和风险提示。

### 指定维度趋势详情
\`\`\`bash
curl -s -H "Authorization: Bearer {{API_TOKEN}}" "{{API_URL}}/health-trends/overall?period=7d"
\`\`\`
支持维度: weight / sleep / exercise / overall，period: 7d / 30d

### 今日健康评分
\`\`\`bash
curl -s -H "Authorization: Bearer {{API_TOKEN}}" "{{API_URL}}/health-score/daily/me"
\`\`\`
返回0-100综合评分及各维度（运动、睡眠、营养、水分、压力）。

### 健康评分趋势
\`\`\`bash
curl -s -H "Authorization: Bearer {{API_TOKEN}}" "{{API_URL}}/health-score/trend/me?days=7"
\`\`\`

## Response Rules
- Present analysis in structured, readable format
- Use severity levels: 🟢 正常, 🟡 注意, 🔴 警告
- Highlight important trends and anomalies
- Provide actionable suggestions
- Always respond in Chinese`,
  },
  {
    id: 'rhinitis-tracker',
    name: '鼻炎追踪',
    description: '记录和查询鼻炎症状（打喷嚏、鼻塞、流涕等），追踪发作历史和环境因素',
    icon: '👃',
    color: 'from-orange-500 to-amber-500',
    toolCount: 8,
    template: `---
name: rhinitis-tracker
description: Track rhinitis symptoms (sneezing, nasal congestion, runny nose), record episodes, query history and environment alerts. Use when the user mentions sneezing, nasal symptoms, rhinitis, or nose-related health issues.
version: 1.0.0
metadata:
  openclaw:
    requires:
      env: [HEALTH_API_URL, HEALTH_API_TOKEN]
      bins: [curl]
    primaryEnv: HEALTH_API_TOKEN
    emoji: "👃"
---

You can track rhinitis symptoms and episodes via the Health Management System API.

## Authentication
- URL: {{API_URL}}
- Header: \\\`Authorization: Bearer {{API_TOKEN}}\\\`
- Content-Type: \\\`application/json\\\`

## 鼻炎症状记录（急性发作）

### 新建发作记录
\\\`\\\`\\\`bash
curl -s -X POST -H "Authorization: Bearer {{API_TOKEN}}" -H "Content-Type: application/json" \\\\
  "{{API_URL}}/illness/episodes" \\\\
  -d '{"illness_name":"打喷嚏","severity":5,"notes":"连续打了好几个喷嚏","start_date":"'$(date +%Y-%m-%d)'"}'
\\\`\\\`\\\`
severity: 1-10 (1=轻微 10=严重)

### 查看当前活跃发作
\\\`\\\`\\\`bash
curl -s -H "Authorization: Bearer {{API_TOKEN}}" "{{API_URL}}/illness/episodes"
\\\`\\\`\\\`

### 查看所有历史发作（含已痊愈）
\\\`\\\`\\\`bash
curl -s -H "Authorization: Bearer {{API_TOKEN}}" "{{API_URL}}/illness/episodes/all"
\\\`\\\`\\\`

### 更新发作状态
\\\`\\\`\\\`bash
curl -s -X PATCH -H "Authorization: Bearer {{API_TOKEN}}" -H "Content-Type: application/json" \\\\
  "{{API_URL}}/illness/episodes/{episode_id}" \\\\
  -d '{"status":"improving","severity":3}'
\\\`\\\`\\\`
status: active / improving / resolved

### 添加每日进展
\\\`\\\`\\\`bash
curl -s -X POST -H "Authorization: Bearer {{API_TOKEN}}" -H "Content-Type: application/json" \\\\
  "{{API_URL}}/illness/episodes/{episode_id}/updates" \\\\
  -d '{"severity":4,"notes":"今天喷嚏减少，但仍有鼻塞","medications":"氯雷他定"}'
\\\`\\\`\\\`

## 慢性鼻炎档案管理

### 记录鼻炎症状（慢性追踪）
先查询用户鼻炎档案ID：
\\\`\\\`\\\`bash
curl -s -H "Authorization: Bearer {{API_TOKEN}}" "{{API_URL}}/disease/profiles"
\\\`\\\`\\\`
然后记录症状：
\\\`\\\`\\\`bash
curl -s -X POST -H "Authorization: Bearer {{API_TOKEN}}" -H "Content-Type: application/json" \\\\
  "{{API_URL}}/disease/profiles/{profile_id}/symptoms" \\\\
  -d '{"symptoms":[{"name":"打喷嚏","severity":6},{"name":"鼻塞","severity":4},{"name":"流涕","severity":5}],"triggers":["冷空气","尘螨"],"medications":[{"name":"氯雷他定","dosage":"10mg"}],"notes":"早起症状明显"}'
\\\`\\\`\\\`

### 查看症状统计
\\\`\\\`\\\`bash
curl -s -H "Authorization: Bearer {{API_TOKEN}}" "{{API_URL}}/disease/profiles/{profile_id}/stats?days=30"
\\\`\\\`\\\`

## Rules
- 当用户说"打喷嚏"、"鼻塞"、"流鼻涕"时，用 illness/episodes 记录急性发作
- severity 解析："轻微"→2, "有点"→3, "比较严重"→6, "很严重"→8
- 常见 illness_name: "打喷嚏", "鼻塞", "流涕", "鼻炎发作"
- 常见 triggers: "冷空气", "尘螨", "花粉", "油烟", "香水"
- 记录后告知用户已记录，并提醒洗鼻等缓解措施
- Always respond in Chinese`,
  },
];

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

// 将 OpenClaw 格式模板转为 Claude Code 格式
function toClaudeCodeTemplate(skill: SkillDef): string {
  // 移除 OpenClaw frontmatter，替换为 Claude Code frontmatter
  const body = skill.template.replace(/^---[\s\S]*?---\n*/m, '');
  const frontmatter = `---
name: ${skill.id}
description: ${skill.description}
allowed-tools: Bash(curl *)
---`;
  return `${frontmatter}\n\n${body}`;
}

function getSkillPath(skillId: string, format: SkillFormat): string {
  return format === 'openclaw'
    ? `~/.openclaw/skills/${skillId}/SKILL.md`
    : `~/.claude/skills/${skillId}/SKILL.md`;
}

function SkillCard({
  skill,
  token,
  isExpanded,
  onToggle,
  format,
  installed,
  isAdmin,
  onInstall,
  onUninstall,
  onToggleEnabled,
  installing,
}: {
  skill: SkillDef;
  token: string;
  isExpanded: boolean;
  onToggle: () => void;
  format: SkillFormat;
  installed: InstalledSkill | null;
  isAdmin: boolean;
  onInstall: () => void;
  onUninstall: () => void;
  onToggleEnabled: (enabled: boolean) => void;
  installing: boolean;
}) {
  const [copied, setCopied] = useState(false);

  const raw = format === 'openclaw' ? skill.template : toClaudeCodeTemplate(skill);
  const content = raw
    .replace(/\{\{API_URL\}\}/g, API_URL)
    .replace(/\{\{API_TOKEN\}\}/g, token || '<请先创建 API Key>');

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    copyToClipboard(content);
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

  return (
    <div className="bg-[#1e1a2e] rounded-xl border border-purple-900/30 overflow-hidden">
      <div
        className="flex items-center justify-between p-5 cursor-pointer hover:bg-white/[0.02] transition-colors"
        onClick={onToggle}
      >
        <div className="flex items-center gap-4">
          <div className={`w-12 h-12 rounded-xl bg-gradient-to-br ${skill.color} flex items-center justify-center text-2xl shadow-lg`}>
            {skill.icon}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-lg font-semibold text-white">{skill.name}</h3>
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
          <span className="text-xs font-medium text-gray-500 bg-white/5 px-2.5 py-1 rounded-full">
            {skill.toolCount} 个工具
          </span>
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
            <span className="text-xs font-mono text-gray-500">{getSkillPath(skill.id, format)}</span>
            <button onClick={handleCopy} className={`text-xs px-3 py-1.5 rounded-md transition-all ${copied ? 'bg-green-600/20 text-green-400' : 'bg-white/5 text-gray-400 hover:bg-white/10 hover:text-white'}`}>
              {copied ? '已复制 ✓' : '复制全部内容'}
            </button>
          </div>
          {token ? (
            <div className="mb-3 flex items-center gap-2 text-xs text-green-400">
              <span>✓</span>
              <span>已绑定 API Key，复制即可直接使用</span>
            </div>
          ) : (
            <div className="mb-3 flex items-center gap-2 text-xs text-amber-400">
              <span>⚠</span>
              <span>请先在上方创建 API Key，内容中会自动填充你的 Token</span>
            </div>
          )}
          <pre className="bg-[#0d0b14] rounded-lg p-4 overflow-x-auto text-sm text-gray-300 font-mono leading-relaxed border border-purple-900/20 max-h-[500px] overflow-y-auto whitespace-pre-wrap">
            {content}
          </pre>
        </div>
      )}
    </div>
  );
}

type SkillFormat = 'openclaw' | 'claude-code';

export default function SkillsPage() {
  const { user } = useAuth();
  const isAdmin = user?.is_admin ?? false;

  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [apiKeys, setApiKeys] = useState<ApiKey[]>([]);
  const [activeToken, setActiveToken] = useState('');
  const [newKeyName, setNewKeyName] = useState('');
  const [creating, setCreating] = useState(false);
  const [newlyCreatedKey, setNewlyCreatedKey] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [configCopied, setConfigCopied] = useState(false);
  const [skillFormat, setSkillFormat] = useState<SkillFormat>('openclaw');

  // OpenClaw 远程管理 state
  const [installedSkills, setInstalledSkills] = useState<InstalledSkill[]>([]);
  const [gatewayStatus, setGatewayStatus] = useState<{ status: string; uptime: string } | null>(null);
  const [installing, setInstalling] = useState<Record<string, boolean>>({});
  const [needRestart, setNeedRestart] = useState(false);
  const [restarting, setRestarting] = useState(false);
  const [loadingRemote, setLoadingRemote] = useState(false);

  const loadApiKeys = useCallback(async () => {
    try {
      const res = await api.get('/v1/user-api-keys');
      setApiKeys(res.data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

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
      // non-admin or server unreachable — silently ignore
    } finally {
      setLoadingRemote(false);
    }
  }, [isAdmin]);

  useEffect(() => {
    loadApiKeys();
  }, [loadApiKeys]);

  useEffect(() => {
    loadRemoteStatus();
  }, [loadRemoteStatus]);

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
  const handleInstallSkill = async (skill: SkillDef) => {
    if (!activeToken) {
      alert('请先创建 API Key');
      return;
    }
    setInstalling((prev) => ({ ...prev, [skill.id]: true }));
    try {
      const skillContent = skill.template
        .replace(/\{\{API_URL\}\}/g, API_URL)
        .replace(/\{\{API_TOKEN\}\}/g, activeToken);
      await openclawSkillsApi.install(
        skill.id,
        skillContent,
        true,
        { HEALTH_API_URL: API_URL, HEALTH_API_TOKEN: activeToken },
        activeToken,
      );
      setNeedRestart(true);
      await loadRemoteStatus();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '安装失败';
      alert(`安装失败: ${msg}`);
    } finally {
      setInstalling((prev) => ({ ...prev, [skill.id]: false }));
    }
  };

  // 卸载 Skill
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

  // 启用/禁用
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

  // 重启 Gateway
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

  const getOpenclawConfig = useCallback(() => {
    const tok = activeToken || '<你的API Key>';
    return JSON.stringify({
      skills: {
        entries: {
          'health-query': {
            enabled: true,
            apiKey: tok,
            env: { HEALTH_API_URL: API_URL, HEALTH_API_TOKEN: tok },
          },
          'health-record': {
            enabled: true,
            apiKey: tok,
            env: { HEALTH_API_URL: API_URL, HEALTH_API_TOKEN: tok },
          },
          'health-analysis': {
            enabled: true,
            apiKey: tok,
            env: { HEALTH_API_URL: API_URL, HEALTH_API_TOKEN: tok },
          },
        },
      },
    }, null, 2);
  }, [activeToken]);

  const handleCopyConfig = () => {
    copyToClipboard(getOpenclawConfig());
    setConfigCopied(true);
    setTimeout(() => setConfigCopied(false), 2000);
  };

  // 查找已安装信息
  const getInstalledInfo = (skillId: string): InstalledSkill | null => {
    return installedSkills.find((s) => s.name === skillId) || null;
  };

  return (
    <ProtectedRoute>
      <div className="min-h-screen bg-[#13111a] text-white">
        <div className="max-w-4xl mx-auto px-4 py-8">
          {/* Header */}
          <div className="mb-8">
            <h1 className="text-2xl font-bold text-white mb-2">AI Skills 管理</h1>
            <p className="text-gray-400">
              管理 API Key，{isAdmin ? '一键安装 Skills 到 OpenClaw 服务器，或' : ''}复制 SKILL.md 到 {skillFormat === 'openclaw' ? 'OpenClaw' : 'Claude Code'} 即可用自然语言管理健康数据
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
                  OpenClaw 原始格式
                </button>
                <button
                  onClick={() => setSkillFormat('claude-code')}
                  className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                    skillFormat === 'claude-code'
                      ? 'bg-purple-600 text-white shadow-sm'
                      : 'text-gray-400 hover:text-white'
                  }`}
                >
                  Claude Code 格式
                </button>
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
              {isAdmin && skillFormat === 'openclaw' ? (
                <>
                  <div className="flex items-start gap-3">
                    <span className="w-6 h-6 rounded-full bg-purple-600/30 text-purple-300 flex items-center justify-center text-xs font-bold flex-shrink-0">1</span>
                    <div>
                      <p className="text-white font-medium">创建 API Key</p>
                      <p className="text-gray-400 mt-0.5">下方创建后自动绑定到 Skills</p>
                    </div>
                  </div>
                  <div className="flex items-start gap-3">
                    <span className="w-6 h-6 rounded-full bg-purple-600/30 text-purple-300 flex items-center justify-center text-xs font-bold flex-shrink-0">2</span>
                    <div>
                      <p className="text-white font-medium">一键安装</p>
                      <p className="text-gray-400 mt-0.5">点击"安装到 OpenClaw"自动部署</p>
                    </div>
                  </div>
                  <div className="flex items-start gap-3">
                    <span className="w-6 h-6 rounded-full bg-purple-600/30 text-purple-300 flex items-center justify-center text-xs font-bold flex-shrink-0">3</span>
                    <div>
                      <p className="text-white font-medium">重启 Gateway</p>
                      <p className="text-gray-400 mt-0.5">安装后需重启使配置生效</p>
                    </div>
                  </div>
                </>
              ) : (
                <>
                  <div className="flex items-start gap-3">
                    <span className="w-6 h-6 rounded-full bg-purple-600/30 text-purple-300 flex items-center justify-center text-xs font-bold flex-shrink-0">1</span>
                    <div>
                      <p className="text-white font-medium">创建 API Key</p>
                      <p className="text-gray-400 mt-0.5">下方创建后自动绑定到 Skills</p>
                    </div>
                  </div>
                  <div className="flex items-start gap-3">
                    <span className="w-6 h-6 rounded-full bg-purple-600/30 text-purple-300 flex items-center justify-center text-xs font-bold flex-shrink-0">2</span>
                    <div>
                      <p className="text-white font-medium">复制 SKILL.md</p>
                      <p className="text-gray-400 mt-0.5">内容已包含你的 API 地址和 Token</p>
                    </div>
                  </div>
                  <div className="flex items-start gap-3">
                    <span className="w-6 h-6 rounded-full bg-purple-600/30 text-purple-300 flex items-center justify-center text-xs font-bold flex-shrink-0">3</span>
                    <div>
                      <p className="text-white font-medium">保存到 {skillFormat === 'openclaw' ? 'OpenClaw' : 'Claude Code'}</p>
                      <p className="text-gray-400 mt-0.5">
                        保存至 <code className="text-purple-300 bg-purple-900/30 px-1 rounded">
                          {skillFormat === 'openclaw' ? '~/.openclaw/skills/' : '~/.claude/skills/'}
                        </code>
                      </p>
                    </div>
                  </div>
                </>
              )}
            </div>
          </div>

          {/* API Key 管理 */}
          <div className="bg-[#1e1a2e] rounded-xl border border-purple-900/30 p-5 mb-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-base font-semibold text-white flex items-center gap-2">
                🔑 API Key 管理
              </h2>
              <div className="flex items-center gap-2 text-xs text-gray-500">
                <span className="inline-block w-2 h-2 rounded-full bg-green-500"></span>
                API: {API_URL}
              </div>
            </div>

            {/* 创建新 Key */}
            <div className="flex gap-2 mb-4">
              <input
                type="text"
                value={newKeyName}
                onChange={(e) => setNewKeyName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleCreateKey()}
                placeholder={`输入名称（如：${skillFormat === 'openclaw' ? 'OpenClaw' : 'Claude Code'}、MCP Server）`}
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
                    <p className="text-sm text-green-300 font-medium mb-1">API Key 创建成功！请立即保存，此密钥仅显示一次</p>
                    <div className="flex items-center gap-2">
                      <code className="text-xs bg-black/30 px-2 py-1 rounded text-green-200 font-mono break-all">{newlyCreatedKey}</code>
                      <button
                        onClick={() => {
                          copyToClipboard(newlyCreatedKey);
                        }}
                        className="text-xs px-2 py-1 bg-green-600/30 text-green-300 rounded hover:bg-green-600/40 transition-all whitespace-nowrap"
                      >
                        复制
                      </button>
                    </div>
                    <p className="text-xs text-green-400/60 mt-1">已自动选为当前 Token，下方 Skills 内容已绑定此 Key</p>
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
                暂无 API Key，请创建一个用于 {skillFormat === 'openclaw' ? 'OpenClaw' : 'Claude Code'} Skills
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
                          {k.scopes} · 创建于 {new Date(k.created_at).toLocaleDateString('zh-CN')}
                        </span>
                        {k.last_used_at && (
                          <span className="text-xs text-gray-600 ml-2">
                            最后使用 {new Date(k.last_used_at).toLocaleDateString('zh-CN')}
                          </span>
                        )}
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

          {/* Skill Cards */}
          <div className="space-y-4">
            {skillDefs.map((skill) => (
              <SkillCard
                key={skill.id}
                skill={skill}
                token={activeToken}
                isExpanded={expandedId === skill.id}
                onToggle={() => setExpandedId(expandedId === skill.id ? null : skill.id)}
                format={skillFormat}
                installed={getInstalledInfo(skill.id)}
                isAdmin={isAdmin}
                onInstall={() => handleInstallSkill(skill)}
                onUninstall={() => handleUninstallSkill(skill.id)}
                onToggleEnabled={(enabled) => handleToggleSkill(skill.id, enabled)}
                installing={installing[skill.id] || false}
              />
            ))}
          </div>

          {/* 安全说明 */}
          <div className="mt-8 bg-[#1e1a2e] rounded-xl border border-amber-500/30 p-5">
            <div className="flex items-start gap-3">
              <span className="text-xl">🔐</span>
              <div>
                <h2 className="text-sm font-semibold text-amber-300 mb-2">数据安全说明</h2>
                <ul className="text-sm text-gray-300 space-y-1.5">
                  <li>每个用户使用<strong className="text-white">自己的 API Key</strong>，Key 与账号绑定，仅能访问本人数据</li>
                  <li>API Key 创建后<strong className="text-white">仅显示一次</strong>，请立即保存</li>
                  <li>请勿将 Key 分享给他人或提交到公开代码仓库</li>
                  <li>如 Key 泄露，请在上方删除旧 Key 并重新创建</li>
                </ul>
              </div>
            </div>
          </div>

          {/* 配置说明 */}
          {skillFormat === 'openclaw' ? (
            <div className="mt-4 bg-[#1e1a2e] rounded-xl border border-purple-900/30 p-5">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-sm font-semibold text-purple-300">openclaw.json 配置（已绑定你的 Token）</h2>
                <button
                  onClick={handleCopyConfig}
                  className={`text-xs px-3 py-1.5 rounded-md transition-all ${
                    configCopied ? 'bg-green-600/20 text-green-400' : 'bg-white/5 text-gray-400 hover:bg-white/10 hover:text-white'
                  }`}
                >
                  {configCopied ? '已复制 ✓' : '复制配置'}
                </button>
              </div>
              <p className="text-xs text-gray-400 mb-3">
                合并到 <code className="text-purple-300 bg-purple-900/30 px-1 rounded">~/.openclaw/openclaw.json</code> 的 skills.entries 中，注入环境变量
              </p>
              <pre className="bg-[#0d0b14] rounded-lg p-4 overflow-x-auto text-sm text-gray-300 font-mono leading-relaxed border border-purple-900/20 max-h-[300px] overflow-y-auto whitespace-pre-wrap">
                {getOpenclawConfig()}
              </pre>
            </div>
          ) : (
            <div className="mt-4 bg-[#1e1a2e] rounded-xl border border-purple-900/30 p-5">
              <h2 className="text-sm font-semibold text-purple-300 mb-3">Claude Code 安装说明</h2>
              <div className="space-y-3 text-sm text-gray-300">
                <p>将上方每个 Skill 的 SKILL.md 文件保存到对应目录：</p>
                <pre className="bg-[#0d0b14] rounded-lg p-4 text-xs font-mono leading-relaxed border border-purple-900/20 whitespace-pre-wrap">{`mkdir -p ~/.claude/skills/health-query
mkdir -p ~/.claude/skills/health-record
mkdir -p ~/.claude/skills/health-analysis

# 分别将复制的内容保存到各目录的 SKILL.md`}</pre>
                <p className="text-xs text-gray-400">
                  Claude Code 会自动发现 <code className="text-purple-300 bg-purple-900/30 px-1 rounded">~/.claude/skills/</code> 下的 SKILL.md 文件并加载为可用 Skill
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </ProtectedRoute>
  );
}
