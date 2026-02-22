'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';

export default function ArchitecturePage() {
  const router = useRouter();
  const { user, isAuthenticated, isLoading } = useAuth();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push('/login');
    } else if (!isLoading && isAuthenticated && !user?.is_admin) {
      router.push('/');
    }
  }, [isLoading, isAuthenticated, user, router]);

  if (isLoading || !isAuthenticated || !user?.is_admin) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-400 mx-auto"></div>
      </div>
    );
  }

  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 pt-4 pb-24">
      <div className="max-w-5xl mx-auto px-4 md:px-8">
        {/* Header */}
        <div className="flex items-center gap-3 mb-8">
          <button
            onClick={() => router.push('/admin')}
            className="text-purple-300 hover:text-white transition-colors"
          >
            &larr; 返回管理后台
          </button>
        </div>

        <div className="bg-white/10 backdrop-blur-lg rounded-2xl border border-white/20 p-6 md:p-10">
          <h1 className="text-3xl font-bold text-white mb-2">系统技术架构文档</h1>
          <p className="text-purple-300 text-sm mb-10">最后更新: 2026-02-22</p>

          <div className="prose prose-invert prose-purple max-w-none space-y-10 text-[15px] leading-relaxed">

            {/* 1. 系统概述 */}
            <Section title="1. 系统概述">
              <p>
                「自由是自律的泡沫」是一个 AI 驱动的全方位健康管理平台，通过自然语言对话实现健康数据的智能记录与分析。
                系统核心理念是<Hl>对话即记录</Hl>——用户通过与 AI 健康顾问聊天（如"我在学习"、"刚喝了一杯咖啡"），
                系统自动解析意图并写入结构化数据库，免去手动填表。
              </p>
              <p>平台覆盖 50+ 健康维度，包括运动、饮食、睡眠、饮水、用药、情绪、女性健康、鼻炎追踪、病症管理等，
                支持 Garmin 手表自动同步、Apple 快捷指令语音录入、微信小程序等多端接入。</p>
            </Section>

            {/* 2. 技术栈 */}
            <Section title="2. 技术栈总览">
              <div className="grid md:grid-cols-2 gap-6">
                <Card title="后端">
                  <ul className="space-y-1">
                    <li><Tag>FastAPI 0.115</Tag> — 异步 Python Web 框架</li>
                    <li><Tag>SQLAlchemy 2.0</Tag> — ORM + PostgreSQL</li>
                    <li><Tag>Pydantic 2.5</Tag> — 数据校验与序列化</li>
                    <li><Tag>OpenAI SDK 1.3</Tag> — LLM 调用客户端</li>
                    <li><Tag>Celery + Redis</Tag> — 异步任务队列</li>
                    <li><Tag>ChromaDB</Tag> — 向量数据库 (知识库 RAG)</li>
                    <li><Tag>Alembic</Tag> — 数据库迁移</li>
                  </ul>
                </Card>
                <Card title="前端">
                  <ul className="space-y-1">
                    <li><Tag>Next.js 14</Tag> — React 全栈框架</li>
                    <li><Tag>React 18</Tag> — UI 渲染</li>
                    <li><Tag>TypeScript 5.3</Tag> — 类型安全</li>
                    <li><Tag>TanStack React Query 5</Tag> — 服务端状态管理</li>
                    <li><Tag>Tailwind CSS 3.3</Tag> — 样式框架</li>
                    <li><Tag>Recharts 2.10</Tag> — 图表可视化</li>
                    <li><Tag>Capacitor 8</Tag> — iOS 原生封装</li>
                  </ul>
                </Card>
                <Card title="基础设施">
                  <ul className="space-y-1">
                    <li><Tag>阿里云 ECS</Tag> — 39.98.206.178</li>
                    <li><Tag>PostgreSQL</Tag> — 生产数据库</li>
                    <li><Tag>Redis</Tag> — 缓存 + 任务队列</li>
                    <li><Tag>PM2</Tag> — 前端进程管理</li>
                    <li><Tag>systemd</Tag> — 后端服务管理</li>
                    <li><Tag>Nginx</Tag> — 反向代理 + SSL</li>
                  </ul>
                </Card>
                <Card title="第三方服务">
                  <ul className="space-y-1">
                    <li><Tag>OpenClaw</Tag> — 自建 LLM (bot.executor.life)</li>
                    <li><Tag>Garmin Connect</Tag> — 运动数据同步</li>
                    <li><Tag>和风天气</Tag> — 天气与空气质量</li>
                    <li><Tag>阿里云 Quark</Tag> — 联网搜索</li>
                    <li><Tag>APNs</Tag> — iOS 推送通知</li>
                  </ul>
                </Card>
              </div>
            </Section>

            {/* 3. 系统架构 */}
            <Section title="3. 系统架构">
              <div className="bg-black/30 rounded-xl p-6 font-mono text-sm text-purple-200 overflow-x-auto">
                <pre>{`
┌─────────────────────────────────────────────────────────┐
│                      客户端层                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐ │
│  │ Next.js  │  │ iOS App  │  │ 微信小程序 │  │  Siri   │ │
│  │  PWA     │  │(Capacitor)│ │  (Taro)   │  │ 快捷指令│ │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬────┘ │
└───────┼──────────────┼────────────┼──────────────┼──────┘
        │              │            │              │
        ▼              ▼            ▼              ▼
┌─────────────────────────────────────────────────────────┐
│                   API 网关层 (Nginx)                     │
│  health.executor.life → Next.js (3000)                  │
│  health-api.executor.life → FastAPI (8000)               │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│                FastAPI 后端 (42 路由模块)                 │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐             │
│  │ Auth API │  │Health API│  │  Chat API  │             │
│  │(JWT认证) │  │(CRUD接口)│  │(AI对话核心)│             │
│  └──────────┘  └──────────┘  └─────┬─────┘             │
│                                    │                    │
│  ┌─────────────────────────────────▼──────────────────┐ │
│  │              ChatService (核心引擎)                 │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐         │ │
│  │  │健康上下文 │  │ LLM 调用 │  │ Action   │         │ │
│  │  │构建器    │  │(OpenClaw)│  │ 解析执行  │         │ │
│  │  └──────────┘  └──────────┘  └──────────┘         │ │
│  └────────────────────────────────────────────────────┘ │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ Garmin   │  │ Weather  │  │ Quark    │              │
│  │ Scheduler│  │ Service  │  │ Search   │              │
│  └──────────┘  └──────────┘  └──────────┘              │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│                     数据存储层                           │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │PostgreSQL│  │  Redis   │  │ ChromaDB │              │
│  │ (60 表)  │  │ (缓存)   │  │(向量知识库)│             │
│  └──────────┘  └──────────┘  └──────────┘              │
└─────────────────────────────────────────────────────────┘
                `}</pre>
              </div>
            </Section>

            {/* 4. OpenClaw 集成 */}
            <Section title="4. OpenClaw AI 集成">
              <p>
                系统使用自建的 <Hl>OpenClaw</Hl> 大语言模型作为核心 AI 引擎，部署在
                <code className="mx-1 px-1.5 py-0.5 bg-white/10 rounded text-cyan-300 text-sm">bot.executor.life</code>，
                通过 OpenAI 兼容的 API 接口调用。
              </p>

              <Card title="配置参数">
                <div className="font-mono text-sm space-y-1">
                  <div><span className="text-gray-400">Base URL:</span> <span className="text-cyan-300">https://bot.executor.life/v1</span></div>
                  <div><span className="text-gray-400">Model:</span> <span className="text-cyan-300">openclaw:main</span></div>
                  <div><span className="text-gray-400">协议:</span> <span className="text-cyan-300">OpenAI /chat/completions 兼容</span></div>
                  <div><span className="text-gray-400">备选:</span> <span className="text-cyan-300">gpt-4o-mini (OpenAI 直连)</span></div>
                </div>
              </Card>

              <Card title="调用流程">
                <div className="bg-black/20 rounded-lg p-4 font-mono text-sm text-purple-200">
                  <pre>{`1. 用户发送消息 → POST /chat/send
2. ChatService 构建系统提示 (800+ 行健康上下文)
3. 调用 OpenClaw API → stream 返回
4. 解析回复中的 <<<ACTIONS:[...]>>> 标记
5. 执行 actions (写入数据库)
6. 返回 AI 回复 + 数据操作结果`}</pre>
                </div>
              </Card>

              <p className="text-white/60 text-sm">
                OpenClaw 是基于开源大模型的自部署方案，避免了对外部 LLM 服务的依赖，
                同时保证了健康数据的隐私安全——所有数据处理在自有服务器完成。
              </p>
            </Section>

            {/* 5. 健康顾问核心架构 */}
            <Section title="5. 健康顾问 (ChatService) 核心架构">
              <p>
                健康顾问是系统的核心模块，位于 <code className="mx-1 px-1.5 py-0.5 bg-white/10 rounded text-cyan-300 text-sm">
                backend/app/services/chat_service.py</code>（约 1500 行），
                负责用户对话处理、健康上下文构建、AI 调用和 Action 执行。
              </p>

              <h4 className="text-lg font-semibold text-white mt-8 mb-3">5.1 健康上下文构建 (_build_health_context)</h4>
              <p>每次对话前，系统从 12+ 数据源构建个性化的健康上下文，注入到 AI 的系统提示中：</p>

              <div className="grid md:grid-cols-2 gap-3 mt-4">
                {[
                  { icon: '👤', title: '用户画像', desc: '姓名、性别、年龄、身高、慢性病、过敏史、健康目标' },
                  { icon: '🌤', title: '环境数据', desc: '实时天气(温度/湿度/风力)、空气质量(AQI)、运动指数' },
                  { icon: '✈️', title: '出行上下文', desc: '当前旅行状态、目的地城市、对应城市天气' },
                  { icon: '⌚', title: 'Garmin 数据', desc: '步数、静息心率、睡眠评分、压力值、Body Battery' },
                  { icon: '😴', title: '睡眠分析', desc: '近3天详细(深睡/REM/浅睡)、近7天和30天均值' },
                  { icon: '🏃', title: '运动分析', desc: '近7/30天: 平均步数、总消耗、活动时长' },
                  { icon: '🍎', title: '饮食分析', desc: '近3天详细(每餐热量/蛋白质/碳水/脂肪)、7天均值' },
                  { icon: '💧', title: '饮水记录', desc: '今日饮水量/目标、各饮品类型占比、7天趋势' },
                  { icon: '✅', title: '打卡记录', desc: '近7/30天按模板分组的完成率和均值' },
                  { icon: '🤒', title: '病症追踪', desc: '当前活跃病症、最新症状日志、慢病档案' },
                  { icon: '💊', title: '用药与补剂', desc: '当前服用药物、补剂记录' },
                  { icon: '😊', title: '情绪与活动', desc: '近期情绪记录、当前活动状态' },
                ].map((item, i) => (
                  <div key={i} className="bg-white/5 rounded-lg p-3 flex items-start gap-3">
                    <span className="text-xl mt-0.5">{item.icon}</span>
                    <div>
                      <div className="text-white font-medium text-sm">{item.title}</div>
                      <div className="text-purple-300 text-xs">{item.desc}</div>
                    </div>
                  </div>
                ))}
              </div>

              <h4 className="text-lg font-semibold text-white mt-8 mb-3">5.2 AI Action 系统</h4>
              <p>
                AI 回复中可以包含结构化的 Action 指令，格式为 <code className="mx-1 px-1.5 py-0.5 bg-white/10 rounded text-cyan-300 text-sm">
                {'<<<ACTIONS:[{...}]>>>'}</code>，由后端自动解析并执行数据写入。
              </p>

              <div className="overflow-x-auto mt-4">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-white/20">
                      <th className="text-left py-2 px-3 text-purple-200 font-medium">Action 类型</th>
                      <th className="text-left py-2 px-3 text-purple-200 font-medium">说明</th>
                      <th className="text-left py-2 px-3 text-purple-200 font-medium">触发示例</th>
                    </tr>
                  </thead>
                  <tbody className="text-purple-100">
                    {[
                      ['checkin', '打卡记录', '"我今天跑步了30分钟"'],
                      ['water', '饮水记录', '"刚喝了一杯咖啡"'],
                      ['supplement', '补剂服用', '"我吃了维生素C"'],
                      ['symptom', '症状记录', '"今天有点头痛"'],
                      ['rhinitis', '鼻炎记录', '"洗了鼻子，打了3个喷嚏"'],
                      ['illness_create', '创建病症', '"我感冒了"'],
                      ['illness_update', '更新病症', '"感冒好多了"'],
                      ['excretion', '排泄记录', '"刚上了厕所"'],
                      ['sleep', '睡眠记录', '"昨晚11点睡的，今早7点起"'],
                      ['activity_status', '活动状态', '"我在学习"'],
                    ].map(([type, desc, example], i) => (
                      <tr key={i} className="border-b border-white/5">
                        <td className="py-2 px-3 font-mono text-cyan-300">{type}</td>
                        <td className="py-2 px-3">{desc}</td>
                        <td className="py-2 px-3 text-white/50 italic">{example}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <h4 className="text-lg font-semibold text-white mt-8 mb-3">5.3 完整对话处理流程</h4>
              <div className="bg-black/30 rounded-xl p-6 font-mono text-sm text-purple-200 overflow-x-auto">
                <pre>{`用户: "我刚跑步30分钟"

1. [接收消息] POST /chat/send → ChatService.send_message()
2. [加载历史] 从 ChatMessage 表获取最近对话上下文
3. [构建上下文] _build_health_context() → 从 12+ 数据源聚合
4. [搜索增强] 判断是否需要联网 → Quark Search API
5. [构建 Prompt]
   ├── 系统提示 (角色 + 能力 + 数据格式说明)
   ├── 健康上下文 (当前用户的所有健康数据摘要)
   ├── 搜索结果 (如有)
   └── 历史对话
6. [调用 LLM] OpenClaw API → stream 返回回复
7. [解析 Action] 从回复中提取 <<<ACTIONS:[...]>>>
   └── { "type": "checkin", "template": "跑步",
         "value": 30, "notes": "30分钟跑步" }
8. [执行 Action] _handle_checkin_action()
   └── 写入 CheckinRecord 表
9. [保存对话] ChatMessage 表记录用户消息 + AI 回复
10. [返回结果]
    ├── reply: "很棒！30分钟的跑步已记录..."
    ├── activities_saved: true
    └── conversation_id: "abc123"`}</pre>
              </div>

              <h4 className="text-lg font-semibold text-white mt-8 mb-3">5.4 双模式支持</h4>
              <div className="grid md:grid-cols-2 gap-4">
                <Card title="成人模式 (健康顾问)">
                  <p className="text-sm text-purple-200">
                    专业的私人健康顾问角色，基于用户健康数据提供个性化建议。支持饮食记录与热量计算、
                    活动状态追踪、联网搜索辅助回答。回答简洁专业，涉及严重健康问题建议就医。
                  </p>
                </Card>
                <Card title="儿童模式 (健康小老师)">
                  <p className="text-sm text-purple-200">
                    面向儿童的健康学习助手，用讲故事、打比方的方式解释健康知识。使用活泼语气和 emoji，
                    涵盖饮食、运动、睡眠、卫生等话题。遇到复杂医学问题引导咨询家长。
                  </p>
                </Card>
              </div>
            </Section>

            {/* 6. 数据模型 */}
            <Section title="6. 数据模型 (60 张表)">
              <p>系统使用 PostgreSQL 存储 60 个数据模型，按业务域分组如下：</p>
              <div className="grid md:grid-cols-2 gap-4 mt-4">
                {[
                  { title: '用户与认证', models: 'User, UserProfile, HealthGoal, InvitationCode, UserApplication, DeviceCredential' },
                  { title: '健康追踪', models: 'BasicHealthData, WeightRecord, BloodPressureRecord, GarminData, ExerciseRecord, MoodRecord' },
                  { title: '饮食与营养', models: 'DietRecord, WaterIntake, SupplementDefinition, SupplementRecord, SupplementIntake' },
                  { title: '医疗与疾病', models: 'MedicalExam, MedicalExamItem, DiseaseRecord, DiseaseTemplate, UserDiseaseProfile, SymptomLog' },
                  { title: '打卡与目标', models: 'HealthCheckin, CheckinTemplate, CheckinRecord, Goal, GoalProgress, HabitDefinition, HabitRecord' },
                  { title: '专项追踪', models: 'VisionRecord, DailyEyeHabit, MenstrualCycle, CycleSymptom, Medication, MedicationLog' },
                  { title: '生活记录', models: 'SleepRecord, ActivityStatus, IllnessEpisode, IllnessUpdate, ExcretionRecord, OutdoorActivity, Trip, TripItem' },
                  { title: 'AI 与通知', models: 'ChatConversation, ChatMessage, DailyRecommendation, HealthAnalysisCache, AIInsight, RealtimeRecommendation' },
                  { title: '社交与积分', models: 'Friendship, PKChallenge, ChallengeParticipant' },
                  { title: '复盘与报告', models: 'DailyReview, PeriodReview, HealthReport, NewsArticle' },
                ].map((group, i) => (
                  <div key={i} className="bg-white/5 rounded-lg p-3">
                    <div className="text-white font-medium text-sm mb-1">{group.title}</div>
                    <div className="text-purple-300 text-xs font-mono leading-relaxed">{group.models}</div>
                  </div>
                ))}
              </div>
            </Section>

            {/* 7. API 路由 */}
            <Section title="7. API 路由体系 (42 模块)">
              <p>后端通过 42 个路由模块提供 REST API，按功能分类：</p>
              <div className="overflow-x-auto mt-4">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-white/20">
                      <th className="text-left py-2 px-3 text-purple-200 font-medium">分类</th>
                      <th className="text-left py-2 px-3 text-purple-200 font-medium">路由模块</th>
                    </tr>
                  </thead>
                  <tbody className="text-purple-100">
                    {[
                      ['认证与用户', '/auth, /users, /user-profile, /user-merge, /invitation'],
                      ['核心健康', '/basic-health, /weight, /blood-pressure, /heart-rate, /body-composition'],
                      ['AI 对话', '/chat (对话核心), /ai-insights, /daily-recommendation'],
                      ['运动与活动', '/garmin-connect, /garmin-analysis, /workout, /activity-status'],
                      ['饮食与营养', '/diet, /diet-recommendation, /water, /supplements'],
                      ['打卡与目标', '/checkin, /goals, /daily-points'],
                      ['医疗与疾病', '/medical-exams, /diseases, /disease-tracking, /illness'],
                      ['专项追踪', '/mood, /medication, /womens-health, /vision, /sleep, /excretion, /rhinitis'],
                      ['社交功能', '/friendship, /pk-challenge'],
                      ['系统管理', '/admin, /monitoring, /performance, /news, /devices, /upload'],
                      ['外部集成', '/siri, /data-collection, /external (用户 API Key)'],
                    ].map(([category, routes], i) => (
                      <tr key={i} className="border-b border-white/5">
                        <td className="py-2 px-3 text-white font-medium whitespace-nowrap">{category}</td>
                        <td className="py-2 px-3 font-mono text-cyan-300 text-xs">{routes}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Section>

            {/* 8. Garmin 同步 */}
            <Section title="8. Garmin 数据同步">
              <p>系统通过 OAuth 认证对接 Garmin Connect，定时自动同步用户的运动、睡眠、心率等数据。</p>
              <Card title="同步机制">
                <ul className="space-y-2 text-sm text-purple-200">
                  <li><Hl>定时任务:</Hl> Celery Beat 每天 08:01 (北京时间) 自动触发</li>
                  <li><Hl>OAuth 缓存:</Hl> Garmin Session 缓存复用，减少登录频率</li>
                  <li><Hl>凭证加密:</Hl> 使用 Fernet 对称加密存储 Garmin 密码</li>
                  <li><Hl>错误容忍:</Hl> 连续失败自动标记凭证失效，管理员可手动重置</li>
                  <li><Hl>数据范围:</Hl> 支持按天数回溯同步 (1-30 天)</li>
                  <li><Hl>管理面板:</Hl> 管理员可查看所有用户同步状态、手动触发同步</li>
                </ul>
              </Card>
              <Card title="同步数据项">
                <div className="grid grid-cols-2 gap-2 text-sm text-purple-200">
                  <span>每日步数与距离</span>
                  <span>卡路里消耗</span>
                  <span>静息心率</span>
                  <span>平均压力值</span>
                  <span>Body Battery</span>
                  <span>睡眠评分与时长</span>
                  <span>深睡/REM/浅睡占比</span>
                  <span>活动强度分钟</span>
                </div>
              </Card>
            </Section>

            {/* 9. 外部 API 系统 */}
            <Section title="9. 外部 API Key 系统">
              <p>
                系统提供开放 API 接口，允许第三方应用通过 API Key 访问用户健康数据或推送建议。
                这是与外部 AI Agent（如 browser-llm-orchestrator）集成的核心接口。
              </p>
              <Card title="接口设计">
                <ul className="space-y-2 text-sm text-purple-200">
                  <li><Hl>认证方式:</Hl> SHA256 哈希的 API Key，通过 X-API-Key 请求头传递</li>
                  <li><Hl>权限范围:</Hl> read (读取健康数据) / write (推送建议)</li>
                  <li><Hl>隐私保护:</Hl> 默认隐藏 GPS 坐标、设备信息等敏感字段</li>
                  <li><Hl>限额控制:</Hl> 每用户最多 10 个 API Key</li>
                  <li><Hl>读取接口:</Hl> GET /external/health-data — 返回聚合健康数据</li>
                  <li><Hl>写入接口:</Hl> POST /external/recommendations — 推送外部健康建议</li>
                </ul>
              </Card>
            </Section>

            {/* 10. 前端架构 */}
            <Section title="10. 前端架构">
              <p>前端基于 Next.js 14 构建，54 个页面路由覆盖全部业务功能。</p>

              <Card title="核心架构模式">
                <ul className="space-y-2 text-sm text-purple-200">
                  <li><Hl>路由:</Hl> App Router (Next.js 14) — 基于文件系统的路由</li>
                  <li><Hl>状态管理:</Hl> TanStack React Query 管理服务端状态，AuthContext 管理认证</li>
                  <li><Hl>API 层:</Hl> 32 个 API 服务对象，通过 Axios 与后端通信</li>
                  <li><Hl>样式:</Hl> Tailwind CSS + 深色主题 (bg-gradient-to-br from-slate-900)</li>
                  <li><Hl>图表:</Hl> Recharts (柱状图、折线图、饼图)</li>
                  <li><Hl>图标:</Hl> lucide-react + @heroicons/react</li>
                  <li><Hl>地图:</Hl> Leaflet + react-leaflet (行程记录)</li>
                </ul>
              </Card>

              <Card title="多端支持">
                <ul className="space-y-2 text-sm text-purple-200">
                  <li><Hl>Web:</Hl> Next.js SSR + CSR，部署在 health.executor.life</li>
                  <li><Hl>iOS App:</Hl> Capacitor 8 封装，App ID: life.executor.health</li>
                  <li><Hl>微信小程序:</Hl> Taro 框架 (packages/mini-program/)</li>
                  <li><Hl>Siri 快捷指令:</Hl> 语音录入健康数据，通过 /siri API 接口</li>
                </ul>
              </Card>

              <h4 className="text-lg font-semibold text-white mt-6 mb-3">页面分类 (54 个路由)</h4>
              <div className="grid md:grid-cols-3 gap-3">
                {[
                  { title: '核心页面', pages: '首页, 健康概览, 今日建议, 健康顾问, 积分' },
                  { title: '健康追踪', pages: '仪表盘, 运动, 心率, 体重, 血压, 身体成分, 健康评分' },
                  { title: '每日记录', pages: '饮食, 饮水, 睡眠, 打卡, 补剂, 活动状态' },
                  { title: '专项管理', pages: '情绪, 用药, 女性健康, 鼻炎, 视力, 病症' },
                  { title: '社交功能', pages: '好友PK, 资讯' },
                  { title: '系统管理', pages: '设置, 管理后台, 知识库, 性能监控' },
                ].map((group, i) => (
                  <div key={i} className="bg-white/5 rounded-lg p-3">
                    <div className="text-white font-medium text-sm mb-1">{group.title}</div>
                    <div className="text-purple-300 text-xs">{group.pages}</div>
                  </div>
                ))}
              </div>
            </Section>

            {/* 11. 联网搜索 */}
            <Section title="11. 联网搜索 (Quark Search)">
              <p>
                健康顾问支持联网搜索能力，当用户提问涉及最新信息、医学知识或健康资讯时，
                系统会自动调用阿里云 Quark 搜索 API 获取网络信息，作为额外上下文注入到 AI 对话中。
              </p>
              <Card title="工作流程">
                <div className="bg-black/20 rounded-lg p-4 font-mono text-sm text-purple-200">
                  <pre>{`1. AI 判断问题需要搜索 → 生成搜索关键词
2. 调用阿里云 IQS API (alibabacloud_iqs20241111)
3. 返回 Top-N 搜索结果 (标题+摘要+URL)
4. 将搜索结果注入对话上下文
5. AI 基于搜索结果 + 健康数据综合回答`}</pre>
                </div>
              </Card>
            </Section>

            {/* 12. 部署架构 */}
            <Section title="12. 部署架构">
              <div className="grid md:grid-cols-2 gap-4">
                <Card title="服务器配置">
                  <ul className="space-y-1 text-sm text-purple-200">
                    <li>阿里云 ECS: 39.98.206.178</li>
                    <li>前端: PM2 管理 → :3000</li>
                    <li>后端: systemd 管理 → :8000</li>
                    <li>Nginx 反向代理 + SSL 证书</li>
                    <li>PostgreSQL 数据库</li>
                    <li>Redis 缓存服务</li>
                  </ul>
                </Card>
                <Card title="域名规划">
                  <ul className="space-y-1 text-sm text-purple-200">
                    <li><span className="text-cyan-300">health.executor.life</span> → 前端</li>
                    <li><span className="text-cyan-300">health-api.executor.life</span> → 后端 API</li>
                    <li><span className="text-cyan-300">bot.executor.life</span> → OpenClaw LLM</li>
                  </ul>
                </Card>
              </div>
              <Card title="部署脚本">
                <div className="font-mono text-sm text-purple-200 space-y-1">
                  <div><code className="text-cyan-300">./deploy.sh -f</code> — 仅部署前端</div>
                  <div><code className="text-cyan-300">./deploy.sh -b</code> — 仅部署后端</div>
                  <div><code className="text-cyan-300">./deploy.sh -a</code> — 全量部署</div>
                  <div><code className="text-cyan-300">./deploy.sh -r</code> — 重启服务</div>
                  <div><code className="text-cyan-300">./deploy.sh -s</code> — 查看状态</div>
                </div>
              </Card>
            </Section>

            {/* 13. 统计 */}
            <Section title="13. 系统规模统计">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {[
                  { num: '60', label: '数据库表' },
                  { num: '42', label: 'API 路由模块' },
                  { num: '54', label: '前端页面' },
                  { num: '32', label: 'API 服务对象' },
                  { num: '10', label: 'AI Action 类型' },
                  { num: '12+', label: '健康数据源' },
                  { num: '45+', label: '后端依赖包' },
                  { num: '1500+', label: 'ChatService 行数' },
                ].map((stat, i) => (
                  <div key={i} className="bg-white/5 rounded-xl p-4 text-center">
                    <div className="text-2xl font-bold text-cyan-400">{stat.num}</div>
                    <div className="text-purple-300 text-xs mt-1">{stat.label}</div>
                  </div>
                ))}
              </div>
            </Section>

          </div>
        </div>
      </div>
    </main>
  );
}

// --- Helper Components ---

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="text-xl font-bold text-white border-b border-white/10 pb-2 mb-4">{title}</h2>
      {children}
    </section>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-white/5 rounded-xl p-4 mt-3">
      <h5 className="text-white font-semibold text-sm mb-2">{title}</h5>
      {children}
    </div>
  );
}

function Tag({ children }: { children: React.ReactNode }) {
  return (
    <code className="px-1.5 py-0.5 bg-purple-500/20 text-purple-300 rounded text-xs font-mono">
      {children}
    </code>
  );
}

function Hl({ children }: { children: React.ReactNode }) {
  return <span className="text-cyan-400 font-medium">{children}</span>;
}
