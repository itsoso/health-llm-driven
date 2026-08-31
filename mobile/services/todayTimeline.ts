/**
 * 今日时间线 service —— 消费后端 GET /timeline/today(范式翻转第一刀)。
 *
 * 一打开首页就看到「今天该做什么 + 刚刚发生了什么 + 我的行动有没有用」,
 * 看板降级到时间线之下。完成动作复用 /agenda/complete 双轨写真实记录。
 *
 * TODO: 部署后改用 api.generated.ts 的 paths['/timeline/today']
 *       (后端 OpenAPI 还没部署,这里先手写最小契约,字段对齐后端 timeline_service)。
 */
import api from './api';

export type TimelineKind =
  | 'action'
  | 'observation'
  | 'outcome'
  | 'checkup'
  | 'advisory'
  | 'work'; // CalDAV busy block(无标题,仅时长)

// 后端 HealthEvent.driver —— 「为什么这项在这」。
// plan_driven=预定计划(协议/用药/复查/日历) / time_driven=按时触发(系统时刻卡,暂未派生)
// / event_driven=事件触发(餐后步行 / 训练灯 / 数据质量 / 观测)。
// 非驱动行(缺省)→ null;前端不画驱动 chip(优雅降级)。
export type TimelineDriver = 'plan_driven' | 'time_driven' | 'event_driven';

export type TimelineWindow =
  | 'morning'
  | 'noon'
  | 'afternoon'
  | 'evening'
  | 'bedtime'
  | 'anytime';

export type TimelineDirection = 'up' | 'down';

export interface TimelineCompleteRef {
  object_type: string;
  object_id: number;
  // F5b 多剂闭环:剂量槽 "HH:MM"。仅真多剂(后端 reminder_times ≥2 个时点)的项带它;
  // 单剂/每日一次省略(后端 model_serializer 不输出该键 → 行为与改前一致)。
  slot?: string;
}

export interface TimelineProof {
  metric: string;
  label: string;
  delta: string;
  // 后端 ProofRef.direction 是 Optional[str];非数值指标(如血压)发 null。
  direction: TimelineDirection | null;
  // 后端在 outcome proof 里给的归因诚实标记(相关非因果)。脚注无条件显示,不依赖此值。
  association_only?: boolean;
}

export interface TodayTimelineItem {
  id: string;
  kind: TimelineKind;
  time_window: TimelineWindow;
  // 真实时点 HH:MM(用药/补剂/锻炼块/工作块);无确定时点 → null(按 time_window 排)。
  scheduled_for?: string | null;
  title: string;
  subtitle: string | null;
  icon: string; // Ionicons name
  color: string; // hex, 直接用
  status: string | null; // pending|completed|skipped|info|overdue|due
  priority: number;
  can_complete: boolean;
  complete_ref: TimelineCompleteRef | null;
  deep_link: string | null;
  severity: string | null;
  proof: TimelineProof | null;
  action_kind?: string | null;
  // 驱动来源标记(后端 HealthEvent.driver);缺省/null → 不画驱动 chip。
  driver?: TimelineDriver | null;
}

export interface TodayTimelineResponse {
  date: string;
  current_window: string;
  /**
   * 时间感知的「现在该做什么」单项 id —— 指向 items 里的一行(当下/下一项,非清晨第一项)。
   * null = 今天没有可完成的下一步。首页 hero 据此渲染「现在该做什么」。
   */
  now?: string | null;
  /** 未来/现在该做的,按 scheduled_for 时间升序(action/checkup/advisory/outcome/work) */
  items: TodayTimelineItem[];
  /** 今天已发生(observation) */
  past: {
    completed_count: number;
    events: TodayTimelineItem[];
  };
  counts: {
    actionable: number;
    overdue: number;
    info: number;
  };
}

export async function fetchTodayTimeline(): Promise<TodayTimelineResponse> {
  const resp = await api.get<TodayTimelineResponse>('/timeline/today');
  return resp.data;
}
