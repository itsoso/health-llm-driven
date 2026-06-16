import type { AgendaItem } from '../services/agenda';

export interface AgendaSummary {
  total: number;
  actionable: number;
  overdue: number;
  info: number;
}

export interface AgendaItemPresentation {
  icon: string;
  tone: 'green' | 'yellow' | 'red' | 'blue' | 'gray';
  statusLabel: string;
  meta: string;
  canComplete: boolean;
}

const STATUS_LABEL: Record<string, string> = {
  pending: '待完成',
  completed: '已完成',
  skipped: '已跳过',
  due: '待复查',
  overdue: '已逾期',
  info: '今日建议',
};

const TYPE_ICON: Record<string, string> = {
  hydration: 'water-outline',
  medication: 'medkit-outline',
  diet: 'restaurant-outline',
  sleep: 'moon-outline',
  training: 'barbell-outline',
  checkup: 'calendar-outline',
  data_quality: 'git-compare-outline',
  correction: 'construct-outline',
};

export function agendaItemPresentation(item: AgendaItem): AgendaItemPresentation {
  if (item.type === 'training') {
    const tone = item.light ?? 'yellow';
    const readiness = typeof item.readiness_score === 'number' ? `Readiness ${item.readiness_score}` : null;
    const confidence = item.confidence != null ? String(item.confidence) : null;
    return {
      icon: 'barbell-outline',
      tone,
      statusLabel: `训练${lightLabel(tone)}`,
      meta: [readiness, confidence].filter(Boolean).join(' · '),
      canComplete: false,
    };
  }

  if (item.type === 'data_quality') {
    return {
      icon: 'git-compare-outline',
      tone: 'yellow',
      statusLabel: '设备待核对',
      meta: item.detail ?? '',
      canComplete: false,
    };
  }

  const canComplete = item.source.object_type === 'health_protocol' && item.status === 'pending';
  return {
    icon: TYPE_ICON[item.type] ?? 'ellipse-outline',
    tone: item.status === 'overdue' ? 'red' : item.status === 'completed' ? 'green' : 'blue',
    statusLabel: STATUS_LABEL[item.status] ?? item.status,
    meta: [item.next_due, item.responsible].filter(Boolean).join(' · '),
    canComplete,
  };
}

export function agendaSummary(items: AgendaItem[]): AgendaSummary {
  return {
    total: items.length,
    actionable: items.filter(item => item.source.object_type === 'health_protocol' && item.status === 'pending').length,
    overdue: items.filter(item => item.status === 'overdue').length,
    info: items.filter(item => item.status === 'info').length,
  };
}

function lightLabel(light: 'green' | 'yellow' | 'red'): string {
  if (light === 'green') return '绿灯';
  if (light === 'red') return '红灯';
  return '黄灯';
}
