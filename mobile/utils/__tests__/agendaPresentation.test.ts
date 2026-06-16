import { agendaItemPresentation, agendaSummary } from '../agendaPresentation';

describe('agendaPresentation', () => {
  it('maps training light to a non-actionable wrist-friendly status', () => {
    const presentation = agendaItemPresentation({
      type: 'training',
      title: '今日训练:暂停高强度',
      status: 'info',
      priority: 90,
      light: 'red',
      readiness_score: 38,
      confidence: 'high',
      detail: '急性病/不适,训练应休息',
      source: { object_type: 'training_decision', object_id: 1 },
    });

    expect(presentation.icon).toBe('barbell-outline');
    expect(presentation.tone).toBe('red');
    expect(presentation.statusLabel).toBe('训练红灯');
    expect(presentation.meta).toContain('Readiness 38');
    expect(presentation.canComplete).toBe(false);
  });

  it('counts protocol actions separately from read-only info items', () => {
    expect(agendaSummary([
      { type: 'hydration', title: '喝水', status: 'pending', priority: 50, source: { object_type: 'health_protocol', object_id: 1 } },
      { type: 'training', title: '今日训练:可按计划', status: 'info', priority: 80, source: { object_type: 'training_decision', object_id: 2 } },
      { type: 'checkup', title: '复查:尿酸', status: 'due', priority: 75, source: { object_type: 'health_problem', object_id: 3 } },
    ])).toEqual({ total: 3, actionable: 1, overdue: 0, info: 1 });
  });
});
