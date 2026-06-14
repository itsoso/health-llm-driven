import { getCausalLinks, getConnectionStatus, type CausalLinksResponse, type ConnectionStatus } from './chronicHealth';
import { getDataIntegrity, type DataIntegrityReport } from './dataHealth';
import { getDeprescribingReview, type DeprescribingReview } from './medication';

export type HealthGuardrailItemKey =
  | 'data_integrity'
  | 'deprescribing'
  | 'connection'
  | 'causal_links';

export interface HealthGuardrailItem {
  key: HealthGuardrailItemKey;
  label: string;
  value: string;
  attention: boolean;
}

export interface HealthGuardrailSummary {
  attentionCount: number;
  title: string;
  subtitle: string;
  href: string;
  items: HealthGuardrailItem[];
}

interface HealthGuardrailSources {
  integrity?: DataIntegrityReport | null;
  deprescribing?: DeprescribingReview | null;
  connection?: ConnectionStatus | null;
  causalLinks?: CausalLinksResponse | null;
}

export function buildHealthGuardrailSummary({
  integrity,
  deprescribing,
  connection,
  causalLinks,
}: HealthGuardrailSources): HealthGuardrailSummary {
  const integrityIssues = Math.max(0, integrity?.issue_count ?? integrity?.issues?.length ?? 0);
  const medicationFlags = Math.max(0, deprescribing?.flags?.length ?? 0);
  const connectionDue = connection?.due === true;
  const causalInsightCount = Math.max(0, causalLinks?.intervention_effects?.length ?? 0);
  const attentionCount = integrityIssues + medicationFlags + (connectionDue ? 1 : 0);

  return {
    attentionCount,
    title:
      attentionCount > 0
        ? `健康守门 ${attentionCount} 项待处理`
        : causalInsightCount > 0
          ? `健康守门正常 · ${causalInsightCount} 条用药关联`
          : '健康守门正常',
    subtitle:
      attentionCount > 0
        ? '先处理会影响建议可信度的健康维护项。'
        : causalInsightCount > 0
          ? '数据可信，已有用药-指标关联可复盘。'
          : '数据与维护项暂无异常，继续执行今日闭环。',
    href: '/health-extras',
    items: [
      {
        key: 'data_integrity',
        label: '数据自检',
        value: integrity ? (integrityIssues > 0 ? `${integrityIssues} 个问题` : '通过') : '未加载',
        attention: integrityIssues > 0,
      },
      {
        key: 'deprescribing',
        label: '用药梳理',
        value: deprescribing
          ? (medicationFlags > 0 ? `${medicationFlags} 条候选` : `${deprescribing.active_count} 种在用`)
          : '未加载',
        attention: medicationFlags > 0,
      },
      {
        key: 'connection',
        label: '社会连接',
        value: connection
          ? (connectionDue ? '本周应自评' : connection.days_since != null ? `${connection.days_since} 天前` : '已维护')
          : '未加载',
        attention: connectionDue,
      },
      {
        key: 'causal_links',
        label: '指标关联',
        value: causalLinks
          ? (causalInsightCount > 0 ? `${causalInsightCount} 条可复盘` : '等待数据')
          : '未加载',
        attention: false,
      },
    ],
  };
}

export async function getHealthGuardrailSummary(): Promise<HealthGuardrailSummary> {
  const [integrity, deprescribing, connection, causalLinks] = await Promise.allSettled([
    getDataIntegrity(),
    getDeprescribingReview(),
    getConnectionStatus(),
    getCausalLinks(),
  ]);

  return buildHealthGuardrailSummary({
    integrity: settledValue(integrity),
    deprescribing: settledValue(deprescribing),
    connection: settledValue(connection),
    causalLinks: settledValue(causalLinks),
  });
}

function settledValue<T>(result: PromiseSettledResult<T>): T | null {
  return result.status === 'fulfilled' ? result.value : null;
}
