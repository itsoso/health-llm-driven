import api from './api';
import { getActiveCards } from './actionCards';
import { getSafetyReport } from './safety';

export interface TodayCoachEvidence {
  label: string;
  value: string;
  tone?: 'good' | 'warn' | 'bad';
}

export interface TodayCoachFocus {
  status: 'ok' | 'attention' | 'risk' | 'missing_data';
  title: string;
  reason: string;
  actionLabel: string;
  actionRoute?: string;
  evidence: TodayCoachEvidence[];
  verifyBy?: string;
}

function severityKey(severity: unknown): string {
  if (typeof severity === 'string') return severity;
  if (severity && typeof severity === 'object' && 'label' in severity) {
    return String((severity as { label?: string }).label || 'info');
  }
  return 'info';
}

export async function getTodayCoachFocus(today: string): Promise<TodayCoachFocus> {
  const [scoreRes, safetyRes, cardsRes, dataHealthRes] = await Promise.allSettled([
    api.get(`/health-score/enhanced/me?target_date=${today}`).then(r => r.data),
    getSafetyReport(),
    getActiveCards(),
    api.get('/data-health/status').then(r => r.data),
  ]);

  const score = scoreRes.status === 'fulfilled' ? scoreRes.value : null;
  const alerts = safetyRes.status === 'fulfilled' ? safetyRes.value.alerts || [] : [];
  const activeCards = cardsRes.status === 'fulfilled' ? cardsRes.value || [] : [];
  const dataHealth = dataHealthRes.status === 'fulfilled' ? dataHealthRes.value : null;

  const highAlert = alerts.find((alert: any) => (
    ['critical', 'high'].includes(severityKey(alert.severity))
  ));
  if (highAlert) {
    return {
      status: 'risk',
      title: highAlert.title,
      reason: highAlert.message,
      actionLabel: highAlert.action || '查看处理建议',
      actionRoute: '/(tabs)/alerts',
      evidence: [{ label: '安全告警', value: '高优先', tone: 'bad' }],
    };
  }

  const firstCard = activeCards[0];
  if (firstCard) {
    return {
      status: 'attention',
      title: firstCard.title,
      reason: '你有一个正在执行的健康行动。',
      actionLabel: '查看行动',
      actionRoute: '/(tabs)/alerts',
      evidence: [{ label: '行动卡', value: firstCard.card_type || 'active' }],
      verifyBy: firstCard.expires_at || undefined,
    };
  }

  if (dataHealth?.garmin?.status && dataHealth.garmin.status !== 'ok') {
    return {
      status: 'missing_data',
      title: '先补齐 Garmin 数据',
      reason: dataHealth.garmin.message || '关键生理数据不完整，今日判断可信度会下降。',
      actionLabel: '去设置',
      actionRoute: '/settings',
      evidence: [{
        label: '数据状态',
        value: dataHealth.garmin.status || 'unknown',
        tone: 'warn',
      }],
    };
  }

  return {
    status: 'ok',
    title: '今日状态稳定',
    reason: score?.suggestions?.[0] || '暂无高优先级风险，保持记录和执行。',
    actionLabel: '生成今日简报',
    evidence: [{ label: '健康评分', value: String(score?.total_score ?? '--') }],
  };
}
