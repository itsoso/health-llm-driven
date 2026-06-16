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
  | 'advisory';

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
}

export interface TodayTimelineResponse {
  date: string;
  current_window: string;
  /** 未来/现在该做的(action/checkup/advisory/outcome) */
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
