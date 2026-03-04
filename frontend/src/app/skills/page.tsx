'use client';

import { useState } from 'react';
import ProtectedRoute from '@/components/ProtectedRoute';

interface SkillData {
  id: string;
  name: string;
  description: string;
  icon: string;
  color: string;
  toolCount: number;
  content: string;
}

const skills: SkillData[] = [
  {
    id: 'health-query',
    name: '健康数据查询',
    description: '查询步数、心率、睡眠、体重、血压、运动、饮食、打卡等健康数据',
    icon: '🔍',
    color: 'from-blue-500 to-cyan-500',
    toolCount: 13,
    content: `---
name: health-query
description: Query health data from the Health Management System - steps, heart rate, sleep, weight, blood pressure, workouts, diet, checkin status, and achievements.
requires:
  env:
    - HEALTH_API_URL
    - HEALTH_API_TOKEN
---

You have access to a Health Management System API. Use curl to query health data.

## Authentication
- URL: \${HEALTH_API_URL}
- Header: \`Authorization: Bearer \${HEALTH_API_TOKEN}\`

## Available Endpoints

### 综合健康数据（Garmin）
\`\`\`bash
curl -s -H "Authorization: Bearer \${HEALTH_API_TOKEN}" "\${HEALTH_API_URL}/garmin-analysis/me/comprehensive?days=7"
\`\`\`
返回：步数、心率、睡眠、压力、Body Battery 综合分析

### 睡眠数据
\`\`\`bash
curl -s -H "Authorization: Bearer \${HEALTH_API_TOKEN}" "\${HEALTH_API_URL}/garmin-analysis/me/sleep?days=7"
\`\`\`

### 心率数据
\`\`\`bash
curl -s -H "Authorization: Bearer \${HEALTH_API_TOKEN}" "\${HEALTH_API_URL}/garmin-analysis/me/heart-rate?days=7"
\`\`\`

### 活动数据
\`\`\`bash
curl -s -H "Authorization: Bearer \${HEALTH_API_TOKEN}" "\${HEALTH_API_URL}/garmin-analysis/me/activity?days=7"
\`\`\`

### 体重记录
\`\`\`bash
curl -s -H "Authorization: Bearer \${HEALTH_API_TOKEN}" "\${HEALTH_API_URL}/weight/records/me?limit=7"
\`\`\`

### 血压记录
\`\`\`bash
curl -s -H "Authorization: Bearer \${HEALTH_API_TOKEN}" "\${HEALTH_API_URL}/blood-pressure/records/me?limit=7"
\`\`\`

### 今日饮水
\`\`\`bash
curl -s -H "Authorization: Bearer \${HEALTH_API_TOKEN}" "\${HEALTH_API_URL}/water/records/me/date/$(date +%Y-%m-%d)"
\`\`\`

### 饮水统计
\`\`\`bash
curl -s -H "Authorization: Bearer \${HEALTH_API_TOKEN}" "\${HEALTH_API_URL}/water/records/me/stats?days=7"
\`\`\`

### 今日打卡
\`\`\`bash
curl -s -H "Authorization: Bearer \${HEALTH_API_TOKEN}" "\${HEALTH_API_URL}/checkin/records/today"
\`\`\`

### 打卡统计
\`\`\`bash
curl -s -H "Authorization: Bearer \${HEALTH_API_TOKEN}" "\${HEALTH_API_URL}/checkin/stats"
\`\`\`

### 运动记录
\`\`\`bash
curl -s -H "Authorization: Bearer \${HEALTH_API_TOKEN}" "\${HEALTH_API_URL}/workout/me?days=7"
\`\`\`

### 成就徽章
\`\`\`bash
curl -s -H "Authorization: Bearer \${HEALTH_API_TOKEN}" "\${HEALTH_API_URL}/achievements/me"
\`\`\`

### 健康评分
\`\`\`bash
curl -s -H "Authorization: Bearer \${HEALTH_API_TOKEN}" "\${HEALTH_API_URL}/health-score/daily/me"
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
    content: `---
name: health-record
description: Record health data - water intake, weight, blood pressure, checkins, and diet entries.
requires:
  env:
    - HEALTH_API_URL
    - HEALTH_API_TOKEN
---

You can record health data via the Health Management System API.

## Authentication
- URL: \${HEALTH_API_URL}
- Header: \`Authorization: Bearer \${HEALTH_API_TOKEN}\`
- Content-Type: \`application/json\`

## Available Actions

### 记录饮水（快速）
\`\`\`bash
curl -s -X POST -H "Authorization: Bearer \${HEALTH_API_TOKEN}" "\${HEALTH_API_URL}/water/records/quick?amount=250"
\`\`\`
默认250ml，可修改 amount 参数。

### 记录体重
\`\`\`bash
curl -s -X POST -H "Authorization: Bearer \${HEALTH_API_TOKEN}" -H "Content-Type: application/json" \\
  "\${HEALTH_API_URL}/weight/records" \\
  -d '{"record_date":"'$(date +%Y-%m-%d)'","weight":72.5}'
\`\`\`

### 记录血压
\`\`\`bash
curl -s -X POST -H "Authorization: Bearer \${HEALTH_API_TOKEN}" -H "Content-Type: application/json" \\
  "\${HEALTH_API_URL}/blood-pressure/records" \\
  -d '{"record_date":"'$(date +%Y-%m-%d)'","systolic":120,"diastolic":80,"pulse":72}'
\`\`\`

### 快速打卡
先查询可用模板：
\`\`\`bash
curl -s -H "Authorization: Bearer \${HEALTH_API_TOKEN}" "\${HEALTH_API_URL}/checkin/templates"
\`\`\`
然后打卡（用模板ID）：
\`\`\`bash
curl -s -X POST -H "Authorization: Bearer \${HEALTH_API_TOKEN}" -H "Content-Type: application/json" \\
  "\${HEALTH_API_URL}/checkin/records/quick" \\
  -d '{"template_id":1,"value":30}'
\`\`\`

### 记录饮食
\`\`\`bash
curl -s -X POST -H "Authorization: Bearer \${HEALTH_API_TOKEN}" -H "Content-Type: application/json" \\
  "\${HEALTH_API_URL}/diet/records" \\
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
    content: `---
name: health-analysis
description: Get AI health analysis, daily recommendations, health trend predictions, and health scores.
requires:
  env:
    - HEALTH_API_URL
    - HEALTH_API_TOKEN
---

You can request health analysis and recommendations from the Health Management System.

## Authentication
- URL: \${HEALTH_API_URL}
- Header: \`Authorization: Bearer \${HEALTH_API_TOKEN}\`

## Available Endpoints

### 健康问题检测
\`\`\`bash
curl -s -H "Authorization: Bearer \${HEALTH_API_TOKEN}" "\${HEALTH_API_URL}/analysis/me/issues"
\`\`\`
返回潜在健康问题及严重程度。

### 今日推荐（刷新）
\`\`\`bash
curl -s -X POST -H "Authorization: Bearer \${HEALTH_API_TOKEN}" "\${HEALTH_API_URL}/daily-recommendation/me/refresh?use_llm=true"
\`\`\`
AI 生成个性化运动、饮食、作息建议。

### 健康趋势预测
\`\`\`bash
curl -s -H "Authorization: Bearer \${HEALTH_API_TOKEN}" "\${HEALTH_API_URL}/health-trend/me/prediction?days=30"
\`\`\`
预测未来7天的睡眠、心率、压力等趋势。

### 健康风险因素
\`\`\`bash
curl -s -H "Authorization: Bearer \${HEALTH_API_TOKEN}" "\${HEALTH_API_URL}/health-trend/me/risk-factors"
\`\`\`

### 今日健康评分
\`\`\`bash
curl -s -H "Authorization: Bearer \${HEALTH_API_TOKEN}" "\${HEALTH_API_URL}/health-score/daily/me"
\`\`\`
返回0-100综合评分及各维度（运动、睡眠、营养、水分、压力）。

### 健康评分趋势
\`\`\`bash
curl -s -H "Authorization: Bearer \${HEALTH_API_TOKEN}" "\${HEALTH_API_URL}/health-score/trend/me?days=7"
\`\`\`

## Response Rules
- Present analysis in structured, readable format
- Use severity levels: 🟢 正常, 🟡 注意, 🔴 警告
- Highlight important trends and anomalies
- Provide actionable suggestions
- Always respond in Chinese`,
  },
];

