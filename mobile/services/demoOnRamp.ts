import { buildDailyArtifact, type DailyArtifact } from './dailyArtifact';
import { buildChatContextRoute, type AgentContextPayload } from '../utils/agentContext';

export type DemoOnRampMilestoneKey = 'safety_brain' | 'evidence_card' | 'top_action';

export interface DemoOnRampMilestone {
  key: DemoOnRampMilestoneKey;
  title: string;
  description: string;
}

export interface DemoOnRampRuntime {
  mode: 'demo';
  isolated: true;
  estimatedMinutes: number;
  sourceLabel: string;
  dailyArtifact: DailyArtifact;
  milestones: DemoOnRampMilestone[];
  chatPrompt: string;
}

export function buildDemoOnRampRuntime(nowMs = Date.now()): DemoOnRampRuntime {
  const dailyArtifact = buildDailyArtifact({
    nowMs,
    readinessScore: 72,
    nowItem: {
      id: 'demo-postmeal-walk',
      title: '午餐后步行 10 分钟',
      subtitle: '示例:餐后轻运动帮助降低血糖波动,今天先做低强度',
      scheduled_for: '12:40',
      can_complete: false,
      complete_ref: null,
      deep_link: null,
    },
    fallbackAction: null,
    sleepHours: 6.1,
    hrv: 38,
    spo2: 96,
    healthKitLastSyncAt: nowMs - 8 * 60 * 1000,
    safetyAlerts: [{ severity: 'high', title: '示例:睡眠不足,今天避免高强度训练' }],
  });

  return {
    mode: 'demo',
    isolated: true,
    estimatedMinutes: 5,
    sourceLabel: '示例数据,不写入真实档案',
    dailyArtifact: {
      ...dailyArtifact,
      stateLabel: '示例运行时',
      actions: {
        canComplete: false,
        canSkip: false,
        skipRequiresReason: false,
        canAskReva: true,
      },
    },
    milestones: [
      {
        key: 'safety_brain',
        title: '安全脑拦截',
        description: '先识别不适合今天做的高强度建议。',
      },
      {
        key: 'evidence_card',
        title: '证据卡',
        description: '把睡眠、HRV、血氧和行动理由放在同一张卡。',
      },
      {
        key: 'top_action',
        title: '下一步行动',
        description: '只给一个现在最值得做的小动作。',
      },
    ],
    chatPrompt: '请用示例数据演示 Reva 如何把安全边界、证据卡和下一步行动串起来。请明确这是示例体验,不要保存为我的真实健康记录。',
  };
}

function buildDemoContext(runtime: DemoOnRampRuntime): AgentContextPayload {
  return {
    demo: true,
    write_policy: 'never_persist_demo_data',
    source_label: runtime.sourceLabel,
    runtime: {
      mode: runtime.mode,
      estimated_minutes: runtime.estimatedMinutes,
      daily_artifact: {
        state_label: runtime.dailyArtifact.stateLabel,
        top_action: {
          title: runtime.dailyArtifact.topAction?.title ?? null,
          subtitle: runtime.dailyArtifact.topAction?.subtitle ?? null,
          scheduled_for: runtime.dailyArtifact.topAction?.scheduledFor ?? null,
          source: runtime.dailyArtifact.topAction?.source ?? null,
        },
        evidence: runtime.dailyArtifact.evidence.map(item => ({
          id: item.id,
          label: item.label,
          value: item.value,
          tone: item.tone,
        })),
        safety_boundary: {
          level: runtime.dailyArtifact.safetyBoundary.level,
          label: runtime.dailyArtifact.safetyBoundary.label,
        },
        freshness: {
          label: runtime.dailyArtifact.freshness.label,
          tone: runtime.dailyArtifact.freshness.tone,
          last_sync_at: runtime.dailyArtifact.freshness.lastSyncAt,
        },
      },
      milestones: runtime.milestones.map(item => ({
        key: item.key,
        title: item.title,
        description: item.description,
      })),
    },
    expected_agent_behavior: [
      '明确标注这是示例体验',
      '不要求用户披露真实隐私数据',
      '不生成诊断或用药调整',
      '最后引导用户连接 HealthKit 或导入真实报告',
    ],
  };
}

export function getDemoOnRampChatRoute(runtime = buildDemoOnRampRuntime()) {
  return buildChatContextRoute({
    prompt: runtime.chatPrompt,
    context: buildDemoContext(runtime),
    badge: '示例体验',
    newChat: true,
  });
}
