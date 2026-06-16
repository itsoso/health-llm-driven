export interface AgendaSource {
  object_type: string;
  object_id: number;
}

export interface AgendaItem {
  type: string;
  title: string;
  status: string;
  time_window?: string;
  priority: number;
  can_default_complete?: boolean;
  detail?: string;
  responsible?: string;
  next_due?: string;
  light?: 'green' | 'yellow' | 'red';
  zone?: string;
  readiness_score?: number | null;
  confidence?: string | number | null;
  source: AgendaSource;
}

export interface AgendaToday {
  agenda_date: string;
  count: number;
  items: AgendaItem[];
}

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
  hydration: 'Droplets',
  medication: 'Pill',
  diet: 'Utensils',
  sleep: 'Moon',
  training: 'Dumbbell',
  checkup: 'CalendarCheck',
  data_quality: 'GitCompare',
  correction: 'Wrench',
};

export function agendaItemPresentation(item: AgendaItem): AgendaItemPresentation {
  if (item.type === 'training') {
    const tone = item.light ?? 'yellow';
    const readiness = typeof item.readiness_score === 'number' ? `Readiness ${item.readiness_score}` : null;
    const confidence = item.confidence != null ? String(item.confidence) : null;
    return {
      icon: 'Dumbbell',
      tone,
      statusLabel: `训练${lightLabel(tone)}`,
      meta: [readiness, confidence].filter(Boolean).join(' · '),
      canComplete: false,
    };
  }

  if (item.type === 'data_quality') {
    return {
      icon: 'GitCompare',
      tone: 'yellow',
      statusLabel: '设备待核对',
      meta: item.detail ?? '',
      canComplete: false,
    };
  }

  const canComplete = item.source.object_type === 'health_protocol' && item.status === 'pending';
  return {
    icon: TYPE_ICON[item.type] ?? 'Circle',
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
