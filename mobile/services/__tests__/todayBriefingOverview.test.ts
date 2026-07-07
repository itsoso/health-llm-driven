import { buildTodayBriefingOverview } from '../todayBriefingOverview';

describe('buildTodayBriefingOverview', () => {
  it('builds the full mobile Today briefing from real source slices', () => {
    const rows = buildTodayBriefingOverview({
      weatherResponse: {
        weather: { temperature: 27, weather: '多云', humidity: 62 },
        exercise_advice: '适合轻度户外活动',
      },
      airQuality: { aqi: 52, aqi_description: '良', pm25: 20 },
      dailyPlan: {
        plan_date: '2026-07-07',
        primary_goal: '把晚餐后血糖波动压低',
        status: 'active',
        state_summary: {},
        actions: [
          {
            domain: 'movement',
            title: '晚饭后步行 10 分钟',
            why: '餐后窗口最适合做低强度活动。',
            when: 'after_dinner',
          },
        ],
      },
      dailyArtifact: {
        artifact_date: '2026-07-07',
        empty_state: false,
        state: { label: '今日状态', tone: 'focused', summary: '餐后窗口是今天重点。' },
        top_action: {
          id: 'walk',
          title: '晚饭后步行 10 分钟',
          do_now: '晚饭后 30 分钟内完成。',
          why_now: '今晚是最短可验证窗口。',
        },
        evidence: [],
        confidence: 'medium',
        freshness: { status: 'fresh', sources: [] },
        safety_boundary: '',
      },
      morningBriefing: {
        date: '2026-07-07',
        greeting: '早上好',
        sections: [
          {
            title: '😴 昨晚睡眠 (7月6日数据)',
            status: 'good',
            items: ['睡眠分数: 82分', '睡眠时长: 7.2小时'],
          },
          {
            title: '⚡ 身体状态',
            status: 'good',
            items: ['身体电量峰值: 81', '静息心率: 58 bpm'],
          },
        ],
      },
    });

    expect(rows.map(row => row.label)).toEqual(['天气', '空气质量', '今日规划', '建议', '昨日总结']);
    expect(rows.find(row => row.id === 'weather')?.value).toContain('27°');
    expect(rows.find(row => row.id === 'air')?.value).toBe('AQI 52 · 良');
    expect(rows.find(row => row.id === 'plan')?.value).toBe('把晚餐后血糖波动压低');
    expect(rows.find(row => row.id === 'advice')?.value).toBe('晚饭后步行 10 分钟');
    expect(rows.find(row => row.id === 'yesterday')?.value).toBe('睡眠分数: 82分');
    expect(rows.find(row => row.id === 'yesterday')?.detail).toContain('身体电量峰值: 81');
  });

  it('keeps explicit neutral fallbacks instead of inventing missing metrics', () => {
    const rows = buildTodayBriefingOverview({});

    expect(rows.map(row => row.label)).toEqual(['天气', '空气质量', '今日规划', '建议', '昨日总结']);
    expect(rows.find(row => row.id === 'weather')?.value).toBe('天气待同步');
    expect(rows.find(row => row.id === 'air')?.value).toBe('空气质量待同步');
    expect(rows.find(row => row.id === 'plan')?.value).toBe('今日规划待生成');
    expect(rows.find(row => row.id === 'advice')?.value).toBe('暂无新的行动建议');
    expect(rows.find(row => row.id === 'yesterday')?.value).toBe('昨日数据待同步');
  });
});
