import { buildDailyArtifact } from '../dailyArtifact';

describe('buildDailyArtifact', () => {
  const NOW = new Date('2026-06-27T08:20:00+08:00').getTime();

  it('promotes the timeline now-item as the only top action', () => {
    const artifact = buildDailyArtifact({
      nowMs: NOW,
      readinessScore: 86,
      nowItem: {
        id: 'hydration-1',
        title: '喝 200ml 温水',
        subtitle: '起床后补水,再开始运动',
        scheduled_for: '08:00',
        can_complete: true,
        complete_ref: { object_type: 'health_protocol', object_id: 12 },
        deep_link: null,
      },
      fallbackAction: { title: '做 10 分钟拉伸', domain: 'movement' },
      sleepHours: 7.2,
      hrv: 48,
      spo2: 97,
      healthKitLastSyncAt: NOW - 10 * 60 * 1000,
      safetyAlerts: [],
    });

    expect(artifact.stateLabel).toBe('今日状态');
    expect(artifact.topAction?.title).toBe('喝 200ml 温水');
    expect(artifact.topAction?.subtitle).toBe('起床后补水');
    expect(artifact.topAction?.source).toBe('timeline');
    expect(artifact.topAction?.canComplete).toBe(true);
    expect(artifact.actions.skipRequiresReason).toBe(true);
    expect(artifact.evidence).toHaveLength(3);
    expect(artifact.evidence.map((item) => item.id)).toEqual(['sleep', 'hrv', 'spo2']);
  });

  it('falls back to the daily plan when no timeline now-item exists', () => {
    const artifact = buildDailyArtifact({
      nowMs: NOW,
      readinessScore: null,
      nowItem: null,
      fallbackAction: {
        title: '午餐后步行 10 分钟',
        domain: 'nutrition',
        reason: '降低餐后血糖波动',
      },
      healthKitLastSyncAt: null,
      safetyAlerts: [],
    });

    expect(artifact.topAction).toMatchObject({
      title: '午餐后步行 10 分钟',
      subtitle: '降低餐后血糖波动',
      source: 'daily_plan',
      canComplete: false,
    });
    expect(artifact.readiness.label).toBe('待同步');
    expect(artifact.freshness).toMatchObject({
      label: 'HealthKit 未自动同步',
      tone: 'caution',
    });
  });

  it('marks stale readiness and critical safety boundary without inventing a diagnosis', () => {
    const artifact = buildDailyArtifact({
      nowMs: NOW,
      readinessScore: 91,
      readinessStale: true,
      readinessDate: '2026-06-26',
      nowItem: null,
      fallbackAction: null,
      sleepHours: 6.5,
      hrv: 42,
      spo2: 92,
      healthKitLastSyncAt: NOW - 5 * 60 * 60 * 1000,
      safetyAlerts: [{ severity: 'high', title: '夜间血氧持续偏低' }],
    });

    expect(artifact.readiness).toMatchObject({
      score: null,
      staleScore: 91,
      label: '昨晚未同步',
      asOf: '2026-06-26',
    });
    expect(artifact.safetyBoundary).toEqual({
      level: 'risk',
      label: '有 1 条风险提醒',
    });
    expect(artifact.evidence[0]).toMatchObject({
      id: 'safety',
      label: '安全提醒',
      value: '夜间血氧持续偏低',
      tone: 'risk',
    });
    expect(artifact.topAction?.title).toBe('补齐今天记录');
  });
});
