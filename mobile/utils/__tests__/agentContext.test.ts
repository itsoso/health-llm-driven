import {
  AGENT_CONTEXT_MAX_CHARS,
  buildChatContextRoute,
  createDietAgentContext,
  createSafetyAlertAgentContext,
  createWorkoutDetailAgentContext,
  serializeAgentContext,
} from '../agentContext';

describe('agentContext', () => {
  it('builds chat route params with serialized context and badge', () => {
    const route = buildChatContextRoute({
      prompt: '今天饮食结构怎么样?',
      context: { from: 'diet/2026-05-14', date: '2026-05-14' },
      badge: '基于今日饮食 3 餐',
    });

    expect(route.pathname).toBe('/(tabs)/chat');
    expect(route.params.prompt).toBe('今天饮食结构怎么样?');
    expect(route.params.badge).toBe('基于今日饮食 3 餐');
    expect(JSON.parse(route.params.context)).toEqual({
      from: 'diet/2026-05-14',
      date: '2026-05-14',
    });
  });

  it('limits serialized context to the backend max length', () => {
    const context = serializeAgentContext({
      from: 'oversized',
      text: 'x'.repeat(AGENT_CONTEXT_MAX_CHARS + 500),
    });

    expect(context.length).toBeLessThanOrEqual(AGENT_CONTEXT_MAX_CHARS);
    expect(context).toContain('[truncated]');
  });

  it('creates compact diet context from daily summary', () => {
    const context = createDietAgentContext({
      record_date: '2026-05-14',
      total_calories: 1820,
      total_protein: 92,
      total_carbs: 180,
      total_fat: 58,
      total_fiber: 21,
      meals_count: 2,
      meals: [
        {
          id: 1,
          user_id: 1,
          record_date: '2026-05-14',
          meal_type: 'breakfast',
          food_items: '鸡蛋、燕麦',
          calories: 520,
          protein: 28,
          carbs: 60,
          fat: 18,
          fiber: 8,
          alcohol_units: null,
          image_url: null,
          notes: '训练前',
          health_tips: null,
        },
      ],
    });

    expect(context).toEqual({
      from: 'diet/2026-05-14',
      date: '2026-05-14',
      totals: {
        calories: 1820,
        protein: 92,
        carbs: 180,
        fat: 58,
        fiber: 21,
      },
      targets: null,
      meals: [
        {
          meal_type: 'breakfast',
          food_items: '鸡蛋、燕麦',
          calories: 520,
          protein: 28,
          carbs: 60,
          fat: 18,
          fiber: 8,
          notes: '训练前',
        },
      ],
    });
  });

  it('keeps safety alert rule context with the alert payload', () => {
    const context = createSafetyAlertAgentContext({
      rule_id: 'hrv_drop',
      severity: 'high',
      category: 'recovery',
      title: 'HRV 连续下降',
      message: 'HRV 低于 7 日均值 20%',
      action: '今晚降低训练强度',
      context: { hrv_today: 28, hrv_7d: 40 },
    });

    expect(context).toEqual({
      from: 'safety-alert/hrv_drop',
      alert_id: 'hrv_drop',
      rule_name: 'HRV 连续下降',
      severity: 'high',
      category: 'recovery',
      message: 'HRV 低于 7 日均值 20%',
      action: '今晚降低训练强度',
      triggered_metrics: { hrv_today: 28, hrv_7d: 40 },
    });
  });

  it('creates a compact single workout review context without route coordinates', () => {
    const context = createWorkoutDetailAgentContext({
      workout: {
        id: 42,
        user_id: 7,
        source: 'garmin',
        workout_date: '2026-05-21',
        workout_type: 'running',
        workout_name: 'Morning Run',
        start_time: '2026-05-21T07:10:00+08:00',
        end_time: '2026-05-21T07:55:00+08:00',
        duration_seconds: 2700,
        distance_meters: 8200,
        avg_heart_rate: 143,
        max_heart_rate: 171,
        calories: 520,
        steps: 8600,
        avg_speed_kmh: 10.9,
        max_speed_kmh: null,
        avg_pace_seconds_per_km: 330,
        avg_cadence: 172,
        max_cadence: null,
        avg_stride_length_cm: 104,
        elevation_gain_meters: 62,
        elevation_loss_meters: null,
        training_effect_aerobic: 3.2,
        training_effect_anaerobic: 0.8,
        vo2max: 48,
        training_load: 126,
        ai_analysis: null,
        post_workout_analysis: null,
        route_data: JSON.stringify([{ lat: 31.1, lng: 121.2 }]),
      },
      chart: {
        workout_id: 42,
        workout_type: 'running',
        duration_seconds: 2700,
        heart_rate_timeline: [{ time: 0, hr: 120 }, { time: 60, hr: 135 }],
        heart_rate_zones: [{ zone: 'Z3', minutes: 18, percentage: 40 }],
        pace_timeline: [{ time: 0, pace: 330 }],
        elevation_timeline: [{ distance: 1, elevation: 20 }],
        avg_heart_rate: 143,
        max_heart_rate: 171,
        avg_pace_display: `5'30"/km`,
        total_distance_km: 8.2,
        calories: 520,
      },
      analysis: {
        workout_id: 42,
        overall_rating: '良好',
        intensity_assessment: '中等偏上',
        heart_rate_analysis: '心率稳定',
        hr_zone_assessment: null,
        pace_analysis: '后半程略降速',
        training_effect_summary: '有氧效果明确',
        recovery_recommendation: '补水并放松小腿',
        next_workout_suggestion: '下次安排轻松跑',
        comparison_with_history: null,
        key_insights: ['配速稳定'],
        improvement_tips: ['加强跑后拉伸'],
      },
      postAnalysis: {
        success: true,
        recovery_tips: ['泡沫轴放松小腿', '补充碳水和蛋白'],
        improvement_tips: ['控制前 2 公里速度'],
      },
      postAnalysisMarkdown: '## 总评\n本次有氧基础不错。',
    });

    expect(context.from).toBe('workout/42');
    expect(context.feedback_intent).toBe('post_workout_review');
    expect(context.workout).toMatchObject({
      id: 42,
      type: 'running',
      duration_min: 45,
      distance_km: 8.2,
      has_route: true,
    });
    expect(JSON.stringify(context)).not.toContain('31.1');
    expect(context.chart).toMatchObject({
      heart_rate_samples_count: 2,
      pace_samples_count: 1,
      elevation_samples_count: 1,
    });
    expect(context.expected_agent_output).toEqual([
      '本次运动复盘',
      '拉伸与恢复建议',
      '下次训练安排',
      '需要用户补充反馈的问题',
    ]);
  });
});
