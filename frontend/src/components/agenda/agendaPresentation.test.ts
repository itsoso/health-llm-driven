import { agendaItemPresentation, agendaSummary } from './agendaPresentation';

describe('agendaPresentation', () => {
  it('labels training decisions as read-only health gates', () => {
    const item = agendaItemPresentation({
      type: 'training',
      title: '今日训练:降一级',
      status: 'info',
      priority: 80,
      light: 'yellow',
      readiness_score: 62,
      confidence: 'medium',
      detail: '恢复就绪度 62/100；多设备一致性 80%',
      source: { object_type: 'training_decision', object_id: 1 },
    });

    expect(item.icon).toBe('Dumbbell');
    expect(item.tone).toBe('yellow');
    expect(item.statusLabel).toBe('训练黄灯');
    expect(item.meta).toContain('Readiness 62');
    expect(item.canComplete).toBe(false);
  });

  it('summarizes overdue checkups and pending actions', () => {
    const summary = agendaSummary([
      { type: 'checkup', title: '复查:血脂', status: 'overdue', priority: 95, source: { object_type: 'health_problem', object_id: 2 } },
      { type: 'hydration', title: '温水杯', status: 'pending', priority: 50, source: { object_type: 'health_protocol', object_id: 3 } },
      { type: 'data_quality', title: '设备数据待核对:HRV', status: 'info', priority: 70, source: { object_type: 'data_quality', object_id: 1 } },
    ]);

    expect(summary).toEqual({
      total: 3,
      actionable: 1,
      overdue: 1,
      info: 1,
    });
  });
});
