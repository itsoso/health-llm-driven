'use client';

import { useEffect } from 'react';
import type { ReactNode } from 'react';
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
      <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-slate-900 via-emerald-950 to-slate-900">
        <div className="mx-auto h-12 w-12 animate-spin rounded-full border-b-2 border-emerald-300" />
      </div>
    );
  }

  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-900 via-emerald-950 to-slate-900 pb-24 pt-4">
      <div className="mx-auto max-w-5xl px-4 md:px-8">
        <div className="mb-8 flex items-center gap-3">
          <button
            onClick={() => router.push('/admin')}
            className="text-emerald-200 transition-colors hover:text-white"
          >
            &larr; 返回管理后台
          </button>
        </div>

        <div className="rounded-2xl border border-white/15 bg-white/10 p-6 backdrop-blur-lg md:p-10">
          <h1 className="mb-2 text-3xl font-bold text-white">系统技术架构文档</h1>
          <p className="mb-10 text-sm text-emerald-200">最后更新: 2026-07-04</p>

          <div className="space-y-10 text-[15px] leading-relaxed text-emerald-50">
            <Section title="1. 系统概述">
              <p>
                阿衡是面向个人长期健康管理的自有 Agent 系统。核心链路是“对话即记录、数据驱动计划、
                动态 UI 执行”，通过真实健康数据、知识库、可穿戴设备和多端交互，帮助用户降低日常记录成本，
                并形成可验证的健康干预闭环。
              </p>
            </Section>

            <Section title="2. 技术栈总览">
              <div className="grid gap-6 md:grid-cols-2">
                <Card title="后端">
                  <ul className="space-y-1">
                    <li><Tag>FastAPI</Tag> 异步 API 与 SSE</li>
                    <li><Tag>SQLAlchemy</Tag> PostgreSQL 持久化</li>
                    <li><Tag>Celery + Redis</Tag> 后台同步、提醒和分析任务</li>
                    <li><Tag>AgentExecutor</Tag> 工具调用、健康上下文和动态卡片编排</li>
                  </ul>
                </Card>
                <Card title="多端">
                  <ul className="space-y-1">
                    <li><Tag>Next.js</Tag> Web 管理台与运营面板</li>
                    <li><Tag>Expo / React Native</Tag> iPhone 主体验</li>
                    <li><Tag>Swift</Tag> Mac 和 Watch 端原生体验</li>
                    <li><Tag>Siri / 微信入口</Tag> 快速记录和对话入口</li>
                  </ul>
                </Card>
                <Card title="模型路由">
                  <ul className="space-y-1">
                    <li><Tag>TokenPlan</Tag> 默认阿里百炼模型池</li>
                    <li><Tag>LangBridge</Tag> 商用模型兼容代理</li>
                    <li><Tag>Usage Tracker</Tag> token、费用和性能剖析</li>
                    <li><Tag>Safety Guardian</Tag> 医疗安全边界与红线规则</li>
                  </ul>
                </Card>
                <Card title="数据层">
                  <ul className="space-y-1">
                    <li><Tag>PostgreSQL</Tag> 用户、健康记录、Agent 会话</li>
                    <li><Tag>ChromaDB</Tag> 系统知识库与检索</li>
                    <li><Tag>Garmin / HealthKit</Tag> 可穿戴和手机健康数据</li>
                    <li><Tag>审计日志</Tag> 关键写入与管理操作追踪</li>
                  </ul>
                </Card>
              </div>
            </Section>

            <Section title="3. 当前调用链路">
              <div className="overflow-x-auto rounded-xl bg-black/30 p-6 font-mono text-sm text-emerald-100">
                <pre>{`
┌──────────────────────────────────────────────────────────────┐
│                           客户端层                            │
│  Web 管理台   iPhone App   Mac App   Watch   Siri/微信入口     │
└───────────────┬────────────┬─────────┬───────┬───────────────┘
                │            │         │       │
                ▼            ▼         ▼       ▼
┌──────────────────────────────────────────────────────────────┐
│              Nginx / health.executor.life /api/v1             │
└──────────────────────────────┬───────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                         FastAPI 后端                          │
│  Auth / Diet / HealthKit / Medical Exams / Agent / Admin      │
│                                                              │
│  ┌──────────────────────┐   ┌──────────────────────────────┐ │
│  │ AgentExecutor         │   │ Safety / Privacy / Cost Gate │ │
│  │ 上下文 -> 工具 -> LLM │   │ 红线、token、性能、审计       │ │
│  └──────────┬───────────┘   └──────────────────────────────┘ │
│             ▼                                                │
│  TokenPlan / LangBridge / OpenAI-compatible providers         │
└─────────────┬────────────────────────────────────────────────┘
              ▼
┌──────────────────────────────────────────────────────────────┐
│          PostgreSQL / Redis / ChromaDB / 文件与报表存储        │
└──────────────────────────────────────────────────────────────┘
                `}</pre>
              </div>
            </Section>

            <Section title="4. Agent 对话与动态 UI">
              <div className="grid gap-4 md:grid-cols-2">
                <Card title="Agent API">
                  <ul className="space-y-1 text-sm">
                    <li><Tag>/agent/stream</Tag> 统一 SSE 对话入口</li>
                    <li><Tag>/agent/conversations</Tag> 会话列表、详情、重命名、删除</li>
                    <li><Tag>/agent/tools</Tag> 工具能力目录</li>
                  </ul>
                </Card>
                <Card title="动态卡片">
                  <ul className="space-y-1 text-sm">
                    <li>饮食记录、用药、体检报告、指标曲线、行动计划</li>
                    <li>卡片可交互，写入前必须经过意图和安全校验</li>
                    <li>Mac/Web/Mobile 共享同一后端语义和成本剖析</li>
                  </ul>
                </Card>
              </div>
            </Section>

            <Section title="5. 关键数据模型">
              <div className="grid gap-3 md:grid-cols-2">
                {[
                  ['用户与认证', 'User, UserProfile, HealthGoal, DeviceCredential'],
                  ['健康记录', 'DietRecord, WaterIntake, Medication, Supplement, GarminData'],
                  ['医疗数据', 'MedicalExam, MedicalExamItem, DiseaseRecord, ClinicalJournal'],
                  ['Agent 与成本', 'AgentConversation, AgentMessage, LLMUsage, InteractionFeedback'],
                  ['计划与执行', 'DailyArtifact, SmartReminder, Goal, CheckinRecord'],
                  ['知识与安全', 'SystemKnowledge, SafetyGuardian, AuditLog'],
                ].map(([title, models]) => (
                  <div key={title} className="rounded-lg bg-white/5 p-3">
                    <div className="mb-1 text-sm font-medium text-white">{title}</div>
                    <div className="font-mono text-xs leading-relaxed text-emerald-200">{models}</div>
                  </div>
                ))}
              </div>
              <p className="mt-3 text-xs text-emerald-200/70">
                注：AgentConversation 物理表名沿用早期历史表，以保护线上会话数据；代码层已使用 Agent 命名。
              </p>
            </Section>

            <Section title="6. 部署与发布">
              <div className="grid gap-4 md:grid-cols-2">
                <Card title="服务部署">
                  <ul className="space-y-1 text-sm">
                    <li><Tag>./deploy.sh -b</Tag> 后端部署</li>
                    <li><Tag>./deploy.sh -f</Tag> Web 部署</li>
                    <li><Tag>./deploy.sh -a</Tag> 全量部署</li>
                    <li><Tag>systemd / PM2</Tag> 进程管理</li>
                  </ul>
                </Card>
                <Card title="移动发布">
                  <ul className="space-y-1 text-sm">
                    <li><Tag>scripts/mobile-ota.sh</Tag> JS/TS/UI OTA 更新</li>
                    <li><Tag>scripts/mobile-local-qr.sh</Tag> 二维码安装包</li>
                    <li>默认不走 TestFlight，除非手工指定</li>
                  </ul>
                </Card>
              </div>
            </Section>
          </div>
        </div>
      </div>
    </main>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h2 className="mb-4 border-b border-white/10 pb-2 text-xl font-bold text-white">{title}</h2>
      {children}
    </section>
  );
}

function Card({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="mt-3 rounded-xl bg-white/5 p-4">
      <h5 className="mb-2 text-sm font-semibold text-white">{title}</h5>
      {children}
    </div>
  );
}

function Tag({ children }: { children: ReactNode }) {
  return (
    <span className="mr-1 inline-flex rounded bg-emerald-400/10 px-1.5 py-0.5 font-mono text-xs text-emerald-200">
      {children}
    </span>
  );
}
