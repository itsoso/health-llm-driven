import api from './api';

export interface DataHealthModuleStatus {
  status: 'ok' | 'warning' | 'error' | string;
  message?: string;
  [key: string]: any;
}

export interface DataHealthStatus {
  garmin?: DataHealthModuleStatus;
  hrv?: DataHealthModuleStatus;
  diet?: DataHealthModuleStatus;
  water?: DataHealthModuleStatus;
  notifications?: DataHealthModuleStatus;
  genetic?: DataHealthModuleStatus;
}

export interface DataPrompt {
  key: string;
  severity: 'blocking' | 'useful' | 'optional';
  title: string;
  body: string;
  route?: string;
}

export interface SleepQuestionPrompt {
  label: string;
  route: string;
}

const PROMPT_CONFIG: Record<string, Omit<DataPrompt, 'body'>> = {
  garmin: { key: 'garmin', severity: 'blocking', title: '连接 Garmin', route: '/settings' },
  hrv: { key: 'hrv', severity: 'useful', title: '补齐 HRV 数据', route: '/settings' },
  diet: { key: 'diet', severity: 'useful', title: '记录今天饮食', route: '/diet' },
  water: { key: 'water', severity: 'useful', title: '记录饮水', route: '/(tabs)/record' },
  notifications: { key: 'notifications', severity: 'optional', title: '检查推送提醒', route: '/notification-settings' },
  genetic: { key: 'genetic', severity: 'optional', title: '补充基因数据' },
};

const SEVERITY_ORDER = { blocking: 0, useful: 1, optional: 2 };

export async function fetchDataHealthStatus(): Promise<DataHealthStatus> {
  const { data } = await api.get<DataHealthStatus>('/data-health/status');
  return data;
}

// ──────────────────────────────────────────────────────────────
// 数据正确性自检(量纲/范围/层断连;系统自我监控)
// 后端 GET /data-health/integrity(PR #152)。区别于 /status(完整度),这里查**正确性**。
// 见 backend/app/services/data_integrity.py::check_user_integrity。
// ──────────────────────────────────────────────────────────────

export type IntegritySeverity = 'critical' | 'warning' | 'info' | string;

export interface IntegrityIssue {
  code: string;
  severity: IntegritySeverity;
  detail: string;
  count: number;
  fix_hint: string;
}

export interface DataIntegrityReport {
  healthy: boolean;
  issue_count: number;
  issues: IntegrityIssue[];
}

export async function fetchDataIntegrity(): Promise<DataIntegrityReport> {
  const { data } = await api.get<DataIntegrityReport>('/data-health/integrity');
  return data;
}

const INTEGRITY_SEVERITY_ORDER: Record<string, number> = { critical: 0, warning: 1, info: 2 };

/** issues 按严重度排序(critical 在前),未知 severity 排末尾。 */
export function sortIntegrityIssues(issues: IntegrityIssue[]): IntegrityIssue[] {
  return [...issues].sort(
    (a, b) =>
      (INTEGRITY_SEVERITY_ORDER[a.severity] ?? 99) - (INTEGRITY_SEVERITY_ORDER[b.severity] ?? 99),
  );
}

export function buildDataPrompts(status: DataHealthStatus | null | undefined): DataPrompt[] {
  if (!status) return [];

  return Object.entries(PROMPT_CONFIG)
    .flatMap(([key, config]) => {
      const item = status[key as keyof DataHealthStatus];
      if (!item || item.status === 'ok') return [];
      return [{
        ...config,
        body: item.message || '这项数据不完整，相关分析可信度会下降。',
      }];
    })
    .sort((a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity]);
}

export function getSleepQuestionPrompt(question: string): SleepQuestionPrompt {
  if (/异丙托溴铵|用药|药|喷鼻|鼻喷|服用/.test(question)) {
    return { label: '去用药记录', route: '/(tabs)/record' };
  }
  if (/运动|训练|跑步|骑行|力量|高强度/.test(question)) {
    return { label: '去运动记录', route: '/workout-list' };
  }
  if (/饮食|晚餐|夜宵|进食|饮酒|酒|咖啡|餐/.test(question)) {
    return { label: '去饮食记录', route: '/diet' };
  }
  if (/睡眠|鼻塞|憋醒|醒来|打鼾|呼吸|睡姿/.test(question)) {
    return { label: '去睡眠记录', route: '/sleep' };
  }
  return { label: '去补充记录', route: '/(tabs)/record' };
}