function SkillCard({
  skill,
  isExpanded,
  onToggle,
}: {
  skill: SkillData;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(skill.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // fallback
      const textarea = document.createElement('textarea');
      textarea.value = skill.content;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="bg-[#1e1a2e] rounded-xl border border-purple-900/30 overflow-hidden">
      {/* Header */}
      <div
        className="flex items-center justify-between p-5 cursor-pointer hover:bg-white/[0.02] transition-colors"
        onClick={onToggle}
      >
        <div className="flex items-center gap-4">
          <div
            className={`w-12 h-12 rounded-xl bg-gradient-to-br ${skill.color} flex items-center justify-center text-2xl shadow-lg`}
          >
            {skill.icon}
          </div>
          <div>
            <h3 className="text-lg font-semibold text-white">{skill.name}</h3>
            <p className="text-sm text-gray-400 mt-0.5">{skill.description}</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs font-medium text-gray-500 bg-white/5 px-2.5 py-1 rounded-full">
            {skill.toolCount} 个工具
          </span>
          <button
            onClick={handleCopy}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
              copied
                ? 'bg-green-600/20 text-green-400 border border-green-500/30'
                : 'bg-purple-600/20 text-purple-300 border border-purple-500/30 hover:bg-purple-600/30'
            }`}
          >
            {copied ? '已复制 ✓' : '复制 SKILL.md'}
          </button>
          <svg
            className={`w-5 h-5 text-gray-400 transition-transform duration-200 ${isExpanded ? 'rotate-180' : ''}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </div>

      {/* Content */}
      {isExpanded && (
        <div className="border-t border-purple-900/30">
          <div className="p-5">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-mono text-gray-500">
                openclaw-skills/{skill.id}/SKILL.md
              </span>
              <button
                onClick={handleCopy}
                className={`text-xs px-3 py-1.5 rounded-md transition-all ${
                  copied
                    ? 'bg-green-600/20 text-green-400'
                    : 'bg-white/5 text-gray-400 hover:bg-white/10 hover:text-white'
                }`}
              >
                {copied ? '已复制 ✓' : '复制全部内容'}
              </button>
            </div>
            <pre className="bg-[#0d0b14] rounded-lg p-4 overflow-x-auto text-sm text-gray-300 font-mono leading-relaxed border border-purple-900/20 max-h-[500px] overflow-y-auto">
              {skill.content}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}

export default function SkillsPage() {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [allCopied, setAllCopied] = useState(false);

  const handleCopyAll = async () => {
    const allContent = skills
      .map((s) => `# ===== ${s.id}/SKILL.md =====\n\n${s.content}`)
      .join('\n\n\n');
    try {
      await navigator.clipboard.writeText(allContent);
      setAllCopied(true);
      setTimeout(() => setAllCopied(false), 2000);
    } catch {
      const textarea = document.createElement('textarea');
      textarea.value = allContent;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setAllCopied(true);
      setTimeout(() => setAllCopied(false), 2000);
    }
  };

  return (
    <ProtectedRoute>
      <div className="min-h-screen bg-[#13111a] text-white">
        <div className="max-w-4xl mx-auto px-4 py-8">
          {/* Header */}
          <div className="mb-8">
            <h1 className="text-2xl font-bold text-white mb-2">OpenClaw Skills</h1>
            <p className="text-gray-400">
              复制 SKILL.md 内容到 OpenClaw，即可在 Telegram、Discord、微信等渠道管理健康数据
            </p>
          </div>

          {/* 使用说明 */}
          <div className="bg-[#1e1a2e] rounded-xl border border-purple-900/30 p-5 mb-6">
            <h2 className="text-sm font-semibold text-purple-300 mb-3">使用方法</h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
              <div className="flex items-start gap-3">
                <span className="w-6 h-6 rounded-full bg-purple-600/30 text-purple-300 flex items-center justify-center text-xs font-bold flex-shrink-0">
                  1
                </span>
                <div>
                  <p className="text-white font-medium">复制 SKILL.md</p>
                  <p className="text-gray-400 mt-0.5">点击下方卡片的"复制"按钮</p>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <span className="w-6 h-6 rounded-full bg-purple-600/30 text-purple-300 flex items-center justify-center text-xs font-bold flex-shrink-0">
                  2
                </span>
                <div>
                  <p className="text-white font-medium">保存到 OpenClaw</p>
                  <p className="text-gray-400 mt-0.5">
                    粘贴到 <code className="text-purple-300 bg-purple-900/30 px-1 rounded">~/.openclaw/skills/</code> 目录
                  </p>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <span className="w-6 h-6 rounded-full bg-purple-600/30 text-purple-300 flex items-center justify-center text-xs font-bold flex-shrink-0">
                  3
                </span>
                <div>
                  <p className="text-white font-medium">配置环境变量</p>
                  <p className="text-gray-400 mt-0.5">
                    在 <code className="text-purple-300 bg-purple-900/30 px-1 rounded">openclaw.json</code> 中设置 API URL 和 Token
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* 一键复制全部 */}
          <div className="flex justify-end mb-4">
            <button
              onClick={handleCopyAll}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                allCopied
                  ? 'bg-green-600/20 text-green-400 border border-green-500/30'
                  : 'bg-white/5 text-gray-300 border border-purple-900/30 hover:bg-white/10'
              }`}
            >
              {allCopied ? '全部已复制 ✓' : '一键复制全部 Skills'}
            </button>
          </div>

          {/* Skill Cards */}
          <div className="space-y-4">
            {skills.map((skill) => (
              <SkillCard
                key={skill.id}
                skill={skill}
                isExpanded={expandedId === skill.id}
                onToggle={() => setExpandedId(expandedId === skill.id ? null : skill.id)}
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
                  <li>每个用户需使用<strong className="text-white">自己的 API Token</strong>，Token 与账号绑定，仅能访问本人数据</li>
                  <li>Token 可在 <a href="/settings" className="text-purple-400 hover:text-purple-300 underline">个人设置</a> 页面获取或在 API Keys 管理中生成长期 Token</li>
                  <li>请勿将 Token 分享给他人或提交到公开代码仓库</li>
                  <li>如 Token 泄露，请立即在设置中重新生成</li>
                </ul>
              </div>
            </div>
          </div>

          {/* 配置示例 */}
          <div className="mt-4 bg-[#1e1a2e] rounded-xl border border-purple-900/30 p-5">
            <h2 className="text-sm font-semibold text-purple-300 mb-3">openclaw.json 配置示例</h2>
            <pre className="bg-[#0d0b14] rounded-lg p-4 overflow-x-auto text-sm text-gray-300 font-mono leading-relaxed border border-purple-900/20">
{`{
  "skills": {
    "entries": {
      "health-query": {
        "env": {
          "HEALTH_API_URL": "https://health-api.executor.life/api/v1",
          "HEALTH_API_TOKEN": "你的个人JWT Token（每人不同）"
        }
      },
      "health-record": {
        "env": {
          "HEALTH_API_URL": "https://health-api.executor.life/api/v1",
          "HEALTH_API_TOKEN": "你的个人JWT Token（每人不同）"
        }
      },
      "health-analysis": {
        "env": {
          "HEALTH_API_URL": "https://health-api.executor.life/api/v1",
          "HEALTH_API_TOKEN": "你的个人JWT Token（每人不同）"
        }
      }
    }
  }
}`}
            </pre>
          </div>
        </div>
      </div>
    </ProtectedRoute>
  );
}
